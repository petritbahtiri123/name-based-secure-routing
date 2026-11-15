import json
from pathlib import Path

from scripts.ci.check import GO_MODULES, command_groups


def test_fixturegen_is_selected_for_offline_test_and_vet_with_preparation():
    module = "tools/demo-lab/fixturegen"
    assert GO_MODULES.count(module) == 1
    commands = [c for c in command_groups("go") if c.cwd == module]
    assert len(commands) == 2
    assert {c.argv[1] for c in commands} == {"test", "vet"}
    assert all("-mod=readonly" in c.argv and "-p=2" in c.argv and c.argv[-1] == "./..." for c in commands)
    assert "-timeout=90s" in next(c.argv for c in commands if c.argv[1] == "test")
    workflow = json.loads(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["go"]["steps"]
    prep = next(s for s in steps if s.get("name") == "Resolve and verify module locks")
    block = ("Push-Location " + module + "\ngo mod download\n"
             "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\ngo mod verify\n"
             "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\nPop-Location")
    assert prep["run"].count(block) == 1
    run = next(s for s in steps if s.get("name") == "Test and vet every Go module")
    assert run["env"]["GOPROXY"] == "off"
    assert steps.index(prep) < steps.index(run)
