#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:?usage: package-release.sh <commit-or-ref>}"
PYTHON="${PYTHON:-python3}"

if command -v cygpath >/dev/null 2>&1; then
  ROOT="$(cygpath -w "$ROOT")"
fi

if command -v git.exe >/dev/null 2>&1; then
  export NBSR_GIT_EXECUTABLE=git.exe
fi

"$PYTHON" "$ROOT/scripts/package_release.py" --repo-root "$ROOT" "$REF"
