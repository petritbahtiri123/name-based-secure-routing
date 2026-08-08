from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wp8_f75_vectors.package import F75VectorError, build_package, verify_package, write_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or verify the additive WP8 F75 vector package")
    parser.add_argument("--check", action="store_true", help="verify the package without writing files")
    parser.add_argument("output", nargs="?", default="vectors/wp8-f75-route-open")
    args = parser.parse_args()
    root = Path(args.output)
    try:
        if args.check:
            expected = build_package()
            result = verify_package(root)
            actual = {path: (root / path).read_bytes() for path in expected}
            if actual != expected:
                raise F75VectorError("F75 generated artifacts drifted")
        else:
            write_package(root, build_package())
            result = verify_package(root)
    except (F75VectorError, OSError) as exc:
        print(f"F75 package error: {exc}", file=sys.stderr)
        return 1
    print(
        "F75 package verified: "
        f"{result['artifacts']} artifacts, "
        f"{result['transcript_mutations']} transcript mutations, "
        f"{result['body_mutations']} body mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
