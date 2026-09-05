import pytest

from scripts.performance.post_close_cleanup import FIELDS, validate_report


def report():
    return {"schema": "nbsr-p2a-post-close-v1", "pid": 42, "role": "source",
            "diagnostics_enabled_before_run": True, "runtime_state": "runtime_alive",
            "ownership": {field: 0 for field in FIELDS}}


def test_requires_post_close_report_not_creation_deltas():
    assert not validate_report({"transport_sessions_created_delta": 0}, "source", 42)
    assert validate_report(report(), "source", 42)


@pytest.mark.parametrize("field", FIELDS)
def test_every_owned_resource_must_be_present_and_exact_zero(field):
    value = report()
    del value["ownership"][field]
    assert not validate_report(value, "source", 42)
    for invalid in (1, -1, False, 0.5, "0", None):
        value["ownership"][field] = invalid
        assert not validate_report(value, "source", 42)


@pytest.mark.parametrize("field,value", [("pid", 41), ("pid", True),
    ("role", "destination"), ("diagnostics_enabled_before_run", False),
    ("runtime_state", "unknown"), ("runtime_state", []), ("schema", "old")])
def test_report_is_bound_to_process_phase_and_enabled_instrumentation(field, value):
    item = report()
    item[field] = value
    assert not validate_report(item, "source", 42)
