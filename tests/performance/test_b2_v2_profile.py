from __future__ import annotations

import pytest
import scripts.profile_b2_v2 as profile

from scripts.profile_b2_v2 import (
    classify_attribution,
    preferred_physical_masks,
    validate_profile_pair,
)


def test_diagnostic_matrix_can_select_one_matched_direct_nbsr_workload() -> None:
    assert hasattr(profile, "benchmark_cells"), "diagnostic matrix selection is not implemented"
    assert profile.benchmark_cells(
        payloads=(16384,),
        paths=("direct", "nbsr"),
        affinities=(4,),
        streams=(8,),
        outstanding_per_stream=(1,),
    ) == [
        {"path": "direct", "streams": 8, "payload_bytes": 16384, "affinity": 4, "outstanding_per_stream": 1},
        {"path": "nbsr", "streams": 8, "payload_bytes": 16384, "affinity": 4, "outstanding_per_stream": 1},
    ]


def test_benchmark_only_stream_and_outstanding_bounds_are_explicit() -> None:
    root = profile.ROOT
    source = (root / "crates/nbsr-transport/src/bin/perf_rust_source.rs").read_text(encoding="utf-8")
    destination = (root / "crates/nbsr-transport/src/bin/wp8_interop_server.rs").read_text(encoding="utf-8")
    direct = (root / "crates/nbsr-transport/src/bin/perf_direct_peer.rs").read_text(encoding="utf-8")
    for text in (source, destination, direct):
        assert "(1..=64).contains(&stream_count)" in text
    for text in (source, direct):
        assert '"--p2a-outstanding-per-stream"' in text


def test_full_postflight_validation_is_outside_measured_interval() -> None:
    root = profile.ROOT
    for relative in (
        "crates/nbsr-transport/src/bin/perf_rust_source.rs",
        "crates/nbsr-transport/src/bin/perf_direct_peer.rs",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        measured = text.index("let measured_ns = measured_started.elapsed().as_nanos();")
        postflight = text.index("let postflight = encode_frame")
        assert measured < postflight


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
