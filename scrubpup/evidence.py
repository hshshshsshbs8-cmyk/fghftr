"""Capture proof of exposure: screenshot, HTML, headers and response metadata.

Screenshots need Playwright (``pip install playwright && playwright install
chromium``). Without it, HTML and headers are still captured through requests.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .utils import HttpClient, domain_of, ensure_dir, evidence_dir, get_logger, today, utcnow

log = get_logger("scrubpup.evidence")


@dataclass
class Evidence:
    url: str
    directory: str
    timestamp: str
    status: int | None = None
    html_path: str = ""
    screenshot_path: str = ""
    headers_path: str = ""
    note: str = ""


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _capture_screenshot(url: str, target: Path) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, wait_until="load", timeout=45_000)
            page.screenshot(path=str(target), full_page=True)
        finally:
            browser.close()
    return str(target)


def capture(url: str, *, client: HttpClient | None = None, screenshot: bool = True) -> Evidence:
    """Capture evidence for ``url`` into ``evidence/YYYY-MM-DD/{domain}/``."""
    client = client or HttpClient()
    directory = ensure_dir(evidence_dir() / today() / domain_of(url))
    stamp = utcnow().replace(":", "").replace("-", "")
    record = Evidence(url=url, directory=str(directory), timestamp=utcnow())

    resp = client.get(url)
    if resp is None:
        record.note = "fetch failed"
        log.warning("could not fetch %s", url)
    else:
        record.status = resp.status
        html_path = directory / f"{stamp}.html"
        html_path.write_text(resp.text, errors="replace")
        headers_path = directory / f"{stamp}.headers.json"
        headers_path.write_text(json.dumps({"url": resp.url, "status": resp.status, "headers": resp.headers}, indent=2))
        record.html_path = str(html_path)
        record.headers_path = str(headers_path)

    if screenshot:
        if playwright_available():
            try:
                record.screenshot_path = _capture_screenshot(url, directory / f"{stamp}.png")
            except Exception as exc:  # noqa: BLE001 - browser failures must not abort capture
                record.note = f"screenshot failed: {exc}"
                log.warning("screenshot failed for %s: %s", url, exc)
        else:
            record.note = "playwright not installed: no screenshot"

    manifest = directory / "manifest.json"
    entries = []
    if manifest.exists():
        try:
            entries = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            entries = []
    entries.append(asdict(record))
    manifest.write_text(json.dumps(entries, indent=2))
    return record
