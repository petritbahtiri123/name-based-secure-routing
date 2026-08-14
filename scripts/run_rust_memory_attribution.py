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
    warmup_seconds: int = 60
    steady_seconds: int = 1800
    drain_seconds: int = 20

    @property
    def run_id(self) -> str:
        return f"rust-rust-p1a-{self.percent}pct-r{self.ordinal}"


def attribution_specs() -> list[AttributionSpec]:
    return [
        AttributionSpec(50, 843.75, 1),
        AttributionSpec(75, 1265.625, 1),
        AttributionSpec(75, 1265.625, 2),
        AttributionSpec(75, 1265.625, 3),
    ]


def load_command(spec: AttributionSpec, finalized: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts/run_performance_load_cell.py"),
        "--path",
        "rust-rust",
        "--offered-rate",
        str(spec.rate),
        "--warmup-seconds",
        str(spec.warmup_seconds),
        "--steady-seconds",
        str(spec.steady_seconds),
        "--idle-p99-ns",
        "404000",
        "--run-id",
        spec.run_id,
        "--output",
        str(finalized),
        "--memory",
        "--durable-events",
        "--rust-diagnostics",
        "--diagnostic-drain-seconds",
        str(spec.drain_seconds),
    ]


def execute_spec(spec: AttributionSpec, output: Path) -> dict[str, object]:
    run_root = output / "runs" / spec.run_id
    return run_durable_memory_child(
        load_command(spec, run_root / "finalized-cell"),
        output=run_root,
        timeout_seconds=spec.warmup_seconds + spec.steady_seconds + spec.drain_seconds + 180,
        offered_requests=round(spec.rate * (spec.warmup_seconds + spec.steady_seconds)),
        cwd=ROOT,
    )


def observer_command(*, enabled: bool, run_id: str, finalized: Path) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts/run_performance_load_cell.py"),
        "--path",
        "rust-rust",
        "--offered-rate",
        "843.75",
        "--warmup-seconds",
        "5",
        "--steady-seconds",
        "30",
        "--idle-p99-ns",
        "404000",
        "--run-id",
        run_id,
        "--output",
        str(finalized),
        "--memory",
        "--durable-events",
        "--validation-profile",
    ]
    if enabled:
        command.extend(["--rust-diagnostics", "--diagnostic-drain-seconds", "0"])
    return command


def execute_observer(output: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for pair in range(1, 6):
        order = (False, True) if pair % 2 else (True, False)
        for enabled in order:
            label = "enabled" if enabled else "disabled"
            run_id = f"observer-p{pair}-{label}"
            run_root = output / "observer" / run_id
            manifest = run_durable_memory_child(
                observer_command(enabled=enabled, run_id=run_id, finalized=run_root / "finalized-cell"),
                output=run_root,
                timeout_seconds=120,
                offered_requests=round(843.75 * 35),
                cwd=ROOT,
            )
            summary = json.loads((run_root / "finalized-cell/summary.json").read_text(encoding="utf-8"))
            rows.append(
                {
                    "pair": pair,
                    "diagnostics_enabled": enabled,
                    "achieved_rate": summary["achieved_rate"],
                    "p99_ns": summary["latency_ns"]["p99"],
                    "errors": manifest["counters"]["failed"],
                }
            )
    enabled_rows = [row for row in rows if row["diagnostics_enabled"]]
    disabled_rows = [row for row in rows if not row["diagnostics_enabled"]]
    throughput_degradation = 100 * (
        1
        - statistics.median(float(row["achieved_rate"]) for row in enabled_rows)
        / statistics.median(float(row["achieved_rate"]) for row in disabled_rows)
    )
    p99_degradation = 100 * (
        statistics.median(float(row["p99_ns"]) for row in enabled_rows) / statistics.median(float(row["p99_ns"]) for row in disabled_rows)
        - 1
    )
    result = {
        "pairs": rows,
        "median_throughput_degradation_percent": throughput_degradation,
        "median_p99_degradation_percent": p99_degradation,
        "additional_protocol_errors": sum(int(row["errors"]) for row in enabled_rows) - sum(int(row["errors"]) for row in disabled_rows),
    }
    result["pass"] = throughput_degradation <= 3 and p99_degradation <= 5 and result["additional_protocol_errors"] == 0
    (output / "observer/summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("plan", "observer", "run"), required=True)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    os.environ.setdefault("NBSR_PERF_CARGO_TARGET", r"C:\codex-target\nbsr-p1a-release")
    if args.phase == "plan":
        print(json.dumps([spec.__dict__ | {"run_id": spec.run_id} for spec in attribution_specs()], indent=2))
    elif args.phase == "observer":
        print(json.dumps(execute_observer(args.output), indent=2))
    else:
        if args.index is None:
            raise SystemExit("--index is required for run")
        print(json.dumps(execute_spec(attribution_specs()[args.index], args.output), indent=2))


if __name__ == "__main__":
    main()
