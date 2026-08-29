"""Prepare and track data-broker opt-out requests.

For email-based brokers a ready-to-send message is generated. For form-based
brokers the opt-out page is opened in a browser (Playwright) with the known
fields pre-filled and a screenshot taken; the final submit click is left to
the user, since brokers require CAPTCHAs and consent confirmation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .brokers import Broker, all_brokers, get_broker
from .config import Config
from .utils import data_dir, ensure_dir, get_logger, project_root, slugify, utcnow

log = get_logger("scrubpup.optout")

REQUESTS_FILE = "optout_requests.json"

EMAIL_TEMPLATE = """Subject: Data deletion / opt-out request - {name}

To the {broker} privacy team,

I am requesting the removal of my personal information from {broker} and any
affiliated sites, under applicable data protection law (GDPR Art. 17 / CCPA
1798.105, as applicable).

Full name: {name}
Email address(es): {emails}
Phone number(s): {phones}
Address(es): {addresses}
Profile URL(s): {profile_urls}

Please confirm in writing once the information has been suppressed and
deleted, and confirm that it will not be re-added from third-party sources.
I expect a response within {days} days.

Regards,
{name}
"""


@dataclass
class OptOutRequest:
    broker: str
    broker_name: str
    method: str
    opt_out_url: str
    status: str = "prepared"  # prepared | submitted | confirmed | failed
    email: str = ""
    profile_url: str = ""
    artifact_path: str = ""
    screenshot_path: str = ""
    expected_days_to_removal: int = 14
    instructions: str = ""
    timestamp: str = field(default_factory=utcnow)


def requests_path() -> Path:
    return data_dir() / REQUESTS_FILE


def load_requests(path: Path | None = None) -> list[OptOutRequest]:
    path = path or requests_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [OptOutRequest(**item) for item in raw]


def save_requests(items: list[OptOutRequest], path: Path | None = None) -> Path:
    path = path or requests_path()
    path.write_text(json.dumps([asdict(i) for i in items], indent=2))
    return path


def record_request(request: OptOutRequest) -> None:
    items = load_requests()
    for idx, existing in enumerate(items):
        if existing.broker == request.broker and existing.email == request.email:
            items[idx] = request
            break
    else:
        items.append(request)
    save_requests(items)


def outbox_dir() -> Path:
    return ensure_dir(project_root() / "outbox")


def render_email(broker: Broker, config: Config, *, email: str = "", profile_url: str = "") -> str:
    ident = config.identity
    return EMAIL_TEMPLATE.format(
        broker=broker.name,
        name=ident.name or "(your name)",
        emails=", ".join([email] if email else ident.emails) or "(none)",
        phones=", ".join(ident.phones) or "(none)",
        addresses="; ".join(ident.addresses) or "(none)",
        profile_urls=profile_url or "(see attached evidence)",
        days=broker.expected_days_to_removal,
    )


def _field_values(broker: Broker, config: Config, email: str, profile_url: str) -> dict[str, str]:
    ident = config.identity
    values = {
        "name": ident.name,
        "email": email or (ident.emails[0] if ident.emails else ""),
        "phone": ident.phones[0] if ident.phones else "",
        "address": ident.addresses[0] if ident.addresses else "",
        "profile_url": profile_url,
        "url": profile_url,
    }
    return {k: v for k, v in values.items() if k in broker.required_fields and v}


def prefill_form(broker: Broker, values: dict[str, str], *, screenshot_dir: Path) -> tuple[str, str]:
    """Open the opt-out page with Playwright and pre-fill known fields.

    Returns ``(screenshot_path, note)``. Nothing is submitted automatically.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", "playwright not installed: open the URL manually"

    selectors = {
        "name": "input[name*='name' i], input[id*='name' i]",
        "email": "input[type='email'], input[name*='email' i]",
        "phone": "input[type='tel'], input[name*='phone' i]",
        "address": "input[name*='address' i]",
        "profile_url": "input[name*='url' i], input[name*='link' i]",
        "url": "input[name*='url' i], input[name*='link' i]",
    }
    path = ensure_dir(screenshot_dir) / f"{slugify(broker.key)}-{utcnow().replace(':', '')}.png"
    filled: list[str] = []
    with sync_playwright() as pw:
        # Broker pages serve a stripped or challenge page to headless Chromium,
        # so a real browser window is used.
        browser = pw.chromium.launch(headless=False)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(broker.opt_out_url, wait_until="load", timeout=45_000)
            _settle(page)
            for key, value in values.items():
                selector = selectors.get(key)
                if selector and _fill_field(page, selector, value, key=key, broker=broker.key):
                    filled.append(key)
            # Client-side hydration can clear inputs after the first fill.
            page.wait_for_timeout(1_500)
            for key in list(filled):
                selector = selectors[key]
                if not _fill_field(page, selector, values[key], key=key, broker=broker.key):
                    filled.remove(key)
            page.screenshot(path=str(path), full_page=True)
        finally:
            browser.close()
    return str(path), f"pre-filled: {', '.join(filled) or 'nothing matched'} (submit manually)"


def _settle(page) -> None:
    """Wait for network activity to stop so hydration cannot wipe our input."""
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception as exc:  # noqa: BLE001 - a busy page is still fillable
        log.debug("page never went idle: %s", exc)


def _fill_field(page, selector: str, value: str, *, key: str, broker: str) -> bool:
    """Fill the first visible, editable match and confirm the value stuck."""
    for element in page.query_selector_all(selector):
        try:
            if not (element.is_visible() and element.is_editable()):
                continue
            if element.input_value() == value:
                return True
            element.fill(value)
            if element.input_value() == value:
                return True
        except Exception as exc:  # noqa: BLE001 - best-effort prefill
            log.debug("could not fill %s on %s: %s", key, broker, exc)
    return False


def prepare(
    broker: Broker,
    config: Config,
    *,
    email: str = "",
    profile_url: str = "",
    interactive: bool = False,
) -> OptOutRequest:
    """Prepare an opt-out request for one broker."""
    request = OptOutRequest(
        broker=broker.key,
        broker_name=broker.name,
        method=broker.type,
        opt_out_url=broker.opt_out_url,
        email=email or (config.identity.emails[0] if config.identity.emails else ""),
        profile_url=profile_url,
        expected_days_to_removal=broker.expected_days_to_removal,
        instructions=broker.instructions,
    )
    if broker.type == "email":
        body = render_email(broker, config, email=email, profile_url=profile_url)
        target = outbox_dir() / f"{slugify(broker.key)}.txt"
        header = f"To: {broker.contact_email or '(see ' + broker.opt_out_url + ')'}\n"
        target.write_text(header + body)
        request.artifact_path = str(target)
    elif interactive:
        values = _field_values(broker, config, email, profile_url)
        shot, note = prefill_form(broker, values, screenshot_dir=project_root() / "evidence" / "optout")
        request.screenshot_path = shot
        request.instructions = f"{broker.instructions} {note}".strip()
    record_request(request)
    return request


def prepare_all(config: Config, *, email: str = "", interactive: bool = False) -> list[OptOutRequest]:
    return [prepare(b, config, email=email, interactive=interactive) for b in all_brokers()]


def prepare_one(key: str, config: Config, **kwargs) -> OptOutRequest:
    broker = get_broker(key)
    if broker is None:
        raise KeyError(f"unknown broker: {key}")
    return prepare(broker, config, **kwargs)


def mark_status(broker_key: str, status: str) -> bool:
    items = load_requests()
    changed = False
    for item in items:
        if item.broker == broker_key:
            item.status = status
            item.timestamp = utcnow()
            changed = True
    if changed:
        save_requests(items)
    return changed
