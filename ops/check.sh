#!/bin/sh
# The checks to run before a merge, here on this machine (the repo runs no GitHub workflows).
set -e
cd "$(dirname "$0")/.."
uv run ruff check .
uv run pytest -q
cd site
pnpm test
pnpm exec tsc --noEmit
