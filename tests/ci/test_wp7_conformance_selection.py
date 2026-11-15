from scripts.ci.check import command_groups


def test_wp7_conformance_selection_is_exact_in_memory_subset():
    prefix = "tests/test_wp7_conformance.py"
    names = (
        'test_audit_logs_are_operator_owned_bounded_and_monotonic',
        'test_audit_sequence_exhaustion_fails_closed_before_recording',
        'test_safe_operator_report_and_errors_exclude_private_destination',
        'test_connector_receipt_cannot_be_used_as_a_private_destination_guessing_or_linkage_oracle',
        'test_audit_overload_has_no_fallback_log_or_unbounded_growth',
        'test_audit_capacity_is_preflighted_before_admission_success_or_peer_audit_mutation',
        'test_public_admission_cannot_bypass_full_or_missing_operator_audits',
        'test_closed_topology_rejects_direct_operator_edge_and_oversized_collections',
        'test_raw_scan_is_deterministic_reaches_service_only_through_connector_and_discovers_no_private_destination',
        'test_verifier_rejects_duplicate_json_members_at_every_object',
    )
    expected = {f"{prefix}::{name}" for name in names}
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    selected = [arg for arg in core.argv if arg.startswith(prefix)]
    assert len(selected) == len(expected)
    assert set(selected) == expected
