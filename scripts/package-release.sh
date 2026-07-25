#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:?usage: package-release.sh <commit-or-ref>}"
PYTHON="${PYTHON:-python3}"

"$PYTHON" "$ROOT/scripts/package_release.py" --repo-root "$ROOT" "$REF"
