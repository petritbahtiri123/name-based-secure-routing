from scripts.ci.check import command_groups


def test_lifecycle_validation_selection_is_exact_offline_subset():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    expected = {
        "tests/performance/test_b3_cleanup_gate.py",
        "tests/performance/test_b3_accept_window.py",
        "tests/performance/test_post_close_cleanup.py",
        "tests/performance/test_session_lifecycle_closure.py",
        "tests/performance/test_b3_failure_markers.py",
    }
    selected = [arg for arg in core.argv if arg.startswith("tests/performance")]
    assert len(selected) == len(expected)
    assert set(selected) == expected
