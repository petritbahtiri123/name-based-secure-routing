from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.performance.p2d_stream_credit import (
    CONCURRENCIES,
    OUTCOME_ACCEPTED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_REVERTED,
    coefficient_of_variation,
    evaluate_acceptance,
    nearest_rank_percentile,
    select_saturation_concurrency,
    should_stop_after_three,
    summarize_pairs,
    validate_continuity,
    validate_live_cell,
    validate_matched_pair,
    validate_replay_limits,
    verify_closed_inventory,
)
from scripts.run_p2d_stream_credit import source_binding


def manifest(mode: str, *, concurrency: int = 16, seconds: int = 60) -> dict:
    return {
        "schema": "nbsr-p2d-cell-manifest-v1",
        "mode": mode,
        "profile": "legacy-stream-open" if mode == "before" else "nbsr-stream-credit-1",
        "concurrency": concurrency,
        "payload_bytes": 1024,
        "operation": "new-application-stream-admission-and-echo",
        "transport_session_model": "persistent-per-shard",
        "service_channel_model": "existing-authorized-per-shard",
        "application_stream_model": "new-per-operation",
        "duration_seconds_requested": seconds,
        "build": {"profile": "release", "features": ["benchmark-harness"]},
        "environment": {"host": "same-host", "timer": "rust-std-instant-qpc"},
        "source": {"commit": "0123456789abcdef", "dirty": False},
    }


def cell(
    mode: str,
    throughput: float,
    p99_ns: int,
    *,
    errors: int = 0,
    concurrency: int = 16,
) -> dict:
    return {
        "schema": "nbsr-p2d-live-cell-v1",
        "mode": mode,
        "profile": "legacy-stream-open" if mode == "before" else "nbsr-stream-credit-1",
        "concurrency": concurrency,
        "payload_bytes": 1024,
        "payload_correct": True,
        "completed_operations": 6000,
        "duration_ns": 60_000_000_000,
        "operations_per_second": throughput,
        "p50_ns": 100_000,
        "p95_ns": 150_000,
        "p99_ns": p99_ns,
        "cpu": {"status": "MEASURED", "process_cpu_ns": 1_000_000},
        "errors": errors,
        "remaining_credits": 16 if mode == "after" else None,
        "refill_count": 12 if mode == "after" else 0,
        "active_epochs": 1 if mode == "after" else 0,
        "replay_entries": 6000,
        "replay_limit": 10_000,
        "build": {"profile": "release", "features": ["benchmark-harness"]},
        "environment": {"host": "same-host", "timer": "rust-std-instant-qpc"},
        "source": {"commit": "0123456789abcdef", "dirty": False},
    }


def test_concurrency_sweep_is_the_exact_approved_sequence() -> None:
    # Catches dropping an endpoint, adding an unapproved load, or treating
    # credit_count=64 as a substitute for the concurrency sweep.
    assert CONCURRENCIES == (1, 2, 4, 8, 16, 32, 64)


def test_pair_manifests_are_matched_except_for_mode_and_profile() -> None:
    validate_matched_pair(manifest("before"), manifest("after"))
    for field, wrong in (
        ("concurrency", 8),
        ("payload_bytes", 2048),
        ("duration_seconds_requested", 61),
        ("operation", "preface-only"),
        ("service_channel_model", "new-per-operation"),
    ):
        changed = manifest("after")
        changed[field] = wrong
        with pytest.raises(ValueError, match=field):
            validate_matched_pair(manifest("before"), changed)


def test_percentile_median_and_sample_cv_are_pinned_to_raw_values() -> None:
    assert nearest_rank_percentile([50, 10, 40, 20, 30], 50) == 30
    assert nearest_rank_percentile([50, 10, 40, 20, 30], 99) == 50
    assert coefficient_of_variation([90.0, 100.0, 110.0]) == pytest.approx(0.1)
    before = [cell("before", value, p99) for value, p99 in ((90, 100), (100, 110), (110, 120))]
    after = [cell("after", value, p99) for value, p99 in ((108, 105), (120, 115), (132, 126))]
    summary = summarize_pairs(before, after)
    assert summary["before_median_operations_per_second"] == 100
    assert summary["after_median_operations_per_second"] == 120
    assert summary["before_throughput_cv"] == pytest.approx(0.1)
    assert summary["after_throughput_cv"] == pytest.approx(0.1)
    assert summary["before_median_p99_ns"] == 110
    assert summary["after_median_p99_ns"] == 115


def test_three_pairs_stop_only_when_both_cvs_are_bounded_and_each_gate_is_clear() -> None:
    stable_before = [cell("before", value, 100) for value in (100, 101, 99)]
    stable_after = [cell("after", value, 104) for value in (121, 122, 120)]
    assert should_stop_after_three(stable_before, stable_after) is True

    noisy_after = [cell("after", value, 104) for value in (105, 121, 137)]
    assert should_stop_after_three(stable_before, noisy_after) is False

    straddles_throughput = [cell("after", value, 104) for value in (119, 121, 120)]
    assert should_stop_after_three(stable_before, straddles_throughput) is False

    straddles_p99 = [cell("after", value, p99) for value, p99 in ((121, 104), (122, 106), (120, 105))]
    assert should_stop_after_three(stable_before, straddles_p99) is False


def test_exact_twenty_percent_and_five_percent_boundaries_pass() -> None:
    before = [cell("before", 100, 100) for _ in range(3)]
    after = [cell("after", 120, 105) for _ in range(3)]
    result = evaluate_acceptance(
        summarize_pairs(before, after),
        security="PASS",
        refill="PASS",
        continuity="PASS",
        soak="PASS",
        resource="PASS",
    )
    assert result["gates"]["throughput"] == "PASS"
    assert result["gates"]["p99"] == "PASS"
    assert result["outcome"] == OUTCOME_ACCEPTED


def test_zero_errors_and_gate_precedence_dominate_performance() -> None:
    before = [cell("before", 100, 100) for _ in range(3)]
    after = [cell("after", 130, 90) for _ in range(3)]
    after[1]["errors"] = 1
    result = evaluate_acceptance(
        summarize_pairs(before, after),
        security="FAIL",
        refill="PASS",
        continuity="PASS",
        soak="PASS",
        resource="PASS",
    )
    assert result["gates"]["errors"] == "FAIL"
    assert result["blocking_gate"] == "errors"
    assert result["outcome"] == OUTCOME_REVERTED

    inconclusive = evaluate_acceptance(
        summarize_pairs([cell("before", 100, 100) for _ in range(3)], [cell("after", 130, 90) for _ in range(3)]),
        security="PASS",
        refill="PASS",
        continuity="PASS",
        soak="INCONCLUSIVE",
        resource="PASS",
    )
    assert inconclusive["blocking_gate"] == "soak"
    assert inconclusive["outcome"] == OUTCOME_INCONCLUSIVE


def test_continuity_requires_ten_refills_and_bounded_credit_replay_state() -> None:
    good = cell("after", 130, 90)
    good.update({"windows_crossed": 10, "refill_count": 10, "remaining_credits": 0, "active_epochs": 2})
    assert validate_continuity(good) == "PASS"
    for field, wrong in (
        ("windows_crossed", 9),
        ("refill_count", 9),
        ("remaining_credits", 65),
        ("active_epochs", 3),
        ("replay_entries", 10_001),
    ):
        invalid = dict(good)
        invalid[field] = wrong
        assert validate_continuity(invalid) == "FAIL"


def test_live_cells_require_observed_payload_timing_cpu_and_bounded_state() -> None:
    validate_live_cell(cell("after", 120, 105))
    for field, wrong in (
        ("payload_bytes", 1000),
        ("payload_correct", False),
        ("errors", 1),
        ("active_epochs", 3),
        ("remaining_credits", -1),
        ("replay_entries", 10_001),
        ("replay_limit", 4_294_967_295),
    ):
        invalid = cell("after", 120, 105)
        invalid[field] = wrong
        with pytest.raises(ValueError, match=field):
            validate_live_cell(invalid)


def test_every_nested_endpoint_must_use_the_exact_p1f_replay_limit() -> None:
    measured = cell("after", 120, 105)
    bad_source = {
        "schema": "nbsr-p2d-rust-shard-v1",
        "completed_operations": 8_000,
        "errors": 0,
        "replay_entries": 8_000,
        "replay_limit": 4_294_967_295,
    }
    good_destination = {
        "schema": "nbsr-p2d-rust-server-v1",
        "completed_operations": 8_000,
        "errors": 0,
        "replay_entries": 8_000,
        "replay_limit": 10_000,
    }
    good_source = {**bad_source, "replay_limit": 10_000}
    measured["shards"] = [
        {"ordinal": 1, "source": bad_source, "destination": good_destination},
        {"ordinal": 2, "source": good_source, "destination": good_destination},
    ]
    measured["replay_limit"] = 10_000

    assert validate_replay_limits(measured) == "FAIL"
    with pytest.raises(ValueError, match="replay_limit"):
        validate_live_cell(measured)


def test_source_binding_covers_all_compiled_and_imported_inputs_with_diff_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    binding = source_binding()
    bound = set(binding["files"])
    compiled = {
        path.relative_to(root).as_posix()
        for path in (root / "crates/nbsr-transport/src").rglob("*.rs")
    }
    assert compiled <= bound
    assert {
        "crates/nbsr-transport/Cargo.toml",
        "crates/nbsr-transport/Cargo.lock",
        "scripts/performance/authority.py",
        "scripts/performance/p2d_stream_credit.py",
        "scripts/run_performance_validation.py",
        "scripts/run_p2d_stream_credit.py",
        "docs/protocol/stream-credit-extension.md",
    } <= bound
    assert binding["commit"] == subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert binding["bound_input_identity"]["status_porcelain_sha256"]
    assert binding["bound_input_identity"]["worktree_diff_sha256"]
    assert binding["bound_input_identity"]["index_diff_sha256"]
    bound_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", *sorted(bound)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert binding["bound_input_identity"]["bound_inputs_clean"] is (not bound_status)


def test_saturation_selects_smallest_concurrency_within_two_percent_of_maximum() -> None:
    sweep = [
        cell("after", throughput, 100, concurrency=concurrency)
        for concurrency, throughput in zip(CONCURRENCIES, (100, 180, 250, 296, 300, 299, 295), strict=True)
    ]
    assert select_saturation_concurrency(sweep) == 8


def test_checksum_inventory_is_closed_and_rejects_unlisted_or_changed_files(tmp_path) -> None:
    (tmp_path / "analysis.json").write_text(json.dumps({"outcome": OUTCOME_ACCEPTED}) + "\n", encoding="utf-8")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "cell.json").write_text("{}\n", encoding="utf-8")
    entries = []
    for relative in ("analysis.json", "raw/cell.json"):
        digest = hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
        entries.append(f"{digest}  {relative}")
    checksum = tmp_path / "checksums.sha256"
    checksum.write_text("\n".join(entries) + "\n", encoding="utf-8")
    assert verify_closed_inventory(tmp_path, checksum) == 2

    (tmp_path / "unlisted.txt").write_text("not closed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        verify_closed_inventory(tmp_path, checksum)
    (tmp_path / "unlisted.txt").unlink()
    (tmp_path / "raw" / "cell.json").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        verify_closed_inventory(tmp_path, checksum)
