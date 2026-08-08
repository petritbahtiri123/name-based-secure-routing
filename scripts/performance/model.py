from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Scenario(str, Enum):
    NBSR_COLD = "nbsr-cold"
    NBSR_WARM_NEW_SERVICE = "nbsr-warm-new-service"
    NBSR_WARM_EXISTING_SERVICE = "nbsr-warm-existing-service"


@dataclass
class BenchmarkState:
    transport_sessions: int = 0
    federation_admissions: int = 0
    route_admissions: int = 0
    stream_admissions: int = 0
    _channels: dict[str, bytes] = field(default_factory=dict)
    _streams: set[tuple[str, int]] = field(default_factory=set)

    @property
    def service_channels(self) -> int:
        return len(self._channels)

    @property
    def channel_ids(self) -> frozenset[bytes]:
        return frozenset(self._channels.values())

    def classify(self, service_id: str) -> Scenario:
        if self.transport_sessions == 0:
            return Scenario.NBSR_COLD
        if service_id not in self._channels:
            return Scenario.NBSR_WARM_NEW_SERVICE
        return Scenario.NBSR_WARM_EXISTING_SERVICE

    def establish_transport(self) -> None:
        if self.transport_sessions != 0:
            raise ValueError("transport is already established")
        self.transport_sessions = 1

    def admit_service(self, service_id: str, channel_id: bytes) -> None:
        if self.transport_sessions != 1:
            raise ValueError("transport is not established")
        if not service_id or len(channel_id) != 16:
            raise ValueError("invalid service authority")
        if service_id in self._channels or channel_id in self._channels.values():
            raise ValueError("service or channel replay")
        self._channels[service_id] = bytes(channel_id)
        self.federation_admissions += 1
        self.route_admissions += 1

    def open_stream(self, service_id: str, stream_id: int) -> None:
        if service_id not in self._channels:
            raise ValueError("service is not admitted")
        key = (service_id, stream_id)
        if key in self._streams:
            raise ValueError("stream replay")
        self._streams.add(key)
        self.stream_admissions += 1
