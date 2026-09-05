"""Interleaved unobserved baseline/candidate comparison with frozen binaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b4b_v2 as v2
from scripts.run_b4b_task4k import checksums
from scripts.run_b4b_task4l import run_one


def verified_binaries(root, expected):
    binaries = {"nbsr": root / "perf_rust_source.exe",
                "server": root / "wp8_interop_server.exe",
                "direct": root / "perf_direct_peer.exe"}
    for key, path in binaries.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[key]:
            raise ValueError(f"binary hash mismatch: {key}")
    return binaries


def execute(baseline, candidate, output):
    output.mkdir(exist_ok=False)
    reference = json.loads((baseline / "reference-environment.json").read_text())
    binaries = {"baseline": verified_binaries(baseline, reference["binary_sha256"])}
    candidate_hashes = {key: hashlib.sha256((candidate / path.name).read_bytes()).hexdigest()
                        for key, path in binaries["baseline"].items()}
    binaries["candidate"] = verified_binaries(candidate, candidate_hashes)
    metadata = v2.host_environment()
    metadata.update(classification="DIAGNOSTIC paired buffer experiment; no stable-capacity claim",
                    baseline_reference=reference, candidate_binary_sha256=candidate_hashes,
                    binaries={k: {n: str(p) for n, p in b.items()} for k, b in binaries.items()},
                    rates=[200, 250], repeats=5, source_shards=2, clients=512,
                    duration_seconds=30, warmup_seconds=2, observer="none")
    v2.write_json(output / "environment.json", metadata)
    (output / "candidate.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"], cwd=v2.ROOT))
    for name in ("scripts/run_b4b_task4m.py", "scripts/run_b4b_task4l.py",
                 "scripts/run_b4b_mixed_connections.py", "scripts/run_b4b_v2.py",
                 "crates/nbsr-transport/src/udp_socket.rs", "crates/nbsr-transport/Cargo.toml",
                 "crates/nbsr-transport/Cargo.lock", "crates/nbsr-transport/src/quinn_adapter.rs"):
        path = output / "source" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v2.ROOT / name, path)
    records = {str(rate): {variant: [] for variant in binaries} for rate in (200, 250)}
    try:
        for repeat in range(1, 6):
            for rate in ((200, 250) if repeat % 2 else (250, 200)):
                for variant in (("baseline", "candidate") if repeat % 2 else ("candidate", "baseline")):
                    print(f"variant={variant}", flush=True)
                    row = run_one(output / variant, binaries[variant], rate, repeat, "none")
                    records[str(rate)][variant].append(row)
                    v2.write_json(output / "analysis.json", {"classification": "DIAGNOSTIC", "records": records})
                    if not row["valid"] or not row["cleanup"]["all_zero"]:
                        raise RuntimeError("invalid/unclean run preserved; stop comparison")
        verified_binaries(baseline, reference["binary_sha256"])
        verified_binaries(candidate, candidate_hashes)
    finally:
        checksums(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    execute(args.baseline, args.candidate, args.output)
