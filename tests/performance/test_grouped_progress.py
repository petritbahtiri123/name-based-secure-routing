"""Grouped progress accounting and bounded state contracts, established RED first."""

from copy import deepcopy

import pytest

from scripts.performance.b5_grouped import ProgressValidator


COUNTERS = ("offered", "reserved", "issued", "completed", "missed", "unreserved_current")


def record(index=1, count=1, deadline=2_000_000_000):
    group = dict(offered=count, reserved=count, issued=count, completed=count, missed=0, unreserved_current=0)
    value = dict(
        schema="nbsr-b5-grouped-progress-v1",
        event="b5_grouped_progress",
        window_index=index,
        phase="steady",
        elapsed_ns=index * 1_000_000_000,
        issue_deadline_ns=deadline,
        interval_start_ns=(index - 1) * 1_000_000_000,
        interval_end_ns=index * 1_000_000_000,
        group_counters=[dict(group_id=g, **group) for g in range(2)],
        goodput_bytes_per_second=4096 * (count if index == 1 else 1) if count else 0,
        sample_count=(2 * count // 64 if index == 1 else 2 * count // 64 - max(0, 2 * (count - 1)) // 64),
        sample_stride=64,
        sample_capacity=64,
        sample_overflow_count=0,
        p50_latency_ns=None,
        p95_latency_ns=None,
        p99_latency_ns=None,
        max_reservation_lateness_ns=0,
        errors=0,
        timeouts=0,
        evidence_valid=True,
    )
    value.update({key: 2 * group[key] for key in COUNTERS})
    if value["sample_count"]:
        value.update(p50_latency_ns=30, p95_latency_ns=30, p99_latency_ns=30)
    return value


def final_for(progress):
    return dict(
        schema="nbsr-b5-grouped-final-v1",
        groups=2,
        payload_bytes=1024,
        streams_per_group=1,
        outstanding_per_stream=1,
        measurement_duration_ns=progress["issue_deadline_ns"],
        drain_duration_ns=max(0, progress["elapsed_ns"] - progress["issue_deadline_ns"]),
        **{key: progress[key] for key in COUNTERS},
        group_counters=deepcopy(progress["group_counters"]),
        max_outstanding_observed=1,
        errors=0,
        timeouts=0,
        collector_overflow_count=0,
        all_groups_joined=True,
        source_cleanup={"status": "NOT_MEASURED"},
        evidence_valid=True,
    )


def test_accepts_contiguous_zero_completion_window_without_inventing_quantile():
    validator = ProgressValidator(groups=2, payload_bytes=1024)
    first = record()
    validator.accept(first)
    second = record(index=2, count=1)
    second.update(goodput_bytes_per_second=0, sample_count=0, p50_latency_ns=None, p95_latency_ns=None, p99_latency_ns=None)
    validator.accept(second)
    validator.finish(final_for(second))


@pytest.mark.parametrize("ids", [[0, 0], [0], [0, 2], [0, 1, 2]])
def test_requires_exact_unique_group_ids(ids):
    value = record()
    value["group_counters"] = [dict(value["group_counters"][0], group_id=g) for g in ids]
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


@pytest.mark.parametrize("second_index", [1, 3])
def test_duplicate_or_missing_window_is_rejected(second_index):
    validator = ProgressValidator(2, 1024)
    validator.accept(record())
    with pytest.raises(ValueError):
        validator.accept(record(index=second_index))


@pytest.mark.parametrize("bad", [True, 1.0, -1, "1"])
def test_counters_require_nonnegative_exact_integers(bad):
    value = record()
    value["completed"] = bad
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


def test_cumulative_operation_counters_cannot_go_backwards():
    validator = ProgressValidator(2, 1024)
    validator.accept(record(count=2))
    with pytest.raises(ValueError):
        validator.accept(record(index=2, count=1))


@pytest.mark.parametrize("field", COUNTERS)
def test_aggregate_must_equal_sum_of_groups(field):
    value = record()
    value[field] += 1
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


@pytest.mark.parametrize("change", [dict(offered=2), dict(issued=2, completed=2), dict(completed=2)])
def test_reconciled_group_sums_do_not_hide_invalid_budget_or_order(change):
    value = record()
    for group in value["group_counters"]:
        group.update(change)
    value.update({key: sum(group[key] for group in value["group_counters"]) for key in COUNTERS})
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


@pytest.mark.parametrize("change", [dict(sample_overflow_count=1), dict(errors=1), dict(timeouts=1), dict(evidence_valid=False)])
def test_failure_latches_and_cannot_be_recovered_by_a_later_good_record(change):
    validator = ProgressValidator(2, 1024)
    with pytest.raises(ValueError):
        validator.accept(dict(record(), **change))
    with pytest.raises(ValueError):
        validator.finish(final_for(record()))


def test_requires_progress_and_matching_unique_final():
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).finish(final_for(record()))
    validator = ProgressValidator(2, 1024)
    validator.accept(record())
    value = final_for(record())
    value["completed"] += 1
    with pytest.raises(ValueError):
        validator.finish(value)


def test_finished_validator_rejects_further_records_and_duplicate_final():
    validator = ProgressValidator(2, 1024)
    validator.accept(record(deadline=1_000_000_000))
    value = final_for(record(deadline=1_000_000_000))
    validator.finish(value)
    with pytest.raises(ValueError):
        validator.finish(value)
    with pytest.raises(ValueError):
        validator.accept(record(index=2))


def test_unreserved_current_is_a_gauge_not_a_monotonic_total():
    validator = ProgressValidator(2, 1024)
    first = record(count=0)
    for group in first["group_counters"]:
        group.update(offered=1, unreserved_current=1)
    first.update(offered=2, unreserved_current=2)
    validator.accept(first)
    second = record(index=2, count=1)
    validator.accept(second)
    validator.finish(final_for(second))


def test_global_quantile_is_not_reconstructed_from_group_quantiles():
    value = record()
    for group in value["group_counters"]:
        group["p99_latency_ns"] = 999
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


def test_retained_state_is_bounded_and_does_not_keep_raw_record_references():
    validator = ProgressValidator(2, 1024)
    for index in range(1, 1001):
        value = record(index=index, count=index, deadline=1_000_000_000_000)
        validator.accept(value)
        value["group_counters"][0]["completed"] = -1
    assert validator.retained_group_count == 2
    assert validator.retained_window_count <= 1
    validator.finish(final_for(record(index=1000, count=1000, deadline=1_000_000_000_000)))


def test_late_first_and_final_snapshot_may_straddle_deadline():
    validator = ProgressValidator(2, 1024)
    value = record(deadline=750_000_000)
    value["phase"] = "mixed"
    validator.accept(value)
    validator.finish(final_for(value))


def test_exact_deadline_boundary_needs_no_mixed_window():
    validator = ProgressValidator(2, 1024)
    first = record(deadline=1_000_000_000)
    validator.accept(first)
    second = record(index=2, count=1, deadline=1_000_000_000)
    second.update(phase="drain", goodput_bytes_per_second=0, sample_count=0, p50_latency_ns=None, p95_latency_ns=None, p99_latency_ns=None)
    validator.accept(second)
    validator.finish(final_for(second))


@pytest.mark.parametrize("phase,deadline", [("steady", 750_000_000), ("drain", 750_000_000), ("mixed", 1_000_000_000)])
def test_phase_must_match_actual_interval_not_scheduled_tick(phase, deadline):
    value = record(deadline=deadline)
    value["phase"] = phase
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


def test_deadline_cannot_change_between_windows():
    validator = ProgressValidator(2, 1024)
    validator.accept(record())
    with pytest.raises(ValueError):
        validator.accept(record(index=2, count=2, deadline=3_000_000_000))


def test_mixed_window_can_include_new_reservations_but_following_drain_cannot():
    validator = ProgressValidator(2, 1024)
    validator.accept(record(deadline=1_500_000_000))
    mixed = record(index=2, count=2, deadline=1_500_000_000)
    mixed["phase"] = "mixed"
    validator.accept(mixed)
    illegal = record(index=3, count=3, deadline=1_500_000_000)
    illegal["phase"] = "drain"
    with pytest.raises(ValueError):
        validator.accept(illegal)


def test_final_configured_duration_cannot_move_to_snapshot_time():
    validator = ProgressValidator(2, 1024)
    mixed = record(deadline=750_000_000)
    mixed["phase"] = "mixed"
    validator.accept(mixed)
    final = final_for(mixed)
    final.update(measurement_duration_ns=1_000_000_000, drain_duration_ns=0)
    with pytest.raises(ValueError):
        validator.finish(final)


def test_sample_ordinal_carries_between_windows_instead_of_resetting():
    validator = ProgressValidator(2, 1024)
    first = record(count=31)
    assert first["completed"] == 62 and first["sample_count"] == 0
    validator.accept(first)
    second = record(index=2, count=32)
    assert second["completed"] == 64 and second["sample_count"] == 1
    validator.accept(second)
    validator.finish(final_for(second))


@pytest.mark.parametrize("completed_per_group,samples", [(32, 0), (1, 1)])
def test_missing_or_invented_global_sample_is_rejected(completed_per_group, samples):
    value = record(count=completed_per_group)
    value.update(
        sample_count=samples,
        p50_latency_ns=30 if samples else None,
        p95_latency_ns=30 if samples else None,
        p99_latency_ns=30 if samples else None,
    )
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)


def test_one_sample_cannot_have_different_percentiles():
    value = record(count=32)
    assert value["sample_count"] == 1
    value["p95_latency_ns"] = 29
    value["p50_latency_ns"] = 28
    with pytest.raises(ValueError):
        ProgressValidator(2, 1024).accept(value)
