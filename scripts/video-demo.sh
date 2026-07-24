#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NO_PAUSE=0
REHEARSAL=0
for arg in "$@"; do
  case "$arg" in
    --no-pause) NO_PAUSE=1 ;;
    --rehearsal) REHEARSAL=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

pause_demo() {
  [[ "$NO_PAUSE" -eq 1 ]] && return
  [[ "$REHEARSAL" -eq 1 ]] && sleep 2 || sleep 1
}

command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
cd "$ROOT"
"$ROOT/scripts/bootstrap.sh"
NBSR_TICKET_TTL_SECONDS=2 docker compose up -d --no-build --wait --wait-timeout 120 --force-recreate

required=(control-plane opa gateway ticket-verifier payments-service)
running="$(docker compose ps --status running --services)"
for service in "${required[@]}"; do
  grep -qx "$service" <<<"$running" || { echo "Service not running: $service" >&2; exit 1; }
done

clear
echo "NAME-BASED SECURE ROUTING — LIVE VALIDATED DEMO"
echo "Real Docker Compose services. No mocked results."
echo
echo "Preflight: 5/5 required services running and ready."
pause_demo

set +e
output="$(python "$ROOT/scripts/demo.py" 2>&1)"
status=$?
set -e
mapfile -t rows < <(grep -E '^(Authorized request|Unauthorized identity|Unknown service|Missing ticket|Tampered ticket|Method/path escalation|Direct backend access|Expired ticket)[[:space:]]+(ALLOW|DENY)[[:space:]]+(ALLOW|DENY)[[:space:]]+(PASS|FAIL)$' <<<"$output")
[[ "${#rows[@]}" -eq 8 ]] || { printf '%s\n' "$output"; echo "Could not parse eight results." >&2; exit 1; }

for i in "${!rows[@]}"; do
  read -r name expected actual result <<<"$(sed -E 's/^(.*[^ ]) +((ALLOW|DENY)) +((ALLOW|DENY)) +(PASS|FAIL)$/\1|\2|\4|\6/' <<<"${rows[$i]}" | tr '|' ' ')"
  printf '\n[%d/8] %s\nExpected: %s\nActual:   %s\nResult:   %s\n' "$((i + 1))" "$name" "$expected" "$actual" "$result"
  pause_demo
done

printf '\nFINAL SUMMARY\n%s\n' "$output"
[[ "$status" -eq 0 ]] || exit "$status"
