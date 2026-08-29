"""ScrubPup CLI - a personal data hygiene watchdog.

Use it only to monitor and protect your own personal information.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from scrubpup import __version__, cachekiller
from scrubpup import evidence as evidence_mod
from scrubpup import optout as optout_mod
from scrubpup import report as report_mod
from scrubpup.brokers import all_brokers, find_brokers
from scrubpup.config import (
    Config,
    ConfigError,
    Identity,
    config_path,
    decrypt_to_plaintext,
    is_encrypted,
    load_config,
    save_config,
)
from scrubpup.daemon import watch as watch_daemon
from scrubpup.demo import PERSONA, DemoClient
from scrubpup.demo import workspace as demo_workspace
from scrubpup.notifier import Notifier
from scrubpup.scanner import Scanner, filter_since, load_findings
from scrubpup.utils import get_logger, parse_duration, redact

console = Console()
log = get_logger("scrubpup.cli")


def _load() -> Config:
    try:
        return load_config()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _prompt_list(label: str) -> list[str]:
    raw = click.prompt(f"{label} (comma separated)", default="", show_default=False)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _findings_table(findings, title: str) -> Table:
    table = Table(title=title, show_lines=False)
    table.add_column("source", style="cyan")
    table.add_column("type", style="magenta")
    table.add_column("url", overflow="fold")
    table.add_column("status", style="yellow")
    for finding in findings:
        table.add_row(finding.source, finding.type, finding.url, finding.status)
    return table


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="scrubpup")
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """ScrubPup - monitor and remove your own personal data from public sources."""
    get_logger("scrubpup", verbose=verbose)


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite an existing configuration.")
def init(force: bool) -> None:
    """Interactively create config/protected.yaml (encrypted at rest)."""
    path = config_path()
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists - use --force to overwrite")
    console.print(Panel.fit("Only enter identifiers that belong to you.", title="ScrubPup setup"))
    identity = Identity(
        name=click.prompt("Full name", default=""),
        emails=_prompt_list("Email addresses"),
        phones=_prompt_list("Phone numbers"),
        usernames=_prompt_list("Usernames"),
        addresses=_prompt_list("Postal addresses"),
        social_handles=_prompt_list("Social handles"),
    )
    config = Config(identity=identity)
    config.settings.scan_interval_hours = click.prompt("Re-scan interval (hours)", default=24, type=int)
    config.settings.notifier = {"terminal": True}
    saved = save_config(config)
    console.print(f"[green]Wrote encrypted config to {saved}[/green]")
    console.print("Keep config/.scrubpup.key safe - without it the config cannot be read.")


@cli.group()
def config() -> None:
    """Inspect or edit the protected configuration."""


@config.command("edit")
def config_edit() -> None:
    """Decrypt, open in $EDITOR, then re-encrypt the config."""
    path = config_path()
    if not path.exists():
        raise click.ClickException("no config yet - run `scrubpup init`")
    try:
        decrypt_to_plaintext(path)
        subprocess.call([os.environ.get("EDITOR", "nano"), str(path)])
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        cfg = load_config(path, encrypt_after=False)
        save_config(cfg, path)
    console.print("[green]Config saved and re-encrypted.[/green]")


@config.command("show")
def config_show() -> None:
    """Show the configuration with identifiers masked."""
    cfg = _load()
    table = Table(title="Protected identity (masked)")
    table.add_column("type", style="cyan")
    table.add_column("value")
    for kind, value in cfg.identity.identifiers():
        table.add_row(kind, value if kind in ("name", "address") else redact(value))
    console.print(table)
    console.print(
        f"scan interval: {cfg.settings.scan_interval_hours}h | "
        f"rate limit: {cfg.settings.rate_limit_per_sec}/s | "
        f"encrypted: {is_encrypted(config_path())}"
    )


@cli.command()
@click.option(
    "--target",
    type=click.Choice(["email", "phone", "username", "address", "name"]),
    help="Only scan one identifier type.",
)
@click.option("--since", help="Show only findings newer than this age, e.g. 7d.")
@click.option("--no-notify", is_flag=True, help="Do not send notifications for new exposures.")
def scan(target: str | None, since: str | None, no_notify: bool) -> None:
    """Scan public sources for your identifiers."""
    cfg = _load()
    scanner = Scanner(cfg)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        progress.add_task("scanning public sources...", total=None)
        all_findings, fresh = scanner.scan_and_store(target)

    shown = fresh
    if since:
        try:
            shown = filter_since(all_findings, parse_duration(since))
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--since") from exc

    console.print(_findings_table(shown, f"{len(shown)} finding(s)"))
    console.print(f"total tracked exposures: {len(all_findings)} | new this run: {len(fresh)}")
    if fresh and not no_notify:
        Notifier(cfg.settings.notifier).notify(
            "new_exposure",
            f"{len(fresh)} new exposure(s)",
            "\n".join(f"- [{f.source}] {f.url}" for f in fresh[:20]),
        )


@cli.command()
@click.option("--broker", help="Broker key or name, e.g. spokeo.")
@click.option("--all", "all_brokers_flag", is_flag=True, help="Prepare opt-outs for every known broker.")
@click.option("--email", default="", help="Contact email to use for this request.")
@click.option("--profile-url", default="", help="URL of the listing to remove.")
@click.option("--interactive", is_flag=True, help="Open form-based opt-outs in a browser with fields pre-filled.")
def optout(broker: str | None, all_brokers_flag: bool, email: str, profile_url: str, interactive: bool) -> None:
    """Prepare data-broker opt-out requests."""
    cfg = _load()
    if not broker and not all_brokers_flag:
        raise click.UsageError("pass --broker NAME or --all")

    if all_brokers_flag:
        requests_made = optout_mod.prepare_all(cfg, email=email, interactive=interactive)
    else:
        try:
            requests_made = [
                optout_mod.prepare_one(broker, cfg, email=email, profile_url=profile_url, interactive=interactive)
            ]
        except KeyError as exc:
            suggestions = ", ".join(b.key for b in find_brokers(broker or "")) or "none"
            raise click.ClickException(f"{exc}. Similar keys: {suggestions}") from exc

    table = Table(title=f"{len(requests_made)} opt-out request(s) prepared")
    table.add_column("broker", style="cyan")
    table.add_column("method")
    table.add_column("next step", overflow="fold")
    for request in requests_made:
        next_step = request.artifact_path or request.opt_out_url
        table.add_row(request.broker_name, request.method, next_step)
    console.print(table)
    console.print("[yellow]Review each artifact before sending; nothing was submitted for you.[/yellow]")
    Notifier(cfg.settings.notifier).notify(
        "optout_completed", f"{len(requests_made)} opt-out request(s) prepared", "See outbox/ for details."
    )


@cli.command()
@click.option("--url", required=True, help="URL whose cached/archived copies should be removed.")
@click.option("--live-removed", is_flag=True, help="The live page is already gone.")
def purge(url: str, live_removed: bool) -> None:
    """Prepare Google / Bing / Wayback removal requests for a URL."""
    request = cachekiller.purge(url, live_removed=live_removed)
    table = Table(title="Cache removal targets")
    table.add_column("target", style="cyan")
    table.add_column("where", overflow="fold")
    table.add_row("Google outdated content", request.google_url)
    table.add_row("Bing content removal", request.bing_url)
    table.add_row("Wayback exclusion", request.wayback_url)
    table.add_row("Signable letter", request.letter_path)
    table.add_row("Printable letter", request.letter_html_path)
    console.print(table)


@cli.command()
@click.option("--url", required=True, help="URL to capture as proof of exposure.")
@click.option("--no-screenshot", is_flag=True, help="Skip the Playwright screenshot.")
def evidence(url: str, no_screenshot: bool) -> None:
    """Capture screenshot, HTML and headers as takedown evidence."""
    record = evidence_mod.capture(url, screenshot=not no_screenshot)
    console.print(
        Panel.fit(
            f"status: {record.status}\nhtml: {record.html_path or '-'}\n"
            f"screenshot: {record.screenshot_path or '-'}\nheaders: {record.headers_path or '-'}\n"
            f"note: {record.note or '-'}",
            title=f"evidence -> {record.directory}",
        )
    )


@cli.command()
@click.option("--interval", type=int, help="Override the re-scan interval in hours.")
@click.option("--no-initial-scan", is_flag=True, help="Wait for the first interval before scanning.")
def watch(interval: int | None, no_initial_scan: bool) -> None:
    """Run continuously, re-scanning on a schedule."""
    cfg = _load()
    console.print("[green]ScrubPup watch mode started (Ctrl+C to stop).[/green]")
    watch_daemon(cfg, interval_hours=interval, run_now=not no_initial_scan)


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["html", "json", "pdf"]), default="html")
def report(fmt: str) -> None:
    """Generate an exposure report."""
    path = report_mod.generate(fmt)
    console.print(f"[green]Report written to {path}[/green]")
    if fmt == "pdf":
        console.print("Open it in a browser and print to PDF to finalise.")


@cli.command()
@click.option("--list", "list_all", is_flag=True, help="List every supported broker.")
@click.option("--search", default="", help="Filter brokers by name.")
def brokers(list_all: bool, search: str) -> None:
    """Show the supported data brokers and their opt-out routes."""
    items = find_brokers(search) if search else all_brokers()
    if not list_all and not search:
        console.print(f"{len(items)} brokers supported. Use --list to show them all.")
        return
    table = Table(title=f"{len(items)} broker(s)")
    table.add_column("key", style="cyan")
    table.add_column("name")
    table.add_column("method")
    table.add_column("days", justify="right")
    table.add_column("opt-out URL", overflow="fold")
    for item in items:
        table.add_row(item.key, item.name, item.type, str(item.expected_days_to_removal), item.opt_out_url)
    console.print(table)


@cli.command()
def status() -> None:
    """Show current protection status."""
    findings = load_findings()
    requests_made = optout_mod.load_requests()
    purges = cachekiller.load_purges()
    encrypted = is_encrypted(config_path()) if config_path().exists() else False

    table = Table(title="ScrubPup status")
    table.add_column("metric", style="cyan")
    table.add_column("value")
    table.add_row("config", f"{config_path()} (encrypted: {encrypted})")
    table.add_row("exposures tracked", str(len(findings)))
    table.add_row("pending exposures", str(sum(1 for f in findings if f.status == "pending")))
    table.add_row("opt-out requests", str(len(requests_made)))
    table.add_row("purge requests", str(len(purges)))
    table.add_row("brokers known", str(len(all_brokers())))
    table.add_row("playwright", "installed" if evidence_mod.playwright_available() else "not installed")
    console.print(table)


@cli.command()
@click.option("--root", type=click.Path(path_type=Path), help="Where to build the demo workspace.")
def demo(root: Path | None) -> None:
    """Run an offline end-to-end demo against a fake persona."""
    path = demo_workspace(root)
    scanner = Scanner(PERSONA, client=DemoClient())
    all_findings, fresh = scanner.scan_and_store()
    console.print(_findings_table(all_findings, f"demo scan: {len(all_findings)} finding(s)"))
    prepared = optout_mod.prepare(
        optout_mod.get_broker("mylife"), PERSONA, email=PERSONA.identity.emails[0]
    )
    purge_request = cachekiller.purge("https://pastebin.com/raw/DEMO1234")
    report_path = report_mod.generate("html")
    console.print(
        Panel.fit(
            f"workspace: {path}\nnew findings: {len(fresh)}\n"
            f"opt-out draft: {prepared.artifact_path}\npurge letter: {purge_request.letter_path}\n"
            f"report: {report_path}",
            title="demo complete (no network calls made)",
        )
    )


if __name__ == "__main__":
    cli()
