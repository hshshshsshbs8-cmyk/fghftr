"""Scan public sources for the user's own identifiers.

Sources: DuckDuckGo HTML search, GitHub public code search, Reddit public
JSON, archive.org CDX API, and paste-site search via DuckDuckGo. Findings
are appended to ``data/findings.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup

from .config import Config
from .utils import HttpClient, data_dir, get_logger, redact, utcnow

log = get_logger("scrubpup.scanner")

PASTE_SITES = ("pastebin.com", "ghostbin.com", "throwbin.io", "justpaste.it", "rentry.co")

FINDINGS_FILE = "findings.json"


@dataclass
class Finding:
    source: str
    url: str
    type: str
    data_matched: str
    timestamp: str = field(default_factory=utcnow)
    screenshot_path: str = ""
    status: str = "pending"  # pending | submitted | removed
    detail: str = ""

    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.source, self.url, self.data_matched)


def findings_path() -> Path:
    return data_dir() / FINDINGS_FILE


def load_findings(path: Path | None = None) -> list[Finding]:
    path = path or findings_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [Finding(**item) for item in raw]


def save_findings(findings: list[Finding], path: Path | None = None) -> Path:
    path = path or findings_path()
    path.write_text(json.dumps([asdict(f) for f in findings], indent=2))
    return path


def filter_since(findings: list[Finding], since: timedelta) -> list[Finding]:
    """Keep only findings first seen within ``since`` of now."""
    cutoff = datetime.now(timezone.utc) - since
    kept = []
    for finding in findings:
        try:
            seen = datetime.fromisoformat(finding.timestamp)
        except ValueError:
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if seen >= cutoff:
            kept.append(finding)
    return kept


def merge_findings(existing: list[Finding], new: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """Merge new findings into existing; returns (all, genuinely-new)."""
    seen = {f.dedupe_key() for f in existing}
    fresh = [f for f in new if f.dedupe_key() not in seen]
    return existing + fresh, fresh


class Scanner:
    def __init__(self, config: Config, *, client: HttpClient | None = None) -> None:
        self.config = config
        self.client = client or HttpClient(rate=config.settings.rate_limit_per_sec)

    # -- sources -----------------------------------------------------------

    def duckduckgo(self, kind: str, value: str) -> list[Finding]:
        query = quote_plus(f'"{value}"')
        resp = self.client.get(f"https://html.duckduckgo.com/html/?q={query}")
        if not resp or resp.status != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        findings = []
        for link in soup.select("a.result__a")[:20]:
            href = link.get("href") or ""
            if not href.startswith("http"):
                continue
            findings.append(
                Finding(
                    source="duckduckgo",
                    url=href,
                    type=kind,
                    data_matched=value,
                    detail=link.get_text(" ", strip=True)[:200],
                )
            )
        return findings

    def paste_sites(self, kind: str, value: str) -> list[Finding]:
        sites = " OR ".join(f"site:{s}" for s in PASTE_SITES)
        query = quote_plus(f'"{value}" ({sites})')
        resp = self.client.get(f"https://html.duckduckgo.com/html/?q={query}")
        if not resp or resp.status != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        findings = []
        for link in soup.select("a.result__a")[:20]:
            href = link.get("href") or ""
            if any(site in href for site in PASTE_SITES):
                findings.append(
                    Finding(source="paste-sites", url=href, type=kind, data_matched=value)
                )
        return findings

    def github_code(self, kind: str, value: str) -> list[Finding]:
        """GitHub code search. Unauthenticated requests are heavily limited;
        failures are logged and skipped."""
        query = quote_plus(f'"{value}"')
        url = f"https://api.github.com/search/code?q={query}&per_page=10"
        resp = self.client.get(url, headers={"Accept": "application/vnd.github+json"})
        if not resp or resp.status != 200:
            if resp:
                log.info("github search unavailable (HTTP %s) for %s", resp.status, redact(value))
            return []
        try:
            items = json.loads(resp.text).get("items", [])
        except json.JSONDecodeError:
            return []
        return [
            Finding(
                source="github",
                url=item.get("html_url", ""),
                type=kind,
                data_matched=value,
                detail=item.get("repository", {}).get("full_name", ""),
            )
            for item in items
            if item.get("html_url")
        ]

    def reddit_user(self, kind: str, value: str) -> list[Finding]:
        if kind != "username" or not re.fullmatch(r"[A-Za-z0-9_\-]{3,20}", value):
            return []
        url = f"https://www.reddit.com/user/{quote(value)}/about.json"
        resp = self.client.get(url, headers={"Accept": "application/json"})
        if not resp or resp.status != 200:
            return []
        try:
            data = json.loads(resp.text).get("data", {})
        except json.JSONDecodeError:
            return []
        if not data.get("name"):
            return []
        return [
            Finding(
                source="reddit",
                url=f"https://www.reddit.com/user/{value}",
                type=kind,
                data_matched=value,
                detail=f"account exists, karma={data.get('total_karma', '?')}",
            )
        ]

    def archive_cdx(self, kind: str, value: str) -> list[Finding]:
        if kind not in ("username", "email"):
            return []
        needle = value.split("@")[0] if "@" in value else value
        if len(needle) < 4:
            return []
        url = (
            "https://web.archive.org/cdx/search/cdx"
            f"?url=*{quote(needle)}*&output=json&limit=25&collapse=urlkey&filter=statuscode:200"
        )
        resp = self.client.get(url)
        if not resp or resp.status != 200:
            return []
        try:
            rows = json.loads(resp.text)
        except json.JSONDecodeError:
            return []
        findings = []
        for row in rows[1:]:  # first row is the header
            if len(row) >= 3:
                findings.append(
                    Finding(
                        source="archive.org",
                        url=f"https://web.archive.org/web/{row[1]}/{row[2]}",
                        type=kind,
                        data_matched=value,
                        detail=row[2],
                    )
                )
        return findings

    def broker_search(self, kind: str, value: str) -> list[Finding]:
        """Grep broker search pages that support simple GET queries."""
        from .brokers import all_brokers

        findings = []
        for broker in all_brokers():
            if not broker.search_url:
                continue
            resp = self.client.get(broker.search_url.format(query=quote_plus(value)))
            if resp and resp.status == 200 and value.lower() in resp.text.lower():
                findings.append(
                    Finding(source=f"broker:{broker.key}", url=resp.url, type=kind, data_matched=value)
                )
        return findings

    # -- orchestration -------------------------------------------------------

    SOURCES = ("duckduckgo", "github", "reddit", "archive", "pastes", "brokers")

    def scan(self, target: str | None = None, sources: tuple[str, ...] = SOURCES) -> list[Finding]:
        enabled = self.config.settings.sources
        results: list[Finding] = []
        for kind, value in self.config.identity.identifiers(target):
            log.info("scanning %s %s", kind, redact(value))
            if "duckduckgo" in sources and enabled.get("duckduckgo", True):
                results += self.duckduckgo(kind, value)
            if "github" in sources and enabled.get("github", True):
                results += self.github_code(kind, value)
            if "reddit" in sources and enabled.get("reddit", True):
                results += self.reddit_user(kind, value)
            if "archive" in sources and enabled.get("archive", True):
                results += self.archive_cdx(kind, value)
            if "pastes" in sources and enabled.get("pastes", True):
                results += self.paste_sites(kind, value)
            if "brokers" in sources and enabled.get("brokers", False):
                results += self.broker_search(kind, value)
        return results

    def scan_and_store(self, target: str | None = None) -> tuple[list[Finding], list[Finding]]:
        """Run a scan, merge into findings.json; returns (all, new)."""
        existing = load_findings()
        merged, fresh = merge_findings(existing, self.scan(target))
        save_findings(merged)
        log.info("scan complete: %d findings (%d new)", len(merged), len(fresh))
        return merged, fresh
