"""Observer-controlled accept-pump timing; unchanged admission workload."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b4b_v2 as v2
from scripts.run_b4b_task4h import observer_gate
from scripts.run_b4b_task4k import checksums
from scripts.run_b4b_task4l import run_one


@contextmanager
def profile_environment(path):
    key = "NBSR_PERF_ACCEPT_PUMP_PROFILE"
    previous = os.environ.pop(key, None)
    try:
        if path is not None:
            os.environ[key] = str(path)
        yield
    finally:
        os.environ.pop(key, None)
        if previous is not None:
            os.environ[key] = previous


def execute(output, target):
    output.mkdir(exist_ok=False)
    built = v2.build(target)
    (output / "binaries").mkdir()
    binaries = {}
    for key, path in built.items():
        binaries[key] = output / "binaries" / path.name
        shutil.copy2(path, binaries[key])
    metadata = v2.host_environment()
    hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in binaries.items()}
    metadata.update(classification="DIAGNOSTIC", binary_sha256=hashes, repeats=5,
                    rates=[200, 250], clients=512, source_shards=2,
                    duration_seconds=30, warmup_seconds=2,
                    timer_wait_scope="select wall time includes polling and scheduler delay; not pure OS timer latency")
    v2.write_json(output / "environment.json", metadata)
    (output / "source.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"], cwd=v2.ROOT))
    for name in ("scripts/run_b4b_task4n.py", "scripts/run_b4b_task4l.py",
                 "crates/nbsr-transport/src/bin/benchmark_support/accept_pump_profile.rs",
                 "crates/nbsr-transport/src/bin/wp8_interop_server.rs"):
        dest = output / "source" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v2.ROOT / name, dest)
    records = {str(rate): {variant: [] for variant in ("off", "on")} for rate in (200, 250)}
    try:
        for repeat in range(1, 6):
            for rate in ((200, 250) if repeat % 2 else (250, 200)):
                for variant in (("off", "on") if repeat % 2 else ("on", "off")):
                    profile = output / f"pump-{rate}-r{repeat}.json" if variant == "on" else None
                    print(f"accept-pump-profile={variant}", flush=True)
                    with profile_environment(profile):
                        row = run_one(output / variant, binaries, rate, repeat, "none")
                    records[str(rate)][variant].append(row)
                    v2.write_json(output / "analysis.json", {"classification": "DIAGNOSTIC", "records": records})
                    if not row["valid"] or not row["cleanup"]["all_zero"]:
                        raise RuntimeError("invalid/unclean measurement preserved")
                    if profile:
                        pump = json.loads(profile.read_text())
                        if pump["accept_wins"] != 512 or sum(pump["timer_histogram"]) != pump["timer_wins"]:
                            raise ValueError("accept-pump profile conservation failed")
        v2.write_json(output / "observer-comparison.json", {
            rate: observer_gate(modes["off"], modes["on"]) for rate, modes in records.items()})
        if hashes != {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in binaries.items()}:
            raise ValueError("binary changed during measurement")
    finally:
        checksums(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path(r"C:\NBSR-build\b4b-task4k"))
    args = parser.parse_args()
    execute(args.output, args.target)
