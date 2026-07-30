"""DNS-compatible synthetic response adapter for the WP2A Name Node."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from nbsr.dns_stub import ClientRoute
from nbsr.name_node import NameResolution
from nbsr.protocol import ErrorCode, ProtocolViolation
from nbsr.protocol.fields import require_timestamp


class NameNodeResolver(Protocol):
    def resolve(
        self,
        presentation_name: str,
        *,
        now: int,
    ) -> NameResolution: ...


class NameNodeDnsAdapter:
    """Convert private Name Node state into the existing synthetic route shape."""

    def __init__(
        self,
        name_node: NameNodeResolver,
        *,
        now: Callable[[], int],
    ) -> None:
        if not callable(getattr(name_node, "resolve", None)) or not callable(now):
            raise TypeError("Name Node adapter dependencies must be callable")
        self._name_node = name_node
        self._now = now

    def __call__(self, canonical_name: str) -> ClientRoute:
        current = require_timestamp(self._now(), message="Invalid Name Node adapter time")
        resolution = self._name_node.resolve(canonical_name, now=current)
        if type(resolution) is not NameResolution:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_INTERNAL,
                "Name Node returned an invalid result",
            )
        return ClientRoute(
            hostname=resolution.canonical_name,
            synthetic_ipv4=resolution.synthetic_ipv4,
            synthetic_ipv6=resolution.synthetic_ipv6,
            route_binding=resolution.route_id.hex(),
            expires_in=max(1, min(60, resolution.expires_at - current)),
        )
