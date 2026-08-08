from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority  # noqa: E402
from scripts.performance.statistics import summarize  # noqa: E402
from scripts.run_performance_validation import (  # noqa: E402
    build_release,
    direct_samples,
    environment,
    go_lifecycle_samples,
    nbsr_samples,
    normalize,
    rust_lifecycle_samples,
)


SCENARIOS = {
    "direct-cold",
    "direct-warm",
    "nbsr-cold",
    "nbsr-warm-new-service",
    "nbsr-warm-existing-service",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", choices=["direct-quic", "rust-rust", "go-rust"], required=True)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--run-ordinal", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args()
    if args.scenario.startswith("direct-") != (args.path == "direct-quic"):
        raise SystemExit("scenario/path mismatch")
    if args.formal:
        minimum = 2_000 if args.scenario.endswith("cold") else 100_000
        if args.samples < minimum:
            raise SystemExit(f"formal {args.scenario} requires at least {minimum} samples")
    env_record = environment()
    if env_record["dirty_tree"]:
        raise SystemExit("formal benchmark requires a clean working tree")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "environment.json").write_text(json.dumps(env_record, indent=2) + "\n", encoding="utf-8")
    environment_digest = hashlib.sha256(
        json.dumps(env_record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run_id = f"{args.path}-{args.scenario}-{args.payload_bytes}-idle-r{args.run_ordinal}"
    with tempfile.TemporaryDirectory(prefix="nbsr-headline-cell-") as temporary:
        temp = Path(temporary)
        authority = temp / "authority"
        write_loopback_authority(authority)
        target = Path(os.environ.get("NBSR_PERF_CARGO_TARGET", r"C:\codex-target\nbsr-perf-formal"))
        binaries = build_release(target)
        if args.path == "direct-quic":
            raw = direct_samples(
                binaries["direct"], authority, args.samples, args.payload_bytes,
                "cold" if args.scenario == "direct-cold" else "warm", temp,
            )
        elif args.scenario == "nbsr-warm-existing-service":
            raw = nbsr_samples(args.path, binaries, authority, args.samples, args.payload_bytes, temp)
        else:
            lifecycle = rust_lifecycle_samples if args.path == "rust-rust" else go_lifecycle_samples
            raw = lifecycle(
                binaries, authority, args.samples, args.payload_bytes, args.scenario, temp,
                services_per_session=32,
            )
    if len(raw) != args.samples or not all(record.get("success", True) for record in raw):
        raise RuntimeError(f"formal headline sample failure: expected {args.samples}, observed {len(raw)}")
    durations = {name: [] for name in ("request_latency_ns", "total_scenario_ns")}
    with gzip.open(output / "raw.ndjson.gz", "wt", encoding="utf-8", newline="\n") as handle:
        for index, record in enumerate(raw):
            normalized = normalize(
                record,
                sample_id=index,
                path=args.path,
                scenario=args.scenario,
                payload=args.payload_bytes,
                environment_digest=environment_digest,
                repository_sha=env_record["repository_sha"],
                run_id=run_id,
            )
            normalized["run_ordinal"] = args.run_ordinal
            handle.write(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n")
            for name in durations:
                if normalized[name] is not None:
                    durations[name].append(int(normalized[name]))
    summary = {
        "schema": "nbsr-performance-headline-cell-v1",
        "formal": args.formal,
        "run_id": run_id,
        "run_ordinal": args.run_ordinal,
        "path": args.path,
        "scenario": args.scenario,
        "payload_bytes": args.payload_bytes,
        "success": len(raw),
        "failure": 0,
        "request_latency_ns": summarize(durations["request_latency_ns"]),
        "total_scenario_ns": summarize(durations["total_scenario_ns"]),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
