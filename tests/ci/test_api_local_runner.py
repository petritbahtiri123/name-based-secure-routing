"""Local runner guardrails; Windows DPAPI roundtrip uses synthetic bytes only."""
import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path("scripts/ci/run_api_analysis.ps1")


def test_runner_is_present_and_key_is_not_an_argument():
    assert SCRIPT.is_file()
    text = SCRIPT.read_text()
    assert 'Environment["OPENAI_API_KEY"]' in text
    assert 'ArgumentList.Add($key)' not in text
    assert 'NBSR\\credentials\\openai-api-key.dpapi' in text
    assert 'WaitForExit(90000)' in text
    assert '$process.Kill($true)' in text
    assert "@('-I', '-B'" in text
    assert '$ExpectedPythonSha256' in text and '$ExpectedClientSha256' in text
    assert 'if ($started -and -not $process.HasExited)' in text


def test_importer_is_explicit_no_overwrite_and_clears_clipboard():
    text = Path("scripts/ci/import_api_key.ps1").read_text()
    assert '[switch]$FromClipboard' in text
    assert '[IO.FileMode]::CreateNew' in text
    assert "Set-Clipboard -Value ''" in text
    assert 'ConvertFrom-SecureString $secure' in text
    assert 'Write-Output $plain' not in text
    assert 'Write-Output $cipher' not in text
    assert "if ($clipboardAcquired) { Set-Clipboard -Value '' }" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows current-user DPAPI only")
def test_synthetic_dpapi_roundtrip_never_launches_api():
    assert SCRIPT.is_file()
    run = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), "-SelfTest"],
                         capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "Synthetic DPAPI roundtrip passed; no process or API call."
