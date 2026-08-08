from __future__ import annotations

import pytest

from scripts.performance.model import BenchmarkState, Scenario


def test_cold_and_warm_states_cannot_be_confused() -> None:
    state = BenchmarkState()
    assert state.classify("service-00") is Scenario.NBSR_COLD
    state.establish_transport()
    assert state.classify("service-00") is Scenario.NBSR_WARM_NEW_SERVICE
    state.admit_service("service-00", b"A" * 16)
    assert state.classify("service-00") is Scenario.NBSR_WARM_EXISTING_SERVICE


def test_existing_service_reuses_admission_and_new_service_does_not() -> None:
    state = BenchmarkState()
    state.establish_transport()
    state.admit_service("service-00", b"A" * 16)
    state.open_stream("service-00", 4)
    state.open_stream("service-00", 8)
    assert state.federation_admissions == 1
    assert state.route_admissions == 1
    assert state.stream_admissions == 2
    state.admit_service("service-01", b"B" * 16)
    assert state.federation_admissions == 2
    assert state.route_admissions == 2


def test_one_transport_serves_twenty_independent_services() -> None:
    state = BenchmarkState()
    state.establish_transport()
    for index in range(20):
        state.admit_service(f"service-{index:02d}", index.to_bytes(16, "big"))
    assert state.transport_sessions == 1
    assert state.service_channels == 20
    assert len(state.channel_ids) == 20
    assert state.federation_admissions == 20


def test_channel_and_stream_authority_cannot_be_forged_by_instrumentation() -> None:
    state = BenchmarkState()
    state.establish_transport()
    with pytest.raises(ValueError, match="service is not admitted"):
        state.open_stream("service-00", 4)
    state.admit_service("service-00", b"A" * 16)
    state.open_stream("service-00", 4)
    with pytest.raises(ValueError, match="stream replay"):
        state.open_stream("service-00", 4)
