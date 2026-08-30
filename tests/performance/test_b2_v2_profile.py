from __future__ import annotations

import pytest

from scripts.profile_b2_v2 import (
    classify_attribution,
    preferred_physical_masks,
    validate_profile_pair,
)


def test_prefers_one_logical_processor_per_physical_core() -> None:
    cores = [
        {"logical_mask": 0x11},
        {"logical_mask": 0x22},
        {"logical_mask": 0x44},
        {"logical_mask": 0x88},
    ]
    assert preferred_physical_masks(cores, (1, 2, 4)) == {1: 0x01, 2: 0x03, 4: 0x0F}


def test_profile_pair_requires_verified_affinity_and_bounded_overhead() -> None:
    pair = {
        "control": {"operations_per_second": 1000, "affinity_verified": True},
        "profile": {"operations_per_second": 970, "affinity_verified": True},
        "symbol_resolution_percent": 100.0,
    }
    assert validate_profile_pair(pair)["valid"] is True
    pair["profile"]["operations_per_second"] = 940
    assert validate_profile_pair(pair)["valid"] is False


def test_hardware_limit_is_prohibited_without_measured_saturation() -> None:
    with pytest.raises(ValueError, match="hardware saturation"):
        classify_attribution(
            plateau_reproduced=True,
            hotspot={"owner": "CPU", "share": 0.40},
            host_resource_saturation=False,
            requested="HARDWARE-LIMITED",
        )


def test_pass_requires_reproduced_named_hotspot_of_at_least_fifteen_percent() -> None:
    assert classify_attribution(
        plateau_reproduced=True,
        hotspot={"owner": "one-outstanding-response-wait", "share": 0.61},
        host_resource_saturation=False,
    ) == {"evidence": "PASS", "system": "HARNESS-LIMITED:one-outstanding-response-wait"}
    assert classify_attribution(
        plateau_reproduced=True,
        hotspot={"owner": "ambiguous", "share": 0.14},
        host_resource_saturation=False,
    )["evidence"] == "PARTIAL"
