from __future__ import annotations

import argparse
from pathlib import Path

from nbsr.federation.profile import assert_core_baseline_lock_authority, assert_f75_core_overlay


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the original Core lock or approved F75 overlay")
    parser.add_argument("mode", choices=("original", "overlay"))
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    if args.mode == "original":
        assert_core_baseline_lock_authority(root)
        print("Core v0.2 original baseline lock: PASS")
    else:
        assert_f75_core_overlay(root)
        print("F75 additive overlay: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
