"""Tests for scanning, redaction, rate limiting and config encryption."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scrubpup import brokers, cachekiller, optout, report, scanner
from scrubpup import config as config_mod
from scrubpup.config import Config, Identity, Settings
from scrubpup.demo import PERSONA, DemoClient
from scrubpup.utils import HttpResponse, RateLimiter, UserAgentRotator, parse_duration, redact


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    """Isolate every test in its own SCRUBPUP_HOME."""
    monkeypatch.setenv("SCRUBPUP_HOME", str(tmp_path))
    monkeypatch.delenv("SCRUBPUP_KEY", raising=False)
    return tmp_path


@pytest.fixture
def persona() -> Config:
    return PERSONA


# -- utils -------------------------------------------------------------------


def test_redact_masks_email_and_phone():
    assert redact("jane.persona@example.com") == "j***********@e******.com"
    assert redact("+1-555-0143-7788") == "+1***-***-7788"
    assert redact("janepersona").startswith("j*")
    assert "persona" not in redact("jane.persona@example.com")


def test_parse_duration():
    assert parse_duration("7d") == timedelta(days=7)
    assert parse_duration("12h") == timedelta(hours=12)
    assert parse_duration("2w") == timedelta(weeks=2)
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_rate_limiter_spaces_calls():
    slept: list[float] = []
    clock = iter([0.0, 0.0, 0.0])
    limiter = RateLimiter(2.0, sleep=slept.append, clock=lambda: next(clock))
    assert limiter.wait() == 0.0
    assert limiter.wait() == 0.5
    assert slept == [0.5]


def test_user_agent_rotator_cycles_pool():
    rotator = UserAgentRotator(["a", "b"], shuffle=False)
    assert [rotator.next() for _ in range(4)] == ["a", "b", "a", "b"]
    assert "User-Agent" in rotator.headers()


# -- config ------------------------------------------------------------------


def test_config_round_trip_is_encrypted_at_rest():
    original = Config(identity=Identity(name="Jane", emails=["jane@example.com"]), settings=Settings())
    path = config_mod.save_config(original)
    assert config_mod.is_encrypted(path)
    assert b"jane@example.com" not in path.read_bytes()

    loaded = config_mod.load_config(path)
    assert loaded.identity.emails == ["jane@example.com"]


def test_load_config_rejects_wrong_key(monkeypatch):
    from cryptography.fernet import Fernet

    path = config_mod.save_config(Config(identity=Identity(name="Jane")))
    monkeypatch.setenv("SCRUBPUP_KEY", Fernet.generate_key().decode())
    with pytest.raises(config_mod.ConfigError):
        config_mod.load_config(path)


def test_identifiers_filtered_by_target(persona):
    assert persona.identity.identifiers("email") == [("email", "jane.persona@example.com")]
    kinds = {kind for kind, _ in persona.identity.identifiers()}
    assert kinds == {"email", "phone", "username", "address", "name"}


# -- scanner -----------------------------------------------------------------


def test_duckduckgo_parses_results(persona):
    findings = scanner.Scanner(persona, client=DemoClient()).duckduckgo("email", "jane.persona@example.com")
    assert [f.url for f in findings] == [
        "https://www.spokeo.com/Jane-Persona/Illinois",
        "https://pastebin.com/raw/DEMO1234",
        "https://www.truepeoplesearch.com/results?name=Jane%20Persona",
    ]
    assert {f.source for f in findings} == {"duckduckgo"}


def test_paste_sites_only_keeps_paste_hosts(persona):
    findings = scanner.Scanner(persona, client=DemoClient()).paste_sites("email", "jane.persona@example.com")
    assert [f.url for f in findings] == ["https://pastebin.com/raw/DEMO1234"]


def test_github_and_reddit_and_archive_sources(persona):
    scan = scanner.Scanner(persona, client=DemoClient())
    assert scan.github_code("email", "jane.persona@example.com")[0].detail == "demo-org/legacy-app"
    reddit = scan.reddit_user("username", "janepersona")
    assert reddit[0].url == "https://www.reddit.com/user/janepersona"
    assert scan.reddit_user("email", "jane.persona@example.com") == []
    archive = scan.archive_cdx("username", "janepersona")
    assert archive[0].url.startswith("https://web.archive.org/web/20220714031200/")


def test_scan_and_store_deduplicates(persona):
    scan = scanner.Scanner(persona, client=DemoClient())
    first_all, first_new = scan.scan_and_store()
    assert first_all and first_all == first_new

    second_all, second_new = scan.scan_and_store()
    assert second_new == []
    assert len(second_all) == len(first_all)
    assert json.loads(scanner.findings_path().read_text())


def test_filter_since_drops_old_findings():
    old = scanner.Finding(
        source="duckduckgo",
        url="https://example.com/old",
        type="email",
        data_matched="jane@example.com",
        timestamp=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds"),
    )
    recent = scanner.Finding(source="reddit", url="https://example.com/new", type="username", data_matched="jane")
    assert scanner.filter_since([old, recent], timedelta(days=7)) == [recent]


def test_failed_requests_are_skipped(persona):
    class DeadClient(DemoClient):
        def request(self, method: str, url: str, **kwargs) -> HttpResponse | None:
            return None

    scan = scanner.Scanner(persona, client=DeadClient())
    assert scan.scan() == []
    assert set(scan.source_health.values()) == {"unreachable"}


def test_blocked_sources_are_reported_not_silently_empty(persona):
    class BlockedClient(DemoClient):
        def request(self, method: str, url: str, **kwargs) -> HttpResponse | None:
            return HttpResponse(url=url, status=429, headers={}, text="rate limited")

    scan = scanner.Scanner(persona, client=BlockedClient())
    assert scan.scan() == []
    assert scan.source_health["duckduckgo"] == "blocked (HTTP 429)"
    assert scan.source_health["github"] == "blocked (HTTP 429)"


def test_reddit_404_counts_as_healthy_absence(persona):
    class MissingUserClient(DemoClient):
        def request(self, method: str, url: str, **kwargs) -> HttpResponse | None:
            if "reddit.com" in url:
                return HttpResponse(url=url, status=404, headers={}, text="{}")
            return super().request(method, url, **kwargs)

    scan = scanner.Scanner(persona, client=MissingUserClient())
    assert not [f for f in scan.scan() if f.source == "reddit"]
    assert scan.source_health["reddit"] == "ok"


class _StubElement:
    """Minimal Playwright element stub: ``clears_after`` fills get wiped."""

    def __init__(self, *, visible: bool = True, editable: bool = True, clears_after: int = 0) -> None:
        self.visible, self.editable, self.clears_after = visible, editable, clears_after
        self.value = ""
        self.fills = 0

    def is_visible(self) -> bool:
        return self.visible

    def is_editable(self) -> bool:
        return self.editable

    def input_value(self) -> str:
        return self.value

    def fill(self, value: str) -> None:
        self.fills += 1
        self.value = "" if self.fills <= self.clears_after else value


class _StubPage:
    def __init__(self, elements: list[_StubElement]) -> None:
        self.elements = elements

    def query_selector_all(self, selector: str) -> list[_StubElement]:
        return self.elements


def test_fill_field_skips_hidden_inputs_and_reports_success():
    hidden = _StubElement(visible=False)
    real = _StubElement()
    page = _StubPage([hidden, real])
    assert optout._fill_field(page, "input", "me@example.com", key="email", broker="spokeo")
    assert hidden.value == "" and real.value == "me@example.com"


def test_fill_field_reports_failure_when_value_does_not_stick():
    wiped = _StubElement(clears_after=99)
    assert not optout._fill_field(_StubPage([wiped]), "input", "me@example.com", key="email", broker="spokeo")


def test_scan_respects_source_toggles(persona):
    config = Config(identity=persona.identity, settings=Settings(sources={"duckduckgo": False, "pastes": False}))
    sources = {f.source for f in scanner.Scanner(config, client=DemoClient()).scan()}
    assert "duckduckgo" not in sources and "paste-sites" not in sources
    assert {"github", "reddit", "archive.org"} & sources


# -- brokers / opt-out -------------------------------------------------------


def test_broker_database_is_well_formed():
    all_of_them = brokers.all_brokers()
    assert len(all_of_them) >= 50
    assert len({b.key for b in all_of_them}) == len(all_of_them)
    for broker in all_of_them:
        assert broker.type in ("form", "email")
        assert broker.opt_out_url.startswith("http")
        assert broker.required_fields
        assert broker.expected_days_to_removal > 0
        if broker.type == "email":
            assert broker.contact_email or broker.instructions


def test_get_and_find_broker():
    assert brokers.get_broker("Spokeo").key == "spokeo"
    assert brokers.get_broker("nope") is None
    assert any(b.key == "spokeo" for b in brokers.find_brokers("spok"))


def test_email_optout_writes_template(persona):
    request = optout.prepare_one("mylife", persona, email="jane.persona@example.com")
    body = Path(request.artifact_path).read_text()
    assert request.method == "email"
    assert "removalrequests@mylife.com" in body
    assert "Jane Q. Persona" in body
    assert optout.load_requests()[0].broker == "mylife"


def test_form_optout_is_recorded_without_submitting(persona):
    request = optout.prepare_one("spokeo", persona, profile_url="https://www.spokeo.com/Jane-Persona")
    assert request.method == "form"
    assert request.status == "prepared"
    assert request.artifact_path == ""


def test_mark_status_updates_request(persona):
    optout.prepare_one("spokeo", persona)
    assert optout.mark_status("spokeo", "submitted")
    assert optout.load_requests()[0].status == "submitted"


# -- cache killer / report ---------------------------------------------------


def test_purge_generates_letters():
    request = cachekiller.purge("https://pastebin.com/raw/DEMO1234", live_removed=True)
    assert "search.google.com" in request.google_url
    letter = Path(request.letter_path).read_text()
    assert "https://pastebin.com/raw/DEMO1234" in letter
    assert "already been taken down" in letter
    assert Path(request.letter_html_path).read_text().startswith("<!doctype html>")


def test_report_summarises_state(persona):
    scanner.Scanner(persona, client=DemoClient()).scan_and_store()
    optout.prepare_one("mylife", persona)
    cachekiller.purge("https://pastebin.com/raw/DEMO1234")

    summary = report.build_summary()
    assert summary["total_exposures"] > 0
    assert summary["optout_requests"] == 1
    assert summary["purge_requests"] == 1
    assert summary["timeline"] == sorted(summary["timeline"], key=lambda item: item["time"])

    html_path = report.generate("html")
    assert "ScrubPup exposure report" in html_path.read_text()
    json_path = report.generate("json")
    assert json.loads(json_path.read_text())["total_exposures"] == summary["total_exposures"]
    with pytest.raises(ValueError):
        report.generate("csv")
