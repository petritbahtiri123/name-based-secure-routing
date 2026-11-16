from scripts.ci.check import command_groups


def test_protocol_documentation_selection_is_exact():
    prefix = "tests/test_documentation.py"
    names = ('test_core_v01_wire_contract_is_complete_and_non_claiming', 'test_core_v01_wire_contract_contains_every_frozen_numeric_mapping', 'test_protocol_package_exports_only_stable_wp1_surface')
    expected = {f"{prefix}::{name}" for name in names}
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    selected = [arg for arg in core.argv if arg.startswith(prefix)]
    assert len(selected) == len(expected)
    assert set(selected) == expected
