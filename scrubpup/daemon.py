"""Background watch mode: periodic re-scans and a daily summary report."""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import Config
from .notifier import Notifier
from .report import build_summary, generate
from .scanner import Scanner
from .utils import get_logger, log_dir

log = get_logger("scrubpup.daemon")


def _wire_apscheduler_logs() -> None:
    handler = logging.FileHandler(log_dir() / "daemon.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s"))
    logging.getLogger("apscheduler").addHandler(handler)
    logging.getLogger("scrubpup").addHandler(handler)


def run_scan_job(config: Config) -> None:
    notifier = Notifier(config.settings.notifier)
    _, fresh = Scanner(config).scan_and_store()
    if fresh:
        lines = "\n".join(f"- [{f.source}] {f.url}" for f in fresh[:20])
        notifier.notify("new_exposure", f"{len(fresh)} new exposure(s) found", lines)
    notifier.notify("scan_completed", "Scheduled scan finished", f"{len(fresh)} new finding(s).")


def run_daily_report(config: Config) -> None:
    path = generate("html")
    summary = build_summary()
    Notifier(config.settings.notifier).notify(
        "scan_completed",
        "Daily ScrubPup summary",
        f"{summary['total_exposures']} exposures tracked, "
        f"{summary['optout_requests']} opt-out requests. Report: {path}",
    )


def watch(config: Config, *, interval_hours: int | None = None, run_now: bool = True) -> None:
    """Run forever, re-scanning every N hours and reporting daily."""
    hours = interval_hours or config.settings.scan_interval_hours
    _wire_apscheduler_logs()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_scan_job, IntervalTrigger(hours=hours), args=[config], id="scan")
    scheduler.add_job(run_daily_report, CronTrigger(hour=8, minute=0), args=[config], id="daily-report")
    log.info("watch mode: scanning every %dh, daily report at 08:00 UTC", hours)
    if run_now:
        run_scan_job(config)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("watch mode stopped")
