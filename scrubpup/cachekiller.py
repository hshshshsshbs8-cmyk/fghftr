"""Prepare search-engine cache / archive removal requests for a URL.

Google and Bing removal tools require being signed in to a Google/Microsoft
account and Wayback exclusions require an emailed request, so this module
generates the deep links and a ready-to-send request letter (text + printable
HTML the user can save as PDF) rather than submitting on the user's behalf.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

from .utils import data_dir, domain_of, ensure_dir, get_logger, project_root, utcnow

log = get_logger("scrubpup.cachekiller")

PURGE_FILE = "purge_requests.json"

GOOGLE_OUTDATED = "https://search.google.com/search-console/remove-outdated-content?url={url}"
BING_REMOVAL = "https://www.bing.com/webmasters/tools/contentremoval"
WAYBACK_EXCLUDE = "https://archive.org/about/exclude.php"
WAYBACK_EMAIL = "info@archive.org"

LETTER_TEMPLATE = """Subject: Removal request for archived/cached copies of {url}

Hello,

I am the person whose personal information appears at the URL below, and I
request removal of cached and archived copies of this page:

    {url}

The live page {live_note}. The cached/archived copies continue to expose my
personal information (contact details / home address / other identifiers),
which puts me at risk. Please remove or exclude this URL.

Requested on: {timestamp}
Signature: ______________________

Regards,
"""


@dataclass
class PurgeRequest:
    url: str
    timestamp: str = field(default_factory=utcnow)
    google_url: str = ""
    bing_url: str = BING_REMOVAL
    wayback_url: str = WAYBACK_EXCLUDE
    letter_path: str = ""
    letter_html_path: str = ""
    status: str = "prepared"


def purge_path() -> Path:
    return data_dir() / PURGE_FILE


def load_purges(path: Path | None = None) -> list[PurgeRequest]:
    path = path or purge_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [PurgeRequest(**item) for item in raw]


def save_purges(items: list[PurgeRequest], path: Path | None = None) -> Path:
    path = path or purge_path()
    path.write_text(json.dumps([asdict(i) for i in items], indent=2))
    return path


def build_letter(url: str, *, live_removed: bool = False) -> str:
    live_note = (
        "has already been taken down or no longer shows this content"
        if live_removed
        else "is pending removal at the source"
    )
    return LETTER_TEMPLATE.format(url=url, live_note=live_note, timestamp=utcnow())


def letter_html(letter: str) -> str:
    body = letter.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Removal request</title>"
        "<style>body{font:14px/1.5 Georgia,serif;max-width:42em;margin:3em auto;"
        "white-space:pre-wrap}</style></head>"
        f"<body><h2>Cache/archive removal request</h2><p>{body}</p>"
        "<p><em>Print this page or save as PDF, sign it, and send it to "
        f"{WAYBACK_EMAIL} (Wayback) or attach it to the search engine forms.</em></p>"
        "</body></html>"
    )


def purge(url: str, *, live_removed: bool = False) -> PurgeRequest:
    """Prepare removal requests for all supported targets."""
    request = PurgeRequest(url=url, google_url=GOOGLE_OUTDATED.format(url=quote(url, safe="")))

    letters = ensure_dir(project_root() / "outbox" / "purge")
    stamp = utcnow().replace(":", "").replace("-", "")
    base = f"{domain_of(url)}-{stamp}"
    letter = build_letter(url, live_removed=live_removed)
    txt = letters / f"{base}.txt"
    txt.write_text(f"To: {WAYBACK_EMAIL}\n{letter}")
    html = letters / f"{base}.html"
    html.write_text(letter_html(letter))
    request.letter_path = str(txt)
    request.letter_html_path = str(html)

    items = load_purges()
    items.append(request)
    save_purges(items)
    log.info("prepared purge request for %s", url)
    return request
