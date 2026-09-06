"""Linux private-resident accounting must not become Windows private bytes."""

import pytest

from scripts.run_b5_v2 import LiveGuards


def guards():
    return LiveGuards(groups=1, max_progress=10, max_resources=100,
                      resource_basis="linux_private_resident")


def progress():
    return dict(phase="steady", elapsed_ns=3_000_000_000,
                goodput_bytes_per_second=100, p99_latency_ns=100)


def test_linux_growth_keeps_the_same_fail_threshold():
    value = guards()
    for index in range(4):
        value.resource(dict(role="source", timestamp_ns=100 + index * 1_000_000_000,
                            private_resident_bytes=100 + index * 100))
    with pytest.raises(RuntimeError, match="private growth: source"):
        value.progress(progress(), received_ns=3_000_000_100)


def test_linux_terminal_null_is_not_zero_or_a_live_memory_sample():
    value = guards()
    for role in ("source", "destination_0"):
        for index in range(3):
            value.resource(dict(role=role, timestamp_ns=100 + index * 1_000_000_000,
                                private_resident_bytes=100))
        value.resource(dict(role=role, timestamp_ns=3_000_000_100,
                            state="Z", memory_state="UNAVAILABLE_ZOMBIE",
                            private_resident_bytes=None))
    value.progress(progress(), received_ns=3_000_000_100)
    result = value.qualification()
    assert result["resource_series_available"] is False
    assert result["resource_memory_metric"] == "private_resident_bytes"
    assert result["resource_sample_clock"] == "timestamp_ns"


@pytest.mark.parametrize("change", [{}, {"state": "S"}, {"state": "Z", "memory_state": "MEASURED"}])
def test_linux_unavailable_live_memory_is_a_failure(change):
    with pytest.raises(RuntimeError, match="memory"):
        guards().resource(dict(role="source", timestamp_ns=100,
                               private_resident_bytes=None, **change))


def test_linux_clock_cannot_be_silently_substituted():
    with pytest.raises(RuntimeError, match="clock"):
        guards().resource(dict(role="source", monotonic_timestamp_ns=100,
                               private_resident_bytes=100))
