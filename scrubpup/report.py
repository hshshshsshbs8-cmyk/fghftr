"""Generate HTML / JSON reports from findings and opt-out state."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import __version__
from .cachekiller import load_purges
from .optout import load_requests
from .scanner import load_findings
from .utils import get_logger, reports_dir, utcnow

log = get_logger("scrubpup.report")


def build_summary() -> dict:
    findings = load_findings()
    optouts = load_requests()
    purges = load_purges()
    by_source = Counter(f.source for f in findings)
    by_status = Counter(f.status for f in findings)
    timeline = sorted(
        [
            *({"time": f.timestamp, "action": f"exposure found ({f.source})", "url": f.url} for f in findings),
            *({"time": o.timestamp, "action": f"opt-out {o.status} ({o.broker_name})", "url": o.opt_out_url} for o in optouts),
            *({"time": p.timestamp, "action": f"purge {p.status}", "url": p.url} for p in purges),
        ],
        key=lambda item: item["time"],
    )
    return {
        "generated_at": utcnow(),
        "version": __version__,
        "total_exposures": len(findings),
        "by_source": dict(by_source),
        "removal_status": dict(by_status),
        "optout_requests": len(optouts),
        "purge_requests": len(purges),
        "urls": sorted({f.url for f in findings}),
        "timeline": timeline,
        "findings": [
            {"source": f.source, "url": f.url, "type": f.type, "status": f.status, "time": f.timestamp}
            for f in findings
        ],
        "optouts": [
            {"broker": o.broker_name, "method": o.method, "status": o.status, "time": o.timestamp}
            for o in optouts
        ],
    }


def _esc(value: str) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(summary: dict) -> str:
    def rows(items, cols):
        out = []
        for item in items:
            cells = "".join(f"<td>{_esc(item.get(c, ''))}</td>" for c in cols)
            out.append(f"<tr>{cells}</tr>")
        return "\n".join(out) or "<tr><td colspan='9'>none</td></tr>"

    source_rows = "\n".join(
        f"<tr><td>{_esc(k)}</td><td>{v}</td></tr>" for k, v in sorted(summary["by_source"].items())
    ) or "<tr><td colspan='2'>none</td></tr>"
    status_rows = "\n".join(
        f"<tr><td>{_esc(k)}</td><td>{v}</td></tr>" for k, v in sorted(summary["removal_status"].items())
    ) or "<tr><td colspan='2'>none</td></tr>"
    url_items = "\n".join(f"<li><a href='{_esc(u)}'>{_esc(u)}</a></li>" for u in summary["urls"]) or "<li>none</li>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>ScrubPup report</title>
<style>
 body {{ font: 14px/1.5 -apple-system, Segoe UI, sans-serif; max-width: 60em; margin: 2em auto; color: #222; }}
 h1 {{ color: #2a6f4e; }} table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
 th {{ background: #f4f7f5; }} .cards {{ display: flex; gap: 1em; }}
 .card {{ flex: 1; background: #f4f7f5; border-radius: 8px; padding: 1em; text-align: center; }}
 .card b {{ font-size: 2em; display: block; }}
</style></head><body>
<h1>ScrubPup exposure report</h1>
<p>Generated {_esc(summary['generated_at'])} (v{_esc(summary['version'])})</p>
<div class="cards">
 <div class="card"><b>{summary['total_exposures']}</b>exposures found</div>
 <div class="card"><b>{summary['optout_requests']}</b>opt-out requests</div>
 <div class="card"><b>{summary['purge_requests']}</b>purge requests</div>
</div>
<h2>Per-source breakdown</h2>
<table><tr><th>Source</th><th>Findings</th></tr>{source_rows}</table>
<h2>Removal status</h2>
<table><tr><th>Status</th><th>Count</th></tr>{status_rows}</table>
<h2>Opt-out requests</h2>
<table><tr><th>Broker</th><th>Method</th><th>Status</th><th>Time</th></tr>
{rows(summary['optouts'], ('broker', 'method', 'status', 'time'))}</table>
<h2>Timeline</h2>
<table><tr><th>Time</th><th>Action</th><th>URL</th></tr>
{rows(summary['timeline'], ('time', 'action', 'url'))}</table>
<h2>All URLs where data was found</h2>
<ul>{url_items}</ul>
</body></html>
"""


def generate(fmt: str = "html", out_dir: Path | None = None) -> Path:
    """Write a report to ``reports/`` and return its path."""
    out_dir = out_dir or reports_dir()
    summary = build_summary()
    stamp = summary["generated_at"].replace(":", "").replace("-", "")
    if fmt == "json":
        path = out_dir / f"report-{stamp}.json"
        path.write_text(json.dumps(summary, indent=2))
    elif fmt in ("html", "pdf"):
        path = out_dir / f"report-{stamp}.html"
        path.write_text(render_html(summary))
        if fmt == "pdf":
            log.info("PDF export: open %s in a browser and print to PDF", path)
    else:
        raise ValueError(f"unsupported format: {fmt}")
    log.info("report written to %s", path)
    return path
