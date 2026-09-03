from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_b4b_mixed_connections as b4b


ROOT = Path(__file__).resolve().parents[1]
CLIENTS = (64, 128)
REPEATS = 1


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run(output: Path, warmup_seconds: float, duration_seconds: float) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b4b-task4c-profile"))
    binaries = b4b.build(target)
    records: list[dict[str, object]] = []
    timeline: list[dict[str, object]] = []
    for clients in CLIENTS:
        started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        started_ns = time.time_ns()
        record = b4b.run_cell(
            clients,
            1,
            1,
            binaries,
            raw,
            duration=duration_seconds,
            warmup=warmup_seconds,
            planned_clients=list(CLIENTS),
        )
        ended_ns = time.time_ns()
        timeline.append(
            {
                "clients": clients,
                "started_utc": started_utc,
                "started_unix_ns": started_ns,
                "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "ended_unix_ns": ended_ns,
            }
        )
        records.append(record)
        write_json(raw / f"clients-{clients}.json", record)

    manifest = {
        "schema": "nbsr-b4b-task4c-profile-workload-v1",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, *sys.argv],
        "clients": list(CLIENTS),
        "repeats": REPEATS,
        "warmup_seconds": warmup_seconds,
        "duration_seconds": duration_seconds,
        "timeline": timeline,
        "records": records,
        "binaries": {
            name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in binaries.items()
        },
    }
    write_json(output / "manifest.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=2.0)
    parser.add_argument("--duration-seconds", type=float, default=8.0)
    args = parser.parse_args()
    run(args.output, args.warmup_seconds, args.duration_seconds)


if __name__ == "__main__":
    main()
