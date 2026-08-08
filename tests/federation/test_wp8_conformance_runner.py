from __future__ import annotations

import sys
from pathlib import Path

from scripts.wp8_conformance.runner import Command, run_commands


def test_runner_stops_when_manifest_gate_fails() -> None:
    commands = [
        Command("manifest", (sys.executable, "-c", "raise SystemExit(7)"), manifest_gate=True),
        Command("must-not-run", (sys.executable, "-c", "print('1 passed')")),
    ]
    result = run_commands(commands)
    assert result["outcome"] == "FAIL"
    assert [item["id"] for item in result["commands"]] == ["manifest"]
    assert result["commands"][0]["exit_code"] == 7


def test_runner_reports_observed_counts_and_explicit_skips() -> None:
    commands = [
        Command("manifest", (sys.executable, "-c", "print('verified')"), manifest_gate=True),
        Command("tests", (sys.executable, "-c", "print('12 passed, 1 skipped')")),
        Command("unsupported", (), skip_reason="independent wire peer not implemented"),
    ]
    result = run_commands(commands)
    assert result["outcome"] == "PASS_WITH_SKIPS"
    assert result["totals"] == {"passed": 12, "failed": 0, "skipped": 2}
    assert result["commands"][2]["skip_reason"] == "independent wire peer not implemented"


def test_runner_propagates_non_manifest_failure_after_collecting_results() -> None:
    commands = [
        Command("manifest", (sys.executable, "-c", "print('verified')"), manifest_gate=True),
        Command("failure", (sys.executable, "-c", "print('2 failed'); raise SystemExit(1)")),
        Command("later", (sys.executable, "-c", "print('3 passed')")),
    ]
    result = run_commands(commands)
    assert result["outcome"] == "FAIL"
    assert result["totals"] == {"passed": 3, "failed": 2, "skipped": 0}
    assert len(result["commands"]) == 3


def test_runner_records_missing_executable_instead_of_crashing() -> None:
    result = run_commands([Command("missing", ("definitely-not-an-nbsr-tool",))])
    assert result["outcome"] == "FAIL"
    assert result["commands"][0]["status"] == "FAIL"
    assert result["commands"][0]["exit_code"] is None


def test_runner_decodes_utf8_tap_counts_on_windows() -> None:
    result = run_commands(
        [
            Command(
                "utf8-tap",
                (
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(b'\\xe2\\x84\\xb9 pass 2\\n')",
                ),
                count_mode="tap",
            )
        ]
    )
    assert result["outcome"] == "PASS"
    assert result["totals"] == {"passed": 2, "failed": 0, "skipped": 0}


def test_real_matrix_includes_dependency_and_repository_privacy_inspection() -> None:
    matrix = (Path(__file__).resolve().parents[2] / "scripts" / "verify_wp8_conformance.py").read_text(
        encoding="utf-8"
    )
    assert 'Command("dependency-inspection"' in matrix
    assert 'Command("repository-privacy-secret-scan"' in matrix
