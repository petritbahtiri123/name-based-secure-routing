from __future__ import annotations

from scripts.performance.cpu_efficiency import analyze_repeat, classify_cells
from scripts.performance.windows_affinity import affinity_mask


def test_affinity_mask_uses_exact_low_order_processors() -> None:
    assert affinity_mask(1, 8) == 0b00000001
    assert affinity_mask(2, 8) == 0b00000011
    assert affinity_mask(4, 8) == 0b00001111


def test_cpu_derivations_use_total_process_cpu_time() -> None:
    result = analyze_repeat(
        {
            "path": "nbsr",
            "payload_bytes": 1024,
            "streams": 64,
            "completed_operations": 1000,
            "measured_ns": 2_000_000_000,
            "aggregate_application_gbps": 0.008192,
            "resources": {
                "total_cpu_ns": 1_000_000_000,
                "roles": {
                    "source": {"cpu_ns": 600_000_000},
                    "destination": {"cpu_ns": 400_000_000},
                },
            },
            "affinity": {"requested_processors": 2, "verified": True},
            "errors": 0,
            "timeouts": 0,
        }
    )

    assert result["operations_per_second"] == 500
    assert result["cpu_ns_per_operation"] == 1_000_000
    assert result["effective_cores"] == 0.5
    assert result["effective_cores_by_role"] == {"source": 0.3, "destination": 0.2}
    assert result["gbit_per_second_per_effective_core"] == 0.016384


def test_invalid_affinity_or_errors_fail_closed() -> None:
    repeat = {
        "path": "nbsr",
        "payload_bytes": 1024,
        "streams": 64,
        "completed_operations": 1,
        "measured_ns": 1,
        "aggregate_application_gbps": 1.0,
        "resources": {"total_cpu_ns": 1},
        "affinity": {"requested_processors": 2, "verified": False},
        "errors": 0,
        "timeouts": 0,
    }
    assert analyze_repeat(repeat)["valid"] is False
    repeat["affinity"]["verified"] = True
    repeat["errors"] = 1
    assert analyze_repeat(repeat)["valid"] is False


def test_classification_does_not_invent_a_bottleneck() -> None:
    cells = [
        {
            "path": "nbsr",
            "payload_bytes": 1024,
            "streams": 64,
            "processors": cores,
            "median_operations_per_second": ops,
            "median_effective_cores": effective,
            "median_peak_role_effective_cores": peak_role,
            "valid_repeats": 3,
            "repeat_count": 3,
        }
        for cores, ops, effective, peak_role in ((1, 100, 0.9, 0.7), (2, 170, 1.7, 1.0), (4, 180, 1.8, 1.1))
    ]
    result = classify_cells(cells)
    assert result["evidence"] == "PASS"
    assert result["system"] == "SOFTWARE-LIMITED"


def test_classification_requires_per_process_cpu_saturation() -> None:
    cells = [
        {
            "path": "nbsr",
            "payload_bytes": 1024,
            "streams": 64,
            "processors": cores,
            "median_operations_per_second": ops,
            "median_effective_cores": effective,
            "median_peak_role_effective_cores": peak_role,
            "valid_repeats": 3,
            "repeat_count": 3,
        }
        for cores, ops, effective, peak_role in ((1, 100, 1.6, 0.95), (2, 170, 3.0, 1.9), (4, 180, 4.1, 3.8))
    ]
    assert classify_cells(cells)["system"] == "CPU-LIMITED"
