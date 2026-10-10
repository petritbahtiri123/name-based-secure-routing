from __future__ import annotations

import argparse
import sys
from pathlib import Path

from federation_v01_vectors.package import build_package, verify_package, write_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic Federation v0.1 conformance vectors")
    parser.add_argument("--check", action="store_true", help="verify without writing")
    parser.add_argument("path", type=Path)
    parser.add_argument("--version", choices=("federation-v0.1-development-v1", "federation-v0.1-development-v2"), default="federation-v0.1-development-v1")
    args = parser.parse_args()
    if args.check:
        errors = verify_package(args.path, version=args.version)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print(f"verified {len(build_package(version=args.version))} Federation v0.1 package files")
        return 0
    write_package(args.path, version=args.version)
    print(f"generated {len(build_package(version=args.version))} Federation v0.1 package files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
