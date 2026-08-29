"""Shared helpers: paths, logging, rate limiting, user-agent rotation, HTTP."""

from __future__ import annotations

import itertools
import logging
import os
import random
import re
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

USER_AGENTS = (
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
)

DEFAULT_TIMEOUT = 20


def project_root() -> Path:
    """Root directory used for config, data, evidence and reports."""
    env = os.environ.get("SCRUBPUP_HOME")
    if env:
        return Path(env).expanduser()
    return Path.cwd()


def data_dir() -> Path:
    return ensure_dir(project_root() / "data")


def config_dir() -> Path:
    return ensure_dir(project_root() / "config")


def evidence_dir() -> Path:
    return ensure_dir(project_root() / "evidence")


def reports_dir() -> Path:
    return ensure_dir(project_root() / "reports")


def log_dir() -> Path:
    return ensure_dir(data_dir() / "logs")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utcnow() -> str:
    """Timestamp used throughout stored records."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_duration(value: str) -> timedelta:
    """Parse a compact duration such as ``30m``, ``12h``, ``7d`` or ``2w``."""
    match = re.fullmatch(r"\s*(\d+)\s*([mhdw])\s*", value.lower())
    if not match:
        raise ValueError(f"invalid duration: {value!r} (use e.g. 30m, 12h, 7d, 2w)")
    amount, unit = int(match.group(1)), match.group(2)
    return {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
    }[unit]


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return re.sub(r"[^a-z0-9.\-]", "_", host) or "unknown"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def redact(value: str) -> str:
    """Mask an identifier so it can be written to logs safely.

    ``jane@example.com`` becomes ``j***@e******.com`` and ``+15551234567``
    becomes ``+1***-***-4567``.
    """
    value = value.strip()
    if not value:
        return ""
    if "@" in value:
        local, _, host = value.partition("@")
        name, dot, tld = host.rpartition(".")
        masked_host = f"{name[:1]}{'*' * max(len(name) - 1, 1)}{dot}{tld}" if dot else host
        return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{masked_host}"
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 7:
        prefix = "+" if value.startswith("+") else ""
        return f"{prefix}{digits[:1]}***-***-{digits[-4:]}"
    return f"{value[:1]}{'*' * max(len(value) - 1, 1)}"


def get_logger(name: str = "scrubpup", *, verbose: bool = False) -> logging.Logger:
    """Logger writing to stderr and to ``data/logs/scrubpup.log``.

    Handlers live on the ``scrubpup`` root logger only; child loggers
    propagate to it so records are emitted exactly once.
    """
    root = logging.getLogger("scrubpup")
    if not root.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s")
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
        try:
            file_handler = logging.FileHandler(log_dir() / "scrubpup.log")
        except OSError:  # read-only filesystem: stderr logging is enough
            pass
        else:
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logging.getLogger(name)


class UserAgentRotator:
    """Cycles through a fixed pool of desktop browser user agents."""

    def __init__(self, agents: Iterable[str] = USER_AGENTS, *, shuffle: bool = True) -> None:
        pool = list(agents)
        if not pool:
            raise ValueError("at least one user agent is required")
        if shuffle:
            random.shuffle(pool)
        self._pool = pool
        self._cycle: Iterator[str] = itertools.cycle(pool)

    @property
    def pool(self) -> list[str]:
        return list(self._pool)

    def next(self) -> str:
        return next(self._cycle)

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": self.next(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if extra:
            headers.update(extra)
        return headers


class RateLimiter:
    """Thread-safe limiter allowing at most ``rate`` calls per second."""

    def __init__(self, rate: float = 2.0, *, sleep=time.sleep, clock=time.monotonic) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.min_interval = 1.0 / rate
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> float:
        """Block until the next call is allowed; returns the seconds slept."""
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.min_interval
        if delay:
            self._sleep(delay)
        return delay


@dataclass
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str]
    text: str


class HttpClient:
    """Rate-limited requests wrapper with rotating user agents."""

    def __init__(
        self,
        *,
        rate: float = 2.0,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        rotator: UserAgentRotator | None = None,
        limiter: RateLimiter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.rotator = rotator or UserAgentRotator()
        self.limiter = limiter or RateLimiter(rate)
        self.timeout = timeout
        self.log = logger or get_logger("scrubpup.http")

    def get(self, url: str, **kwargs) -> HttpResponse | None:
        return self.request("GET", url, **kwargs)

    def request(self, method: str, url: str, **kwargs) -> HttpResponse | None:
        """Perform a request, returning ``None`` when the call fails."""
        headers = self.rotator.headers(kwargs.pop("headers", None))
        self.limiter.wait()
        try:
            response = self.session.request(
                method, url, headers=headers, timeout=kwargs.pop("timeout", self.timeout), **kwargs
            )
        except requests.RequestException as exc:
            self.log.warning("request failed %s %s: %s", method, url, exc)
            return None
        return HttpResponse(
            url=str(response.url),
            status=response.status_code,
            headers=dict(response.headers),
            text=response.text,
        )
