from scripts.ci.check import command_groups


def test_lifecycle_validation_selection_is_exact_offline_subset():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    expected = {
        "tests/performance/test_b3_cleanup_gate.py",
        "tests/performance/test_b3_accept_window.py",
        "tests/performance/test_post_close_cleanup.py",
        "tests/performance/test_session_lifecycle_closure.py",
        "tests/performance/test_b3_failure_markers.py",
        "tests/performance/test_physical_core_classification.py",
        "tests/performance/test_wpr_trace_quality.py",
        "tests/performance/test_failure_evidence.py",
        "tests/performance/test_evidence_verifier.py",
        "tests/performance/test_grouped_progress.py",
        "tests/performance/test_statistics.py",
        "tests/performance/test_cpu_efficiency.py",
        "tests/performance/test_linux_native_packet_accounting.py",
        "tests/performance/test_native_packet_markers.py",
        "tests/performance/test_native_packet_phases.py",
        "tests/performance/test_mixed_workload.py",
        "tests/performance/test_sustained_capacity.py",
        "tests/performance/test_benchmark_model.py",
        "tests/performance/test_bounded_replay_model.py",
        "tests/performance/test_session_rotation_model.py",
        "tests/performance/test_evidence_writer.py",
        "tests/performance/test_completion_evidence.py",
        "tests/performance/test_b3_linux_analysis.py",
        "tests/performance/test_b3_v2_analysis.py",
        "tests/performance/test_b5_stream.py",
    }
    selected = [arg for arg in core.argv if arg.startswith("tests/performance")]
    assert len(selected) == len(expected)
    assert set(selected) == expected
