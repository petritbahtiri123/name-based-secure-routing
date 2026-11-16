from scripts.ci.check import command_groups


def test_transport_inventory_selection_excludes_cargo_and_broad_transport_file():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    prefix = "tests/test_wp3_rust_transport_isolation.py"
    selected = [arg for arg in core.argv if arg.startswith(prefix)]
    assert selected == [prefix + "::test_no_certificate_or_private_key_fixture_is_committed"]
    assert core.argv.count("tests/test_transport_fixture_inventory.py") == 1
