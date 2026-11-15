from scripts.ci.check import command_groups


def test_legacy_origin_cache_is_selected_once_without_live_name_services():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    assert core.argv.count("tests/test_legacy_origin.py") == 1
    assert "tests/test_name_node_server.py" not in core.argv
    assert "tests/test_name_route_e2e.py" not in core.argv
