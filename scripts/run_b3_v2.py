"""B3 Rust same-process lifecycle and simultaneous resource scale."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b3_session_lifecycle as b3
from scripts.run_b4b_task4k import checksums


def spec_for(axis, count, repeat):
    spec = dict(name=f"{axis}-{count}-r{repeat}", kind=axis, active_count=count,
                sessions=1, channels=1, streams=1, cycles=1, start_rate=100)
    if axis == "bundles":
        if not 1 <= count <= 1024:
            raise ValueError("logical client bound is 1024")
        spec.update(sessions=count, kind="sessions",
                    resource_scope="one authenticated connection + session + channel + stream per bundle")
    elif axis == "channels":
        if not 1 <= count <= 32:
            raise ValueError("frozen harness authority supports at most 32 services per connection")
        spec.update(channels=count, resource_scope="channels with one stream each; one connection/session")
    elif axis == "streams":
        if count % 8 or not 8 <= count <= 512:
            raise ValueError("stream axis uses eight fixed channels, 1..64 streams each")
        spec.update(channels=8, streams=count // 8,
                    resource_scope="application streams across eight fixed channels; one connection/session")
    elif axis == "cycles":
        if not 1 <= count <= 100:
            raise ValueError("bounded cycle count required")
        spec.update(cycles=count, streams=64, active_count=64, cycle_mode="same-process",
                    resource_scope="same source/destination processes; one session/channel and 64 streams per cycle")
    else:
        raise ValueError("unknown resource axis")
    return spec


def execute(args):
    specs = [spec_for(args.axis, count, repeat) for count in args.counts for repeat in range(1, args.repeats + 1)]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "binaries").mkdir()
    binaries = {}
    for role, name in (("rust", "perf_rust_source.exe"), ("server", "wp8_interop_server.exe")):
        retained = args.output / "binaries" / name
        shutil.copy2(args.target / "release" / name, retained)
        binaries[role] = retained
    metadata = {"schema": "nbsr-b3-v2-raw-v1", "classification": "DIAGNOSTIC" if args.repeats < 3 else "MEASURED_PENDING_ANALYSIS",
                "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "binary_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in binaries.items()},
                "workloads": specs, "scope": "Windows loopback; Rust to Rust; no server-class claim",
                "source_processes": 1, "source_runtime_shards": "2 for simultaneous bundles; 1 for sequential cycles",
                "acceptance_scope": "B3-only single armed accept, concurrent held sessions; not the B4 admission-capacity workload",
                "memory_scope": "private bytes/working set/handles/threads and ownership, not allocator heap attribution",
                "live_resource_proof": "all named .active markers observed before active sampling and before any release"}
    b3.write_json(args.output / "environment.json", metadata)
    (args.output / "source.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"]))
    for source in ("scripts/run_b3_v2.py", "scripts/run_b3_session_lifecycle.py",
                   "crates/nbsr-transport/src/bin/perf_rust_source.rs",
                   "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
                   "crates/nbsr-transport/src/bin/b3_support/mod.rs"):
        dest = args.output / "source" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    records = []
    try:
        for spec in specs:
            print(spec["name"], flush=True)
            row = b3.run_cell("rust-rust", spec, binaries, args.output,
                              idle_seconds=2, active_seconds=2, cooldown_seconds=2, cadence=0.5)
            records.append(row)
            b3.write_json(args.output / "records.json", records)
            if not row["cleanup"]["all_zero"]:
                raise RuntimeError("nonzero ownership; preserve and investigate")
    finally:
        checksums(args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path(r"C:\NBSR-build\b4b-task4k"))
    parser.add_argument("--axis", choices=("bundles", "channels", "streams", "cycles"), required=True)
    parser.add_argument("--counts", type=int, nargs="+", required=True)
    parser.add_argument("--repeats", type=int, choices=(1, 3, 5), default=5)
    args = parser.parse_args()
    try:
        execute(args)
    except Exception as error:
        print(f"B3_FAILED: {type(error).__name__}; retained details under {args.output}", file=sys.stderr)
        sys.exit(1)
