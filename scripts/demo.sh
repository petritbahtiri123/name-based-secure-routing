#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/bootstrap.sh"
NBSR_TICKET_TTL_SECONDS=2 docker compose up -d --build --wait --force-recreate
python "$ROOT/scripts/demo.py"
