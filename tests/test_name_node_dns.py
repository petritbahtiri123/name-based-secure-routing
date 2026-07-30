from __future__ import annotations

import pytest

from nbsr.name_node import NameResolution
from nbsr.name_node_dns import NameNodeDnsAdapter
from nbsr.resolution_state import NameClassification


def name_resolution(*, expires_at: int = 160) -> NameResolution:
    return NameResolution(
        classification=NameClassification.NBSR_SERVICE,
        canonical_name="api.example",
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        route_id=b"r" * 16,
        expires_at=expires_at,
    )


class FakeNameNode:
    def __init__(self, resolution: NameResolution) -> None:
        self.resolution = resolution
        self.calls: list[tuple[str, int]] = []

    def resolve(self, presentation_name: str, *, now: int) -> NameResolution:
        self.calls.append((presentation_name, now))
        return self.resolution


def test_adapter_exposes_only_synthetic_client_route() -> None:
    resolution = name_resolution()
    node = FakeNameNode(resolution)
    adapter = NameNodeDnsAdapter(node, now=lambda: 100)

    route = adapter("api.example")

    assert route.hostname == resolution.canonical_name
    assert route.synthetic_ipv4 == resolution.synthetic_ipv4
    assert route.synthetic_ipv6 == resolution.synthetic_ipv6
    assert route.route_binding == resolution.route_id.hex()
    assert route.expires_in == 60
    assert "origin" not in vars(route)
    assert node.calls == [("api.example", 100)]


@pytest.mark.parametrize(
    ("expires_at", "expected"),
    (
        (99, 1),
        (100, 1),
        (101, 1),
        (130, 30),
        (160, 60),
        (1_000, 60),
    ),
)
def test_adapter_clamps_client_lifetime_independently(expires_at: int, expected: int) -> None:
    adapter = NameNodeDnsAdapter(
        FakeNameNode(name_resolution(expires_at=expires_at)),
        now=lambda: 100,
    )

    route = adapter("api.example")

    assert route.expires_in == expected
