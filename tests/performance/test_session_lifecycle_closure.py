from __future__ import annotations

from scripts.performance.session_lifecycle_closure import analyze_path


def sample(phase: str, cycle: int, private: int, *, role: str = "destination") -> dict:
    return {
        "role": role,
        "phase": phase,
        "cycle": cycle,
        "working_set_bytes": private + 1_000_000,
        "private_bytes": private,
        "handle_count": 20,
        "thread_count": 4,
        "cpu_percent_assigned": 5.0,
    }


def test_analysis_derives_scaling_and_clean_cycles() -> None:
    cells = [
        {"kind": "streams", "active_count": count, "sessions": 1, "channels": 1, "streams": count,
         "samples": [sample("idle", 0, 10_000_000), sample("active", 0, 10_000_000 + count * 4096), sample("cooldown", 0, 10_010_000)],
         "cleanup": {"all_zero": True}}
        for count in (1, 8, 32, 64)
    ]
    cycles = {"kind": "cycles", "active_count": 64, "sessions": 1, "channels": 8, "streams": 64,
              "samples": sum(([sample("active", cycle, 11_000_000), sample("cooldown", cycle, 10_020_000 + cycle * 1000)] for cycle in range(5)), []),
              "cleanup": {"all_zero": True}}

    result = analyze_path("rust-rust", cells + [cycles])

    assert result["evidence"] == "PASS"
    assert result["lifecycle"] == "CLEAN"
    assert result["scaling"]["streams"]["private_bytes_per_resource"] > 0
    assert result["cycles"]["cooldown_private_slope_bytes_per_cycle"] == 1000


def test_analysis_preserves_nonzero_cleanup_as_resource_growth() -> None:
    cell = {"kind": "cycles", "active_count": 1, "sessions": 1, "channels": 1, "streams": 1,
            "samples": sum(([sample("active", cycle, 11_000_000), sample("cooldown", cycle, 10_000_000 + cycle * 1_000_000)] for cycle in range(5)), []),
            "cleanup": {"all_zero": False}}
    result = analyze_path("go-rust", [cell])
    assert result["evidence"] == "PASS"
    assert result["lifecycle"] == "RESOURCE-GROWTH"
