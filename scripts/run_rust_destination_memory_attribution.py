from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.performance.durable_memory import run_durable_memory_child  # noqa: E402


@dataclass(frozen=True)
class AttributionSpec:
    percent: int
    rate: float
    ordinal: int
    warmup_seconds: int
    steady_seconds: int
    drain_seconds: int

    @property
    def run_id(self) -> str:
        return f"rust-rust-p1b-{self.percent}pct-r{self.ordinal}"


@dataclass(frozen=True)
class ObserverSpec:
    rate: float = 843.75
    warmup_seconds: int = 32
    steady_seconds: int = 60
    drain_seconds: int = 5


def attribution_specs() -> list[AttributionSpec]:
    return [
        AttributionSpec(50, 843.75, 1, 60, 600, 20),
        AttributionSpec(75, 1265.625, 1, 60, 900, 20),
        AttributionSpec(75, 1265.625, 2, 60, 900, 20),
        AttributionSpec(75, 1265.625, 3, 60, 900, 20),
    ]


def observer_spec() -> ObserverSpec:
    return ObserverSpec()


def load_command(
    *,
    rate: float,
    warmup_seconds: int,
    steady_seconds: int,
    drain_seconds: int,
    run_id: str,
    finalized: Path,
    durable_root: Path,
    enabled: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts/run_performance_load_cell.py"),
        "--path", "rust-rust",
        "--offered-rate", str(rate),
        "--warmup-seconds", str(warmup_seconds),
        "--steady-seconds", str(steady_seconds),
        "--idle-p99-ns", "404000",
        "--payload-bytes", "1024",
        "--run-id", run_id,
        "--output", str(finalized),
        "--memory",
        "--durable-events",
        "--durable-root", str(durable_root),
        "--validation-profile",
    ]
    if enabled:
        command.extend([
            "--destination-diagnostics",
            "--diagnostic-drain-seconds", str(drain_seconds),
        ])
    return command


def execute_spec(spec: AttributionSpec, output: Path) -> dict[str, object]:
    run_root = output / "runs" / spec.run_id
    return run_durable_memory_child(
        load_command(
            rate=spec.rate,
            warmup_seconds=spec.warmup_seconds,
            steady_seconds=spec.steady_seconds,
            drain_seconds=spec.drain_seconds,
            run_id=spec.run_id,
            finalized=run_root / "finalized-cell",
            durable_root=output,
            enabled=True,
        ),
        output=run_root,
        timeout_seconds=spec.warmup_seconds + spec.steady_seconds + spec.drain_seconds + 180,
        offered_requests=round(spec.rate * (spec.warmup_seconds + spec.steady_seconds)),
        cwd=ROOT,
    )


def summarize_observer(rows: list[dict[str, object]]) -> dict[str, object]:
    enabled = [row for row in rows if row["diagnostics_enabled"]]
    disabled = [row for row in rows if not row["diagnostics_enabled"]]
    throughput_degradation = 100 * (
        1
        - statistics.median(float(row["achieved_rate"]) for row in enabled)
        / statistics.median(float(row["achieved_rate"]) for row in disabled)
    )
    p99_degradation = 100 * (
        statistics.median(float(row["p99_ns"]) for row in enabled)
        / statistics.median(float(row["p99_ns"]) for row in disabled)
        - 1
    )
    additional_errors = sum(int(row["errors"]) for row in enabled) - sum(
        int(row["errors"]) for row in disabled
    )
    return {
        "pairs": rows,
        "median_throughput_degradation_percent": throughput_degradation,
        "median_p99_degradation_percent": p99_degradation,
        "additional_protocol_errors": additional_errors,
        "pass": throughput_degradation <= 3
        and p99_degradation <= 5
        and additional_errors == 0,
    }


def execute_observer(output: Path) -> dict[str, object]:
    spec = observer_spec()
    rows: list[dict[str, object]] = []
    for pair in range(1, 6):
        order = (False, True) if pair % 2 else (True, False)
        for enabled in order:
            label = "enabled" if enabled else "disabled"
            run_id = f"observer-p{pair}-{label}"
            run_root = output / "observer" / run_id
            manifest = run_durable_memory_child(
                load_command(
                    rate=spec.rate,
                    warmup_seconds=spec.warmup_seconds,
                    steady_seconds=spec.steady_seconds,
                    drain_seconds=spec.drain_seconds,
                    run_id=run_id,
                    finalized=run_root / "finalized-cell",
                    durable_root=output,
                    enabled=enabled,
                ),
                output=run_root,
                timeout_seconds=spec.warmup_seconds + spec.steady_seconds + spec.drain_seconds + 120,
                offered_requests=round(spec.rate * (spec.warmup_seconds + spec.steady_seconds)),
                cwd=ROOT,
            )
            summary = json.loads(
                (run_root / "finalized-cell/summary.json").read_text(encoding="utf-8")
            )
            rows.append(
                {
                    "pair": pair,
                    "diagnostics_enabled": enabled,
                    "achieved_rate": summary["achieved_rate"],
                    "p99_ns": summary["latency_ns"]["p99"],
                    "errors": manifest["counters"]["failed"],
                }
            )
    result = summarize_observer(rows)
    summary_path = output / "observer/summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("plan", "observer", "run"), required=True)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    os.environ.setdefault("NBSR_PERF_CARGO_TARGET", r"C:\codex-target\nbsr-p1b-release")
    if args.phase == "plan":
        print(json.dumps([item.__dict__ | {"run_id": item.run_id} for item in attribution_specs()], indent=2))
    elif args.phase == "observer":
        print(json.dumps(execute_observer(args.output), indent=2))
    else:
        if args.index is None:
            raise SystemExit("--index is required for run")
        print(json.dumps(execute_spec(attribution_specs()[args.index], args.output), indent=2))


if __name__ == "__main__":
    main()
