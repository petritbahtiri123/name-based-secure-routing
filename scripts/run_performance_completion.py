from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.performance.durable_memory import run_durable_memory_child  # noqa: E402


PATHS = ("direct-quic", "rust-rust", "go-rust")
DISCOVERY_RATES = {
    "direct-quic": (3_000, 4_000, 4_500, 5_000),
    "rust-rust": (1_000, 1_500, 1_750, 2_000),
    "go-rust": (200, 300, 400),
}
IDLE_P99_NS = {"direct-quic": 170_840, "rust-rust": 404_000, "go-rust": 466_540}
MEMORY_SAFETY_TIMEOUT_SECONDS = 2_040
LOAD_CELL_CLIENT_TIMEOUT_SECONDS = 3_600


@dataclass(frozen=True)
class RunSpec:
    phase: str
    path: str
    rate: float
    warmup_seconds: int
    steady_seconds: int
    run_ordinal: int
    percent: int | None = None
    sampling_cadence_seconds: int = 1

    @property
    def run_id(self) -> str:
        suffix = f"-{self.percent}pct" if self.percent is not None else ""
        return f"{self.path}-{self.phase}-{self.rate:g}{suffix}-r{self.run_ordinal}"


def completion_plan(phase: str, *, accepted_capacities: dict[str, float]) -> list[RunSpec]:
    if phase == "discover":
        return [RunSpec(phase, path, rate, 60, 600, 1) for path in PATHS for rate in DISCOVERY_RATES[path]]
    if set(accepted_capacities) != set(PATHS):
        raise ValueError("accepted capacities are required independently for all paths")
    if phase == "confirm":
        return [RunSpec(phase, path, accepted_capacities[path], 60, 600, ordinal) for path in PATHS for ordinal in (1, 2, 3)]
    if phase == "formal":
        return [RunSpec(phase, path, accepted_capacities[path] * percent / 100, 60, 600, 1, percent) for path in PATHS for percent in (25, 50, 75, 90)]
    if phase == "memory":
        load_points = {"direct-quic": (50, 68), "rust-rust": (50, 75), "go-rust": (50, 75)}
        return [
            RunSpec(phase, path, accepted_capacities[path] * percent / 100, 60, 1_800, 1, percent)
            for path in PATHS
            for percent in load_points[path]
        ]
    raise ValueError(f"unsupported completion phase {phase}")


def command_for(spec: RunSpec, output_root: Path, *, output_override: Path | None = None) -> list[str]:
    output = output_override if output_override is not None else output_root / spec.phase / spec.run_id
    command = [
        sys.executable, str(ROOT / "scripts/run_performance_load_cell.py"),
        "--path", spec.path, "--offered-rate", str(spec.rate),
        "--warmup-seconds", str(spec.warmup_seconds), "--steady-seconds", str(spec.steady_seconds),
        "--idle-p99-ns", str(IDLE_P99_NS[spec.path]), "--run-id", spec.run_id,
        "--output", str(output),
    ]
    if spec.phase in {"discover", "confirm", "formal"}:
        command.append("--formal")
    if spec.phase == "memory":
        command.extend([
            "--memory", "--sampling-cadence-seconds", str(spec.sampling_cadence_seconds),
            "--durable-events",
        ])
    return command


def execute_spec(
    spec: RunSpec, output_root: Path, *, timeout_seconds: float = MEMORY_SAFETY_TIMEOUT_SECONDS,
) -> None:
    output = output_root / spec.phase / spec.run_id
    if output.exists():
        raise SystemExit(f"refusing to overwrite completed or partial run: {output}")
    if spec.phase == "memory":
        child_output = output / "finalized-cell"
        command = command_for(spec, output_root, output_override=child_output)
        command.extend(["--durable-root", str(output)])
        run_durable_memory_child(
            command,
            output=output,
            timeout_seconds=timeout_seconds,
            offered_requests=round(spec.rate * (spec.warmup_seconds + spec.steady_seconds)),
            authoritative_run=True,
            cwd=ROOT,
        )
        return
    subprocess.run(command_for(spec, output_root), cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["discover", "confirm", "formal", "memory"], required=True)
    parser.add_argument("--accepted-capacities", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-index", type=int)
    args = parser.parse_args()
    accepted = json.loads(args.accepted_capacities.read_text(encoding="utf-8")) if args.accepted_capacities else {}
    specs = completion_plan(args.phase, accepted_capacities=accepted)
    plan = [{**asdict(spec), "run_id": spec.run_id, "command": command_for(spec, args.output)} for spec in specs]
    if args.execute_index is None:
        print(json.dumps(plan, indent=2))
        return
    spec = specs[args.execute_index]
    execute_spec(spec, args.output)


if __name__ == "__main__":
    main()
