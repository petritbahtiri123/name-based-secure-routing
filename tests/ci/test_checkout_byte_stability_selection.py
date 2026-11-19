import json
from pathlib import Path

from scripts.ci.check import command_groups


def test_checkout_byte_stability_selected_once_in_both_core_platforms():
    commands = command_groups("python-core")
    target = "tests/test_checkout_byte_stability.py"
    assert sum(command.argv.count(target) for command in commands) == 1
    core = next(command for command in commands if command.name == "python-core")
    assert target in core.argv
    workflow = json.loads(Path(".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["python"]
    assert set(job["strategy"]["matrix"]["os"]) == {"ubuntu-24.04", "windows-2025"}
    step = next(step for step in job["steps"] if "check.py python-core" in step.get("run", ""))
    assert "if" not in step
