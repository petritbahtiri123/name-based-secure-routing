from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
COUNT = re.compile(r"(?P<count>\d+)\s+(?P<kind>passed|failed|skipped)")
TAP_COUNT = re.compile(r"(?:#|ℹ)\s+(?P<kind>pass|fail|skipped)\s+(?P<count>\d+)")
GO_PASS = re.compile(r'"Action":"pass"[^\n]*"Test":')
GO_FAIL = re.compile(r'"Action":"fail"[^\n]*"Test":')


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    argv: tuple[str, ...]
    cwd: str = "."
    manifest_gate: bool = False
    skip_reason: str | None = None
    count_mode: str = "auto"


def _counts(output: str, mode: str, succeeded: bool) -> dict[str, int]:
    result = {"passed": 0, "failed": 0, "skipped": 0}
    if mode == "gate":
        result["passed" if succeeded else "failed"] = 1
        return result
    for match in COUNT.finditer(output):
        if mode == "rust":
            result[match.group("kind")] += int(match.group("count"))
        else:
            result[match.group("kind")] = max(result[match.group("kind")], int(match.group("count")))
    if mode == "tap":
        for match in TAP_COUNT.finditer(output):
            kind = {"pass": "passed", "fail": "failed", "skipped": "skipped"}[match.group("kind")]
            result[kind] = max(result[kind], int(match.group("count")))
    if mode == "go-json":
        result["passed"] = len(GO_PASS.findall(output))
        result["failed"] = len(GO_FAIL.findall(output))
    return result


def run_commands(commands: list[Command]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    totals = {"passed": 0, "failed": 0, "skipped": 0}
    failed = False
    for command in commands:
        if command.skip_reason is not None:
            records.append({"id": command.id, "status": "SKIP", "skip_reason": command.skip_reason})
            totals["skipped"] += 1
            continue
        environment = os.environ.copy()
        environment.setdefault("CARGO_TARGET_DIR", str(Path(os.environ.get("LOCALAPPDATA", ROOT)) / "Temp/nbsr-task10-cargo"))
        executable = command.argv[0]
        if os.name == "nt" and executable == "npm":
            executable = shutil.which("npm.cmd") or executable
        argv = (executable, *command.argv[1:])
        try:
            completed = subprocess.run(
                argv,
                cwd=ROOT / command.cwd,
                env=environment,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                errors="replace",
                timeout=1_800,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            records.append(
                {
                    "id": command.id,
                    "argv": list(command.argv),
                    "cwd": command.cwd,
                    "exit_code": None,
                    "counts": {"passed": 0, "failed": 0, "skipped": 0},
                    "status": "FAIL",
                    "error": str(exc),
                }
            )
            failed = True
            if command.manifest_gate:
                break
            continue
        counts = _counts(completed.stdout, command.count_mode, completed.returncode == 0)
        if command.count_mode not in {"gate", "auto"} and sum(counts.values()) == 0:
            completed = subprocess.CompletedProcess(completed.args, 1, completed.stdout)
        for kind in totals:
            totals[kind] += counts[kind]
        record = {
            "id": command.id,
            "argv": list(command.argv),
            "cwd": command.cwd,
            "exit_code": completed.returncode,
            "counts": counts,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
        }
        records.append(record)
        if completed.returncode != 0:
            failed = True
            if command.manifest_gate:
                break
    outcome = "FAIL" if failed else ("PASS_WITH_SKIPS" if totals["skipped"] else "PASS")
    return {"commands": records, "outcome": outcome, "totals": totals}
