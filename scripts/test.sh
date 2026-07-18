#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python -m pytest -q
command -v opa >/dev/null && opa test policy -v || true
command -v docker >/dev/null && docker compose config --quiet || true
