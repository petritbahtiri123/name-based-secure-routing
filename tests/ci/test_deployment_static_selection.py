from scripts.ci.check import command_groups


def test_static_deployment_checks_are_selected_without_live_launchers():
    commands = command_groups("python-core")
    core = next(c for c in commands if c.name == "python-core")
    for path in ("tests/test_deployment_tls.py", "tests/test_kind_security.py"):
        assert core.argv.count(path) == 1
    for command in commands:
        assert all("kind-up" not in arg and "verify-kind-security" not in arg for arg in command.argv)
