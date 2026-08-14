from __future__ import annotations

import itertools
import random

import pytest

from scripts.performance.bounded_replay_model import (
    FullHistoryOracle,
    MAX_STREAM_ORDINAL,
    SlidingWindow,
    StrictHighWater,
    compare_candidate,
    run_investigation,
)


def test_strict_high_water_matches_sequential_history_but_rejects_valid_reordering() -> None:
    sequential = [4, 8, 12, 16, 4, 12]
    assert compare_candidate(sequential, StrictHighWater()) == {
        "events": 6,
        "false_accepts": 0,
        "false_rejects": 0,
        "maximum_state_entries": 1,
    }

    reordered_distinct = [12, 4, 8]
    assert compare_candidate(reordered_distinct, StrictHighWater()) == {
        "events": 3,
        "false_accepts": 0,
        "false_rejects": 2,
        "maximum_state_entries": 1,
    }


def test_finite_sliding_window_rejects_unseen_id_after_an_unbounded_legal_gap() -> None:
    for window in (1, 2, 4, 8, 16, 64, 1_024):
        # QUIC stream ordinals are modeled after removing the fixed low two bits.
        sequence = [0, window + 1, 1]
        result = compare_candidate(sequence, SlidingWindow(window))
        assert result["false_accepts"] == 0
        assert result["false_rejects"] == 1
        assert result["maximum_state_entries"] <= window


def test_exhaustive_concurrent_style_permutations_expose_high_water_false_rejects() -> None:
    totals = {"events": 0, "false_accepts": 0, "false_rejects": 0}
    for permutation in itertools.permutations((0, 1, 2, 3, 4, 5)):
        result = compare_candidate(list(permutation), StrictHighWater())
        for key in totals:
            totals[key] += result[key]
    assert totals == {
        "events": 4_320,
        "false_accepts": 0,
        "false_rejects": 2_556,
    }


def test_seeded_property_sequences_preserve_oracle_duplicate_rejection() -> None:
    generator = random.Random(0x503143)
    for _ in range(2_000):
        values = generator.sample(range(0, 4_096), 32)
        duplicate_positions = generator.sample(range(32), 8)
        sequence = values + [values[index] for index in duplicate_positions]
        generator.shuffle(sequence)

        oracle = FullHistoryOracle()
        accepted: set[int] = set()
        for stream_ordinal in sequence:
            expected = stream_ordinal not in accepted
            assert oracle.observe(stream_ordinal) is expected
            if expected:
                accepted.add(stream_ordinal)


def test_identifier_boundaries_and_fresh_session_scope_are_explicit() -> None:
    sequence = [0, MAX_STREAM_ORDINAL, MAX_STREAM_ORDINAL - 1, 0]
    assert compare_candidate(sequence, FullHistoryOracle()) == {
        "events": 4,
        "false_accepts": 0,
        "false_rejects": 0,
        "maximum_state_entries": 3,
    }

    old_session = FullHistoryOracle()
    new_session = FullHistoryOracle()
    assert old_session.observe(1) is True
    assert old_session.observe(1) is False
    assert new_session.observe(1) is True


def test_every_candidate_handles_maximum_without_overflow_and_rejects_invalid_domain() -> None:
    for candidate in (
        FullHistoryOracle(),
        StrictHighWater(),
        SlidingWindow(4),
    ):
        assert candidate.observe(MAX_STREAM_ORDINAL - 1) is True
        assert candidate.observe(MAX_STREAM_ORDINAL) is True
        assert candidate.observe(MAX_STREAM_ORDINAL) is False
        state_before_invalid = candidate.state_entries
        with pytest.raises(ValueError, match="outside legal QUIC stream ordinal domain"):
            candidate.observe(-1)
        with pytest.raises(ValueError, match="outside legal QUIC stream ordinal domain"):
            candidate.observe(MAX_STREAM_ORDINAL + 1)
        assert candidate.state_entries == state_before_invalid


def test_reproducible_investigation_reports_candidate_divergence() -> None:
    result = run_investigation()
    assert result["seed"] == 0x503143
    assert result["generated_sequences"] == 10_000
    assert result["generated_events"] == 800_000
    assert result["oracle"] == {
        "false_accepts": 0,
        "false_rejects": 0,
        "maximum_state_entries": 64,
    }
    assert result["strict_high_water"]["false_accepts"] == 0
    assert result["strict_high_water"]["false_rejects"] > 0
    for candidate in result["sliding_windows"]:
        assert candidate["false_accepts"] == 0
        assert candidate["false_rejects"] > 0
        assert candidate["maximum_state_entries"] <= candidate["window_ordinals"]
        assert candidate["bitmap_bits"] == candidate["window_ordinals"]
        assert candidate["bitmap_payload_bytes"] == 8 + (candidate["window_ordinals"] + 7) // 8
