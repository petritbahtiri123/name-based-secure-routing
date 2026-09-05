import pytest

from scripts.run_b3_v2 import spec_for
from scripts.performance.b3_v2_analysis import analyze_scale


def test_default_stream_shape_remains_eight_channels():
    spec = spec_for("streams", 512, 1, materialized_streams=True)
    assert (spec["channels"], spec["streams"], spec["active_count"]) == (8, 64, 512)
    assert spec["name"] == "streams-512-r1"


def test_explicit_wide_series_uses_existing_authority_and_credit_bounds():
    spec = spec_for("streams", 2048, 1, materialized_streams=True, fixed_channels=32)
    assert (spec["channels"], spec["streams"], spec["active_count"]) == (32, 64, 2048)
    assert spec["name"] == "streams-c32-2048-r1"
    assert "32 fixed channels" in spec["resource_scope"]
    assert spec["materialized_streams"] is True


@pytest.mark.parametrize("count,channels", [(0, 32), (33, 32), (2080, 32), (1024, 8),
                                          (64, 0), (64, 33), (64, True)])
def test_invalid_partition_or_authority_bound_is_rejected(count, channels):
    with pytest.raises(ValueError):
        spec_for("streams", count, 1, fixed_channels=channels)


def test_other_axes_cannot_silently_ignore_fixed_channel_override():
    with pytest.raises(ValueError):
        spec_for("bundles", 32, 1, fixed_channels=32)


def test_memory_regression_refuses_to_pool_different_fixed_channel_costs():
    cells = [{"name": str(channels), "kind": "streams", "active_count": 32,
              "materialized_streams": True, "resource_scope": f"{channels} fixed channels",
              "cleanup": {"all_zero": True},
              "samples": [{"role": role, "phase": phase, "private_bytes": channels * 1000,
                           "working_set_bytes": 1000, "handle_count": 10, "thread_count": 4}
                          for role in ("source", "destination") for phase in ("idle", "active")]}
             for channels in (8, 32)]
    with pytest.raises(ValueError, match="resource scope"):
        analyze_scale(cells)
