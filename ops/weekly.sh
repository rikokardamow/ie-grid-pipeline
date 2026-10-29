#!/usr/bin/env bash
# The weekly run, by hand (no scheduler is installed): new lists in, report out, the
# page rebuilt from it. Exit code is the job's: 1 only when the run failed.
#   ops/weekly.sh
set -uo pipefail
cd "$(dirname "$0")/.."
uv run python -m iegrid.weekly
status=$?
if [ -d site/node_modules ]; then
  (cd site && pnpm build >/dev/null && echo "site: built site/out") || echo "site: build failed"
fi
exit $status
