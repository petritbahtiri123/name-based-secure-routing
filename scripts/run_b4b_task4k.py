from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import run_b4b_v2 as v2
from scripts.run_b4b_task4i import ownership_high_water, summarize


RATES = (125, 150, 200, 250, 300, 400)
SHARDS = (1, 2)
CLIENTS = 512


def classify_boundary_movement(one: list[dict], two: list[dict]) -> dict:
    stable_one = max((cell["offered_rate"] for cell in one if cell["status"] == "STABLE"), default=0)
    stable_two = max((cell["offered_rate"] for cell in two if cell["status"] == "STABLE"), default=0)
    first_saturated_one = min((cell["offered_rate"] for cell in one if cell["status"] == "SATURATED"), default=None)
    first_saturated_two = min((cell["offered_rate"] for cell in two if cell["status"] == "SATURATED"), default=None)
    moved = stable_two > stable_one or (
        first_saturated_one is not None and (first_saturated_two is None or first_saturated_two > first_saturated_one)
    )
    return {
        "classification": "PASS" if moved else "FAIL",
        "one_shard_highest_stable": stable_one,
        "two_shard_highest_stable": stable_two,
        "one_shard_first_saturated": first_saturated_one,
        "two_shard_first_saturated": first_saturated_two,
    }


def checksums(root: Path) -> None:
    lines = []
    for path in sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256"):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def enrich(cell: dict, records: list[dict], directory: Path) -> dict:
    expected_shards = int(records[0]["source_shards"])
    shard_ids = sorted({key for record in records for key in record["source_shard_cpu"]})
    if shard_ids != [str(shard) for shard in range(expected_shards)]:
        raise ValueError("source shard CPU mapping is incomplete")
    if any(not record["source_shard_cpu"].get(str(shard), {}).get("valid") for record in records for shard in range(expected_shards)):
        raise ValueError("source shard CPU sampling is invalid")
    cell["source_shard_effective_cores"] = {
        shard: statistics.median(
            float(record["source_shard_cpu"][shard]["effective_cores"])
            for record in records
            if record["source_shard_cpu"].get(shard, {}).get("valid")
        )
        for shard in shard_ids
    }
    ownership = []
    for path in sorted(directory.glob("*/lifecycle-diagnostics.ndjson")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        ownership.append(ownership_high_water(rows))
    keys = {key for row in ownership for key in row}
    cell["ownership_high_water_median"] = {key: statistics.median(row.get(key, 0) for row in ownership) for key in sorted(keys)}
    return cell


def execute(output: Path, duration: float = 30, warmup: float = 2) -> dict:
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    target = Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b4b-task4k"))
    binaries = v2.build(target)
    environment = v2.host_environment()
    sources = [
        "crates/nbsr-transport/src/bin/benchmark_support/batch_release.rs",
        "crates/nbsr-transport/src/bin/benchmark_support/lifecycle_shards.rs",
        "crates/nbsr-transport/src/bin/perf_rust_source.rs",
        "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
        "scripts/performance/resources.py",
        "scripts/run_b4b_mixed_connections.py",
        "scripts/run_b4b_v2.py",
        "scripts/run_b4b_task4i.py",
        "scripts/run_b4b_task4k.py",
    ]
    for source in sources:
        destination = output / "capture-source" / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v2.ROOT / source, destination)
    environment.update(
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        build="release",
        duration_seconds=duration,
        warmup_seconds=warmup,
        total_clients=CLIENTS,
        offered_rates=list(RATES),
        source_shards=list(SHARDS),
        command=[sys.executable, *sys.argv],
        claim_boundary="two-shard benchmark admission-source scheduler on Windows loopback; not production capacity",
        binary_sha256={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in binaries.items()},
        source_sha256={source: hashlib.sha256((v2.ROOT / source).read_bytes()).hexdigest() for source in sources},
    )
    v2.write_json(output / "environment.json", environment)
    cells_by_shard = {1: [], 2: []}
    invalid = []
    for rate in RATES:
        for shards in SHARDS:
            directory = raw / f"shards-{shards}" / f"rate-{rate}"
            directory.mkdir(parents=True)
            records = []
            target_repeats = 3
            repeat = 1
            while repeat <= target_repeats:
                print(f"rate={rate}/s shards={shards} repeat={repeat}/{target_repeats}", flush=True)
                record = v2.run_measured_cell(
                    CLIENTS,
                    1,
                    repeat,
                    binaries,
                    directory,
                    duration=duration,
                    warmup=warmup,
                    planned_clients=[CLIENTS],
                    release_rate=rate,
                    source_shards=shards,
                    counter_path=directory / f"r{repeat}-host.csv",
                )
                v2.write_json(directory / f"r{repeat}.json", record)
                (records if record["valid"] else invalid).append(record)
                if repeat == 3 and len(records) == 3:
                    target_repeats = v2.required_repeats(records)
                repeat += 1
            if not records:
                continue
            baseline = cells_by_shard[shards][0] if cells_by_shard[shards] else None
            cells_by_shard[shards].append(enrich(summarize(rate, records, baseline), records, directory))
        if all(
            cells_by_shard[shards]
            and cells_by_shard[shards][-1]["status"] == "SATURATED"
            and any(cell["status"] == "STABLE" for cell in cells_by_shard[shards][:-1])
            for shards in SHARDS
        ):
            break
    boundary = classify_boundary_movement(cells_by_shard[1], cells_by_shard[2])
    analysis = {
        "schema": "nbsr-b4b-task4k-analysis-v1",
        **boundary,
        "invalid_runs": len(invalid),
        "cells_by_shard": {str(key): value for key, value in cells_by_shard.items()},
        "claim_boundary": "HARNESS-ONLY comparison; destination and deadlines unchanged",
    }
    if invalid:
        analysis["classification"] = "FAIL"
    v2.write_json(output / "analysis.json", analysis)
    checksums(output)
    return analysis


def analyze_existing(output: Path) -> dict:
    analysis = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    boundary = classify_boundary_movement(analysis["cells_by_shard"]["1"], analysis["cells_by_shard"]["2"])
    analysis.update(boundary)
    v2.write_json(output / "analysis.json", analysis)
    checksums(output)
    return analysis


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=30)
    parser.add_argument("--warmup-seconds", type=float, default=2)
    parser.add_argument("--analyze-existing", action="store_true")
    args = parser.parse_args()
    if args.analyze_existing:
        analyze_existing(args.output)
    else:
        execute(args.output, args.duration_seconds, args.warmup_seconds)
