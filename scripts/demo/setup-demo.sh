#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
action=${1:---check}
case "$action" in
  --check) if [ "$#" -gt 0 ]; then shift; fi; mode=check ;;
  --prepare) shift; mode=prepare ;;
  --build) shift; mode=build ;;
  *) echo 'Use --check, --prepare [--allow-downloads], or --build' >&2; exit 2 ;;
esac
exec python3 "$root/tools/demo-lab/demo.py" "$mode" "$@"
