from scripts.ci.check import command_groups


def test_demo_client_security_contracts_selected_once():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    assert core.argv.count("tests/test_demo.py") == 1
    assert "scripts/demo.py" not in core.argv
    assert "nbsr/demo_client.py" not in core.argv
