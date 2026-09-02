from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_max_throughput_v2_stage2 as stage2
from scripts.performance.authority import write_loopback_authority
from scripts.profile_b2_v2 import windows_processor_topology


ROOT = Path(__file__).resolve().parents[1]
GROUPS = (1, 2, 4)
PATHS = ("direct", "nbsr")


def profile_cells() -> list[dict[str, int | str]]:
    return [
        {
            "path": path,
            "payload_bytes": 16384,
            "streams_per_group": 1,
            "outstanding_per_stream": 4,
            "groups": groups,
            "runtime_workers": 1,
        }
        for groups in GROUPS
        for path in PATHS
    ]


def run(output: Path, warmup_seconds: float, duration_seconds: float) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    topology = windows_processor_topology()
    affinity_mask = int(topology["affinity_masks"]["4"]["decimal"])
    if not topology["verified"] or affinity_mask != 0x55:
        raise RuntimeError("verified physical-core mask 0x55 required")

    raw = output / "raw"
    raw.mkdir(parents=True)
    binaries = stage2.p2a.build(Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b2-v2-profile")))
    records = []
    with tempfile.TemporaryDirectory(prefix="nbsr-stage3-") as temporary:
        authority = Path(temporary) / "authority"
        write_loopback_authority(authority)
        for cell in profile_cells():
            record = stage2.run_repeat(
                cell, 1, binaries, authority, warmup_seconds, duration_seconds, raw, affinity_mask
            )
            path = raw / (
                f"{cell['path']}-p16384-s1-o4-g{cell['groups']}-r1.json"
            )
            path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
            records.append(record)

    manifest = {
        "schema": "nbsr-max-throughput-v2-stage3-profile-workload-v1",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": [sys.executable, *sys.argv],
        "warmup_seconds": warmup_seconds,
        "duration_seconds": duration_seconds,
        "processor_topology": topology,
        "process_affinity_mask": hex(affinity_mask),
        "records": records,
        "all_valid": all(record["valid"] for record in records),
        "all_cleanup_pass": all(record["cleanup_pass"] for record in records),
        "errors": sum(int(record["errors"]) for record in records),
        "timeouts": sum(int(record["timeouts"]) for record in records),
        "binaries": {
            name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in binaries.items()
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=2)
    parser.add_argument("--duration-seconds", type=float, default=8)
    args = parser.parse_args()
    run(args.output, args.warmup_seconds, args.duration_seconds)


if __name__ == "__main__":
    main()
