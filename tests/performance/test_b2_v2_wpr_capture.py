from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "capture_b2_v2_wpr.ps1"


def test_wpr_capture_script_is_fail_closed_and_preserves_matched_workloads() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "MANUAL_ELEVATION_REQUIRED" in source
    assert "WindowsPrincipal" in source
    assert "wpr.exe" in source
    assert "wpa.exe" in source
    assert "wpaexporter.exe" in source
    assert "-cancel" not in source
    assert 'Run-Benchmark -Label "control"' in source
    assert 'Run-Benchmark -Label "profiled"' in source
    assert "finally" in source
    assert "& $Xperf -d $TracePath" in source
    assert "profile-overhead.json" in source
    assert "metadata.json" in source
    assert '[string]$Payloads = "16384"' in source
    assert '[string]$Paths = "direct,nbsr"' in source
    assert '[string]$Affinities = "4"' in source
    assert '[int]$MaxRepeats = 1' in source
    assert '"--payloads", $Payloads' in source
    assert '"--paths", $Paths' in source
    assert '"--affinities", $Affinities' in source
    assert '"--max-repeats", $MaxRepeats' in source
    assert "trace-integrity.json" in source
    assert "Total # Lost Events" in source
    assert "cpu-profile-detail.txt" in source
    assert "TRACE_INTEGRITY_FAILED" in source
    assert "PROFILE_OVERHEAD_FAILED" in source
    assert '"PROC_THREAD+LOADER+PROFILE"' in source
    assert '"-stackwalk", "Profile"' in source
    assert 'capture_mode = "xperf-sampled-cpu-only"' in source
    assert 'blocked_time = "not-captured"' in source
    assert 'Invoke-Wpr @("-start", "CPU", "-filemode")' not in source
    assert '"CSwitch"' not in source
    assert '"ReadyThread"' not in source


def test_wpr_capture_script_parses_as_powershell() -> None:
    command = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT}', [ref]$null, [ref]$errors); "
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
