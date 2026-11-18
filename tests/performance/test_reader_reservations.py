import io
import pytest
from scripts.performance import reader_output_limits as limits
from scripts.performance import reader_phase_budget as budget


def test_existing_bytes_plus_remaining_reservations_not_double_counted():
    counts = dict(output=575, task=6739946464, artifacts=575)
    value = budget.project(counts, {"a": 100, "b": 200}, {"c": 50}, {"a": 50, "c": 20}, 5, aux_cap=60, cleanup_cap=80, output_cap=1000)
    assert value["projected_output"] == 940
    assert value["remaining_cleanup"] == 60


def test_aggregate_overflow_rejected_even_when_each_slot_fits():
    with pytest.raises(ValueError):
        budget.project(
            dict(output=561, task=6739946464, artifacts=561),
            {"a": 100, "b": 200},
            {"c": 50},
            {},
            0,
            aux_cap=60,
            cleanup_cap=80,
            output_cap=1000,
        )


def test_duplicate_fixed_purpose_rejected():
    b = limits.ClaimBook()
    p = limits.purpose_for_path("live-lab/reader-command/stdout.log")
    b.claim(p)
    with pytest.raises(ValueError):
        b.claim(p)


def test_real_writer_overflow_and_partial_write_latch():
    claim = limits.live_reader_claims(limits.ClaimBook())["stdout.log"]

    class Short:
        def write(self, raw):
            return len(raw) - 1

        def flush(self):
            pass

    writer = limits.BoundedWriter(claim, Short())
    with pytest.raises(limits.OutputLimitError):
        writer.write(b"abc")
    assert claim.reserved_bytes == 3
    with pytest.raises(limits.OutputLimitError):
        limits.BoundedWriter(claim, io.BytesIO())


def test_real_writer_cap_applies_to_shared_aliases():
    claim = limits.live_reader_claims(limits.ClaimBook())["stdout.log"]
    a = limits.BoundedWriter(claim, io.BytesIO())
    b = limits.BoundedWriter(claim, io.BytesIO())
    a.write(b"x" * claim.maximum_bytes)
    with pytest.raises(limits.OutputLimitError):
        b.write(b"x")
    assert claim.reserved_bytes == claim.maximum_bytes


def test_growth_between_scans_is_charged_before_projection():
    counts = budget.align(dict(output=500, task=6739946464, artifacts=500, phase_root=100), 200)
    assert counts["output"] == 600
    with pytest.raises(ValueError):
        budget.project(counts, {"a": 500}, {}, {}, 0, aux_cap=0, cleanup_cap=0, output_cap=1000)


def test_approved_170_mib_does_not_relax_global_task_cap():
    # Approval changes only output_cap, not the global task/artifacts boundary.
    global_cap = 6739946464 + 378 * 1024**2
    with pytest.raises(ValueError, match="global remaining obligations"):
        budget.project(
            dict(output=142410748, task=global_cap, artifacts=global_cap),
            {"a": 1},
            {},
            {},
            0,
            aux_cap=0,
            cleanup_cap=0,
            output_cap=170 * 1024**2,
        )


def test_full_successor_envelope_includes_preparation_source_and_cleanup():
    normal = {"source_and_config": 4194304, "preparation": 5474304, "normal": 13074432, "additional_margin": 2097152}
    result = budget.project(
        dict(output=142410748, task=7104449818, artifacts=7104449818),
        normal,
        {},
        {},
        0,
        aux_cap=1048576,
        cleanup_cap=2097152,
        output_cap=170 * 1024**2,
    )
    assert result["remaining_total"] == 27985920
    assert result["projected_output"] == 170396668
    assert result["projected_task"] == 7132435738


def test_live_fixed_grants_reserve_once_without_minting_spare():
    book = limits.ClaimBook()
    whole, grants = limits.live_partition_claims(book)
    assert whole.reserved_bytes == sum(c.maximum_bytes for c in grants.values()) == 2492 * 1024
    assert whole.maximum_bytes == 2608 * 1024
    assert grants["completion_shared"].purpose == "live/completion"
    assert "receiver_receipts" not in grants
    with pytest.raises(ValueError):
        limits.live_partition_claims(book)
    limits.mark_unknown(grants["producer_capture"], "partial_write")
    assert whole.reserved_bytes == 2492 * 1024
    with pytest.raises(limits.OutputLimitError):
        limits.charge_alias(grants["producer_capture"], 0)


def test_every_live_grant_enforces_its_fixed_maximum():
    for name in limits._LIVE_PARTITIONS:
        _, grants = limits.live_partition_claims(limits.ClaimBook())
        claim = grants[name]
        limits.charge_alias(claim, claim.maximum_bytes)
        with pytest.raises(limits.OutputLimitError):
            limits.charge_alias(claim, 1)
