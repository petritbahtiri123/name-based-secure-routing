from scripts.ci.check import command_groups


def test_name_service_in_memory_tests_are_selected_without_live_servers():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    assert core.argv.count("tests/test_name_service.py") == 1
    assert "tests/test_name_node_server.py" not in core.argv
    assert "tests/test_name_route_e2e.py" not in core.argv
