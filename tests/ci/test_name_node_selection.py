from scripts.ci.check import command_groups


def test_core_selects_offline_name_node_adapters_without_server_tests():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    for path in ("tests/test_name_node_dns.py", "tests/test_name_node_observability.py"):
        assert core.argv.count(path) == 1
    assert "tests/test_name_node_server.py" not in core.argv
    assert "tests/test_name_route_e2e.py" not in core.argv
