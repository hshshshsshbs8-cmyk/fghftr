#!/usr/bin/env bash
# Set up ScrubPup: virtualenv, dependencies, directories and (optionally) Playwright.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
WITH_BROWSER="${WITH_BROWSER:-1}"

echo "==> checking python"
"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 10):
    sys.exit(f"python 3.10+ required, found {sys.version.split()[0]}")
print(f"using python {sys.version.split()[0]}")
PY

echo "==> creating virtualenv at $VENV"
"$PYTHON" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> installing dependencies"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
pip install -e .

if [ "$WITH_BROWSER" = "1" ]; then
  echo "==> installing playwright + chromium (screenshots and form pre-fill)"
  pip install "playwright>=1.44"
  playwright install chromium || echo "!! playwright browser download failed - screenshots will be skipped"
fi

echo "==> creating directories"
mkdir -p config data/logs evidence reports outbox

if [ ! -f config/protected.yaml ]; then
  cp config.example.yaml config/protected.yaml
  chmod 600 config/protected.yaml
  echo "==> copied config.example.yaml to config/protected.yaml - edit it, or run 'scrubpup init'"
fi

cat <<'EOF'

ScrubPup installed. Next steps:

  source .venv/bin/activate
  scrubpup init            # interactive setup (encrypts config/protected.yaml)
  scrubpup demo            # offline end-to-end demo, no network calls
  scrubpup scan            # scan public sources for your identifiers

Keep config/.scrubpup.key private: without it the config cannot be decrypted.
EOF
