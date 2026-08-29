"""Offline demo: scan a fake persona against canned responses.

No network calls are made, so ``scrubpup demo`` is safe to run anywhere and
produces a complete workspace (findings, opt-out artifacts, report) under
``demo-workspace/``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Config, Identity, Settings
from .utils import HttpClient, HttpResponse, RateLimiter, get_logger

log = get_logger("scrubpup.demo")

PERSONA = Config(
    identity=Identity(
        name="Jane Q. Persona",
        emails=["jane.persona@example.com"],
        phones=["+1-555-0143-7788"],
        usernames=["janepersona"],
        addresses=["742 Evergreen Terrace, Springfield"],
        social_handles=["jpersona"],
    ),
    settings=Settings(scan_interval_hours=24, rate_limit_per_sec=1000.0),
)

_DDG_HTML = """
<html><body>
 <a class="result__a" href="https://www.spokeo.com/Jane-Persona/Illinois">Jane Q. Persona, Springfield IL - Spokeo</a>
 <a class="result__a" href="https://pastebin.com/raw/DEMO1234">leaked contact dump</a>
 <a class="result__a" href="https://www.truepeoplesearch.com/results?name=Jane%20Persona">Jane Persona public record</a>
</body></html>
"""

_GITHUB_JSON = json.dumps(
    {
        "items": [
            {
                "html_url": "https://github.com/demo-org/legacy-app/blob/main/.env.example",
                "repository": {"full_name": "demo-org/legacy-app"},
            }
        ]
    }
)

_REDDIT_JSON = json.dumps({"data": {"name": "janepersona", "total_karma": 431}})

_CDX_JSON = json.dumps(
    [
        ["urlkey", "timestamp", "original", "mimetype", "statuscode"],
        ["com,forum)/u/janepersona", "20220714031200", "http://forum.example.com/u/janepersona", "text/html", "200"],
    ]
)


class DemoClient(HttpClient):
    """HttpClient replacement that serves fixtures instead of live requests."""

    def __init__(self) -> None:
        super().__init__(rate=1000.0, limiter=RateLimiter(1000.0))

    def request(self, method: str, url: str, **kwargs) -> HttpResponse | None:
        if "api.github.com" in url:
            body = _GITHUB_JSON
        elif "reddit.com" in url:
            body = _REDDIT_JSON
        elif "web.archive.org/cdx" in url:
            body = _CDX_JSON
        elif "duckduckgo.com" in url:
            body = _DDG_HTML
        else:
            return HttpResponse(url=url, status=404, headers={}, text="")
        return HttpResponse(url=url, status=200, headers={"content-type": "text/html"}, text=body)


def workspace(root: Path | None = None) -> Path:
    """Point ScrubPup's paths at an isolated demo workspace."""
    path = (root or Path.cwd() / "demo-workspace").resolve()
    path.mkdir(parents=True, exist_ok=True)
    os.environ["SCRUBPUP_HOME"] = str(path)
    return path
