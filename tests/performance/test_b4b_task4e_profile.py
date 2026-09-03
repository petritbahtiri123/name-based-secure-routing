from pathlib import Path
import importlib
import json
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_task4e_cells_and_unchanged_workload_call(tmp_path, monkeypatch):
    path = ROOT / "scripts/run_b4b_task4e_profile.py"
    assert path.exists(), "Task 4e capture runner missing"
    runner = importlib.import_module("scripts.run_b4b_task4e_profile")
    monkeypatch.setattr(runner.b4b, "build", lambda target: {})
    def cell(clients, repeat, connections, binaries, raw, **kwargs):
        assert (repeat, connections) == (1, 1)
        assert kwargs == dict(duration=8, warmup=2, planned_clients=[128, 256, 512])
        return {"clients": clients, "valid": False}
    monkeypatch.setattr(runner.b4b, "run_cell", cell)
    output = tmp_path / "capture"
    runner.run(output, 2, 8)
    manifest = json.loads((output / "manifest.json").read_text())
    assert [r["clients"] for r in manifest["records"]] == [128, 256, 512]
    assert all(not r["valid"] for r in manifest["records"])
    assert manifest["cleanup_diagnostic_clients"] == [512]
    assert all(t["ended_unix_ns"] >= t["started_unix_ns"] for t in manifest["timeline"])


def test_task4e_capture_preserves_separate_integrity_and_waits():
    path = ROOT / "scripts/capture_b4b_task4e.ps1"
    assert path.exists(), "Task 4e elevated capture missing"
    source = path.read_text(encoding="utf-8")
    for required in (
        "MANUAL_ELEVATION_REQUIRED", "Profile+CSwitch+ReadyThread",
        "kernel_lost_events", "network_lost_events", "network_trace_valid",
        "TRACE_INTEGRITY_FAILED", "profile-overhead.json", "readythread.txt",
        "run_b4b_task4e_profile.py", "@(128, 256, 512)",
    ):
        assert required in source
    command = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{path}', [ref]$null, [ref]$errors); if ($errors.Count) {{ exit 1 }}"
    )
    result = subprocess.run(["pwsh", "-NoProfile", "-Command", command], check=False)
    assert result.returncode == 0
