# ScrubPup

A personal data hygiene watchdog. ScrubPup monitors where **your own** personal
information appears in public sources, keeps a record of every exposure, and
prepares the opt-out, takedown and cache-removal requests needed to get it
removed.

No paid APIs, no auth tokens, no SaaS calls: everything comes from public
endpoints (DuckDuckGo HTML, the GitHub public API, Reddit's public JSON, the
archive.org CDX API and paste sites), rate limited to 2 requests/second with
rotating user agents.

## Legal note

> Only use this tool to monitor and protect YOUR OWN personal information.
> Unauthorized use against others may violate computer fraud laws, GDPR,
> CCPA, and other regulations. The authors are not responsible for misuse.

## Install

```bash
git clone <this-repo> scrubpup && cd scrubpup
./install.sh                 # venv + deps + dirs + playwright/chromium
source .venv/bin/activate
scrubpup init                # interactive setup
```

Requires Python 3.10+. To skip the browser install: `WITH_BROWSER=0 ./install.sh`.

Docker:

```bash
docker build -t scrubpup .
docker run --rm -v "$PWD/workspace:/data" scrubpup scan
```

## Try it without exposing your own data

```bash
scrubpup demo
```

Runs the whole pipeline (scan, opt-out draft, cache-removal letter, HTML
report) against a fake persona using canned responses — no network calls — and
writes everything to `demo-workspace/`.

## Configuration

Your identifiers live in `config/protected.yaml`; see
[`config.example.yaml`](config.example.yaml) for every documented field.
After the first load the file is encrypted at rest with `cryptography.fernet`.
The key is stored in `config/.scrubpup.key` (mode 600), or supplied via the
`SCRUBPUP_KEY` environment variable — **without the key the config cannot be
decrypted**, so back it up somewhere safe.

Set `SCRUBPUP_HOME` to relocate the whole workspace (`config/`, `data/`,
`evidence/`, `reports/`, `outbox/`); it defaults to the current directory.

## Usage

```bash
scrubpup init                      # interactive setup
scrubpup config edit               # decrypt, open $EDITOR, re-encrypt
scrubpup config show               # masked view: j***@e******.com
scrubpup scan                      # full scan of every source
scrubpup scan --target email       # only one identifier type
scrubpup scan --since 7d           # show findings from the last 7 days
scrubpup optout --broker spokeo    # prepare one broker opt-out
scrubpup optout --all              # prepare opt-outs for every known broker
scrubpup purge --url URL           # Google/Bing/Wayback removal requests
scrubpup evidence --url URL        # screenshot + HTML + headers as proof
scrubpup watch                     # daemon: re-scan on a schedule
scrubpup report --format html      # html | json | pdf
scrubpup brokers --list            # list supported brokers
scrubpup status                    # current protection status
```

### Scanning

`scrubpup scan` walks every identifier in your config across:

| Source | What it finds |
| --- | --- |
| DuckDuckGo HTML | any public page quoting your identifier |
| GitHub code search | your email/username committed into public repos |
| Reddit public JSON | whether a username is an active account |
| archive.org CDX | archived URLs containing your username |
| Paste sites | pastebin, ghostbin, throwbin, justpaste, rentry hits |
| Data brokers | optional per-broker page grep (`sources.brokers: true`) |

Findings are appended to `data/findings.json` (source, url, type, matched
data, timestamp, screenshot path, removal status) and deduplicated across runs,
so `scan` only reports genuinely new exposures.

Public endpoints throttle aggressively, especially from datacenter/VPN IPs:
unauthenticated GitHub code search returns 403, DuckDuckGo answers 202 with a
challenge page, and Reddit blocks non-browser clients. ScrubPup keeps scanning
and then prints a `sources that did not answer` table, because zero findings
from a blocked source is not the same as being clean. Run scans from a
residential connection for meaningful coverage.

### Opting out

`scrubpup brokers --list` shows the built-in database of 70+ brokers with the
opt-out URL, method, required fields and expected removal time.

ScrubPup **never submits an opt-out on your behalf**. Brokers gate their forms
behind CAPTCHAs and email/SMS confirmation, so silent auto-submission would
mostly produce failures you'd never notice. Instead:

- **email-based brokers** get a filled-in request letter written to `outbox/`,
  citing GDPR Art. 17 / CCPA 1798.105 — review it and send it from your mail
  client.
- **form-based brokers** with `--interactive` open in a real browser
  (Playwright, headed — brokers serve a stripped page to headless Chromium)
  with the fields it recognises pre-filled and a screenshot captured; you solve
  the CAPTCHA and click submit. Prefills are verified after page hydration and
  refilled if the page wipes them, and the reported field list only names
  fields whose value actually stuck.

Every request is tracked in `data/optout_requests.json` with its status
(`prepared` / `submitted` / `confirmed` / `failed`).

### Cache removal and evidence

`scrubpup purge --url URL` emits the deep link to Google's outdated-content
tool, the Bing content-removal tool and the archive.org exclusion page, plus a
signable removal letter as text and printable HTML (print to PDF).

`scrubpup evidence --url URL` stores a full-page screenshot, the raw HTML,
response headers and status under `evidence/YYYY-MM-DD/{domain}/` — useful as
proof when a host asks you to substantiate a takedown.

### Notifications

Configure any combination of terminal, SMTP email, Discord webhook and Slack
webhook under `settings.notifier`. Alerts fire on new exposures, prepared
opt-outs and completed scheduled scans. SMTP passwords are read from the
environment variable named by `password_env`, never from the config file.

### Daemon mode

`scrubpup watch` uses APScheduler to re-scan every `scan_interval_hours` and
sends a summary report at 08:00 UTC daily. Activity is logged to
`data/logs/`.

## Privacy of ScrubPup's own output

Identifiers are masked wherever they are displayed or logged
(`j***@e******.com`, `+1***-***-4567`). Full values only ever live inside the
encrypted config and the artifacts you explicitly generate. `.gitignore`
excludes the config, key, findings, evidence, reports and outbox.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

Playwright is optional (`pip install -e ".[browser]"`): without it, evidence
capture still records HTML, headers and status, and simply skips screenshots.
