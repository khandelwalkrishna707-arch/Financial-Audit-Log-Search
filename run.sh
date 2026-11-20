#!/usr/bin/env bash
# One command to run Audit Log Search locally:
#   ./run.sh            set up (first time only), then open the dashboard
#   ./run.sh 8080       same, on another port
# Everything stays on this computer: the server only listens on 127.0.0.1.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-5000}"
DB="${AUDIT_SEARCH_DB:-audit.db}"

if [ ! -x .venv/bin/audit-search ]; then
  echo "First run: creating .venv and installing (needs Python 3.10+)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[web]"
fi

if [ ! -f "$DB" ]; then
  echo "No database yet: loading the synthetic sample data..."
  for f in data/samples/*.csv data/samples/*.json data/samples/*.jsonl; do
    [ -f "$f" ] && .venv/bin/audit-search import --file "$f" --db "$DB" | head -1
  done
fi

exec .venv/bin/audit-search web --db "$DB" --port "$PORT" --open
