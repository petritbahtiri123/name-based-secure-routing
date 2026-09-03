from __future__ import annotations

import importlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture_b4b_task4c.ps1"


def test_task4c_profiles_only_matched_64_and_128_client_cells() -> None:
    task4c = importlib.import_module("scripts.run_b4b_task4c_profile")

    assert task4c.CLIENTS == (64, 128)
    assert task4c.REPEATS == 1


def test_task4c_capture_is_elevated_integrity_checked_and_exports_wait_views() -> None:
    source = CAPTURE.read_text(encoding="utf-8")

    assert "MANUAL_ELEVATION_REQUIRED" in source
    assert "PROC_THREAD+LOADER+PROFILE+CSWITCH+DISPATCHER" in source
    assert "Profile+CSwitch+ReadyThread" in source
    assert "Microsoft-Windows-Winsock-AFD" in source
    assert "Microsoft-Windows-TCPIP" in source
    assert "cpu-profile-detail.txt" in source
    assert "cswitch-process-thread.txt" in source
    assert "readythread.txt" in source
    assert "thread-activity.txt" in source
    assert "process-thread.txt" in source
    assert "kernel-trace-stats.txt" in source
    assert "network-trace-stats.txt" in source
    assert "network_trace_valid" in source
    assert "$controlCell.successful_admissions / [double]$controlCell.admission_elapsed_seconds" in source
    assert "TRACE_INTEGRITY_FAILED" in source
    assert "profile-overhead.json" in source


def test_task4c_capture_script_parses_as_powershell() -> None:
    command = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{CAPTURE}', [ref]$null, [ref]$errors); "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_task4c_analyzer_attributes_roles_by_recorded_pid() -> None:
    analyzer = importlib.import_module("scripts.analyze_b4b_task4c")
    rows = analyzer.parse_profile_rows(
        'perf_rust_source.exe ( 101), 900, 1.00, Ntfs.sys!"Unknown"\n'
        'perf_rust_source.exe ( 101), 100, 0.10, perf_rust_source.exe!quinn\n'
    )

    assert rows[101][0][0] == 900
    assert analyzer.file_system_weight(rows[101]) == 900


def test_task4c_analyzer_keeps_handshake_separate_from_total_admission_latency() -> None:
    analyzer = importlib.import_module("scripts.analyze_b4b_task4c")
    output = (
        '{"success":true,"transport_handshake_ns":100,"ttfab_ns":900}\n'
        '{"success":true,"transport_handshake_ns":300,"ttfab_ns":1000}\n'
    )

    assert analyzer.handshake_percentiles(output) == {"p50_ms": 0.0001, "p95_ms": 0.0003, "p99_ms": 0.0003}
