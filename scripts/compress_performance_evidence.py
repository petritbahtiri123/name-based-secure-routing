from __future__ import annotations

import argparse
import gzip
import hashlib
from pathlib import Path
import shutil


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    raw = (args.evidence / "raw").resolve()
    archive = args.archive.resolve()
    if archive.exists():
        raise SystemExit(f"archive already exists: {archive}")
    archive.mkdir(parents=True)
    for source in sorted(raw.glob("*.ndjson")):
        original_digest = digest(source)
        archived = archive / source.name
        shutil.move(source, archived)
        compressed = source.with_suffix(source.suffix + ".gz")
        with archived.open("rb") as input_handle, compressed.open("wb") as raw_output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=0) as output_handle:
                shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
        restored = hashlib.sha256()
        with gzip.open(compressed, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                restored.update(chunk)
        if restored.hexdigest() != original_digest:
            raise SystemExit(f"compressed evidence verification failed: {source.name}")
        print(f"{source.name}: archived raw SHA-256 {original_digest}; compressed {compressed.name}")


if __name__ == "__main__":
    main()
