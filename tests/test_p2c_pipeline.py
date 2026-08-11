from __future__ import annotations

import pytest

from scripts.performance.p2c_pipeline import acceptance, select_window, validate_windows


def cell(window: int, throughput: float, p99: float, errors: int = 0) -> dict:
    return {
        "window": window,
        "throughput": throughput,
        "p99_ns": p99,
        "errors": errors,
        "pending_high_water": window,
    }


def test_only_approved_small_windows_are_accepted() -> None:
    assert validate_windows([1, 2, 4, 8, 16]) == [1, 2, 4, 8, 16]
    for values in ([0], [3], [17], [1, 2, 2]):
        with pytest.raises(ValueError):
            validate_windows(values)


def test_selects_smallest_window_with_most_of_saturated_benefit() -> None:
    cells = [cell(1, 100, 100), cell(2, 135, 101), cell(4, 148, 102), cell(8, 150, 103)]
    assert select_window(cells) == 4


def test_acceptance_uses_medians_and_enforces_all_hard_gates() -> None:
    before = [cell(1, value, 100) for value in (99, 100, 101)]
    after = [cell(4, value, 104) for value in (111, 112, 113)]
    result = acceptance(before, after, security_pass=True, quality_pass=True, soak_pass=True)
    assert result["throughput_improvement"] == pytest.approx(0.12)
    assert result["p99_change"] == pytest.approx(0.04)
    assert result["keep"] is True
    after[1]["errors"] = 1
    assert acceptance(before, after, security_pass=True, quality_pass=True, soak_pass=True)["keep"] is False
