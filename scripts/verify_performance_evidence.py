from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    root = parser.parse_args().evidence.resolve()
    checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"checksums.json", "manifest.json"}
    }
    if actual != set(checksums):
        raise SystemExit(f"evidence inventory mismatch missing={set(checksums) - actual} extra={actual - set(checksums)}")
    for name, expected in checksums.items():
        observed = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit(f"evidence digest mismatch: {name}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["files"] != sorted(checksums):
        raise SystemExit("manifest inventory differs from checksums")
    raw_count = 0
    for path in (root / "raw").glob("*.ndjson"):
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
            raw_count += 1
    print(f"NBSR performance evidence: PASS ({len(checksums)} files, {raw_count} raw samples)")


if __name__ == "__main__":
    main()
