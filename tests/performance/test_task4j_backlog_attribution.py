import pytest

from scripts.analyze_b4b_task4j import analyze_diagnostic_rows, percentile, verify_source_manifest


def row(ts, quic, sessions, channels, streams, pending=0):
    values = {
        "timestamp_ns": ts,
        "phase": "sample",
        "pending_routes_current_entries": pending,
        "audit_queue_current_entries": 0,
    }
    for prefix, current, completed in (
        ("quic_connections", quic, 10 - quic),
        ("transport_sessions", sessions, 10 - sessions),
        ("service_channels", channels, 10 - channels),
        ("application_streams", streams, 10 - streams),
    ):
        values[f"{prefix}_created"] = 0 if ts == 0 else 10
        values[f"{prefix}_completed"] = 0 if ts == 0 else completed
        values[f"{prefix}_current_live"] = current
    return values


def test_stage_occupancy_is_derived_from_aligned_samples():
    result = analyze_diagnostic_rows(
        [
            row(0, 0, 0, 0, 0),
            row(1_000_000_000, 8, 6, 4, 2),
            row(2_000_000_000, 0, 0, 0, 0),
        ]
    )
    assert result["occupancy_peak"] == {
        "transport_establishment": 2,
        "control_and_route_admission": 2,
        "channel_and_application_activation": 2,
        "application_and_close": 2,
    }
    assert result["completion_rate_per_second"]["quic_connections"] == 5.0


def test_counter_invariant_violation_is_rejected():
    with pytest.raises(ValueError, match="stage ordering"):
        analyze_diagnostic_rows([row(0, 0, 0, 0, 0), row(1, 2, 3, 1, 0)])


def test_non_monotonic_cumulative_counter_is_rejected():
    rows = [row(0, 0, 0, 0, 0), row(1, 1, 1, 1, 1), row(2, 0, 0, 0, 0)]
    rows[2]["transport_sessions_completed"] = 8
    rows[1]["transport_sessions_completed"] = 9
    with pytest.raises(ValueError, match="non-monotonic"):
        analyze_diagnostic_rows(rows)


def test_percentile_is_deterministic_and_rejects_empty_input():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    with pytest.raises(ValueError, match="empty"):
        percentile([], 0.5)


def test_source_manifest_rejects_mutation(tmp_path):
    (tmp_path / "raw.json").write_text("original", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(b"original").hexdigest()
    (tmp_path / "checksums.sha256").write_text(f"{digest}  raw.json\n", encoding="ascii")
    verify_source_manifest(tmp_path)
    (tmp_path / "raw.json").write_text("mutated", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_source_manifest(tmp_path)
