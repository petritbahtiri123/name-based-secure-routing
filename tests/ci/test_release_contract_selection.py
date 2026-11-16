from scripts.ci.check import command_groups


def test_release_contracts_are_selected_without_release_execution():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    assert core.argv.count("tests/test_release_packaging.py") == 1
    assert "scripts/package_release.py" not in core.argv
    assert "docker" not in core.argv
