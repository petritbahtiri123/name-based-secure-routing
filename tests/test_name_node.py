from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from nbsr.legacy_origin import (
    LegacyDnsResult,
    LegacyDnsSnapshot,
    LegacyOriginCache,
)
from nbsr.name_node import LegacyServicePolicy, NameNode, NbsrServicePolicy
from nbsr.originset import DnssecStatus, OriginEndpoint
from nbsr.protocol import ErrorCode, ProtocolViolation, ServiceRecord
from nbsr.resolution_state import NameClassification, ResolutionContextStore
from nbsr.synthetic import SyntheticAddressPool


def nbsr_policy(**changes: object) -> NbsrServicePolicy:
    values = {
        "canonical_name": "api.example",
        "source_operator_id": "source.operator",
        "source_edge_id": "source.edge",
        "policy_hash": b"p" * 32,
    }
    values.update(changes)
    return NbsrServicePolicy(**values)


def legacy_policy(**changes: object) -> LegacyServicePolicy:
    values = {
        "canonical_name": "legacy.example",
        "service_id": "legacy.service",
        "service_record_generation": 1,
        "source_operator_id": "source.operator",
        "source_edge_id": "source.edge",
        "destination_operator_id": "destination.operator",
        "destination_edge_set": ("edge.a", "edge.b"),
        "allowed_ports": (80, 443),
        "policy_hash": b"p" * 32,
        "issuer_id": b"legacy-issuer",
        "origin_name": "origin.example",
        "allowed_networks": ("192.0.2.0/24", "2001:db8::/32"),
    }
    values.update(changes)
    return LegacyServicePolicy(**values)


@pytest.mark.parametrize(
    ("factory", "changes"),
    (
        (nbsr_policy, {"canonical_name": "API.example"}),
        (nbsr_policy, {"canonical_name": "192.0.2.1"}),
        (nbsr_policy, {"source_operator_id": "not valid"}),
        (nbsr_policy, {"policy_hash": b"short"}),
        (legacy_policy, {"service_record_generation": True}),
        (legacy_policy, {"destination_edge_set": ("edge.b", "edge.a")}),
        (legacy_policy, {"destination_edge_set": ("edge.a", "edge.a")}),
        (legacy_policy, {"allowed_ports": (443, 80)}),
        (legacy_policy, {"allowed_ports": (80, 80)}),
        (legacy_policy, {"allowed_ports": (True,)}),
        (legacy_policy, {"policy_hash": b"short"}),
        (legacy_policy, {"issuer_id": b""}),
        (legacy_policy, {"origin_name": ""}),
        (legacy_policy, {"origin_name": "192.0.2.8"}),
        (legacy_policy, {"allowed_networks": ("0.0.0.0/0",)}),
        (legacy_policy, {"allowed_networks": ("192.0.2.0/24", "10.0.0.0/8")}),
        (legacy_policy, {"allowed_networks": ("192.0.2.0/24", "192.0.2.0/24")}),
    ),
)
def test_policy_rejects_noncanonical_or_unbounded_values(factory, changes) -> None:
    with pytest.raises(ProtocolViolation):
        factory(**changes)


def test_policy_objects_are_immutable() -> None:
    policy = legacy_policy()

    with pytest.raises((FrozenInstanceError, AttributeError)):
        policy.allowed_ports = (443,)

    assert replace(policy) == policy


def service_record(**changes: object) -> ServiceRecord:
    values = {
        "record_version": 1,
        "canonical_name": "api.example",
        "sequence": 7,
        "owner_key_id": b"owner",
        "service_id": "api.service",
        "destination_operator_id": "destination.operator",
        "destination_edge_set": ("edge.a", "edge.b"),
        "origin_connector_id": "connector.a",
        "transports": ("tcp",),
        "ports": (80, 443),
        "route_profiles": ("nbsr-quic-1",),
        "publication_mode": "nbsr-secure-only",
        "not_before": 50,
        "not_after": 500,
        "revocation_ref": "revocation.api",
    }
    values.update(changes)
    return ServiceRecord(**values)


class StaticRegistry:
    def __init__(self, result: ServiceRecord | Exception | None):
        self.result = result

    def resolve(self, canonical_name: str, *, now: int) -> ServiceRecord | None:
        assert canonical_name == "api.example"
        assert now == 100 or now == 101
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class CountingLegacyProvider:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request, now):
        self.calls += 1
        raise AssertionError("legacy provider must not be called")


class SequentialIds:
    def __init__(self, values: tuple[bytes, ...] | None = None) -> None:
        self.values = list(
            values
            or (
                b"c" * 32,
                b"r" * 16,
                b"l" * 16,
                b"d" * 32,
                b"s" * 16,
                b"m" * 16,
            )
        )
        self.requested_lengths: list[int] = []

    def __call__(self, length: int) -> bytes:
        self.requested_lengths.append(length)
        return self.values.pop(0)


_DEFAULT_RECORD = object()


def configured_nbsr_node(
    registry_result: ServiceRecord | ProtocolViolation | None | object = _DEFAULT_RECORD,
    *,
    provider: CountingLegacyProvider | None = None,
    ids: SequentialIds | None = None,
) -> tuple[NameNode, ResolutionContextStore, SequentialIds]:
    identifier_source = ids or SequentialIds()
    store = ResolutionContextStore(max_entries=8)
    node = NameNode(
        StaticRegistry(service_record() if registry_result is _DEFAULT_RECORD else registry_result),
        (nbsr_policy(),),
        (),
        provider or CountingLegacyProvider(),
        lambda _request, _endpoint: True,
        LegacyOriginCache(max_entries=8),
        SyntheticAddressPool(
            "127.80.0.0/29",
            "fd00:6e62:7372::/125",
            ttl_seconds=60,
        ),
        store,
        identifier_source,
    )
    return node, store, identifier_source


def test_valid_signed_name_returns_only_stable_synthetic_state() -> None:
    node, store, ids = configured_nbsr_node()

    first = node.resolve("API.EXAMPLE.", now=100)
    second = node.resolve("api.example", now=101)
    first_binding = store.lookup(first.synthetic_ipv4, now=100)
    second_binding = store.lookup(second.synthetic_ipv6, now=101)

    assert first.synthetic_ipv4 == second.synthetic_ipv4
    assert first.synthetic_ipv6 == second.synthetic_ipv6
    assert first.classification is NameClassification.NBSR_SERVICE
    assert first.canonical_name == "api.example"
    assert first.expires_at == 400
    assert first.route_id == b"r" * 16
    assert second.route_id == b"s" * 16
    assert not hasattr(first, "originset")
    assert not hasattr(first, "origin_address")
    assert first_binding is not None
    assert first_binding.originset is None
    assert first_binding.route_intent.service_id == "api.service"
    assert first_binding.route_intent.record_sequence == 7
    assert first_binding.route_intent.destination_edge_set == ("edge.a", "edge.b")
    assert first_binding.route_intent.allowed_ports == (80, 443)
    assert second_binding is not None
    assert second_binding.resolution_context_id == b"d" * 32
    assert ids.requested_lengths == [32, 16, 16, 32, 16, 16]
    assert first_binding.mapping.expires_at >= datetime.fromtimestamp(400, UTC)


@pytest.mark.parametrize(
    "failure",
    (
        None,
        ProtocolViolation(ErrorCode.NBSR_E_RECORD_UNTRUSTED, "bad signature"),
        ProtocolViolation(ErrorCode.NBSR_E_RECORD_STALE, "stale"),
        ProtocolViolation(ErrorCode.NBSR_E_RECORD_REVOKED, "revoked"),
    ),
)
def test_invalid_configured_nbsr_name_never_downgrades_to_legacy(failure) -> None:
    provider = CountingLegacyProvider()
    node, _, _ = configured_nbsr_node(failure, provider=provider)

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("api.example", now=100)

    expected = ErrorCode.NBSR_E_RECORD_UNTRUSTED if failure is None else failure.code
    assert caught.value.code is expected
    assert provider.calls == 0


@pytest.mark.parametrize(
    "values",
    (
        (b"short", b"r" * 16, b"l" * 16),
        (b"c" * 32, b"same-route-lease", b"same-route-lease"),
    ),
)
def test_invalid_or_reused_identifiers_fail_before_binding(values) -> None:
    node, store, _ = configured_nbsr_node(ids=SequentialIds(values))

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("api.example", now=100)

    assert caught.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED
    assert store.lookup("127.80.0.1", now=100) is None


def test_unexpected_registry_failure_is_non_sensitive_internal_error() -> None:
    node, _, _ = configured_nbsr_node(RuntimeError("sensitive registry detail"))

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("api.example", now=100)

    assert caught.value.code is ErrorCode.NBSR_E_INTERNAL
    assert "sensitive" not in str(caught.value)


def legacy_snapshot(
    *,
    requested_name: str = "legacy.example",
    origin_name: str = "origin.example",
    address: str = "192.0.2.10",
    observed_at: int = 100,
    result: LegacyDnsResult = LegacyDnsResult.POSITIVE,
    dnssec_status: DnssecStatus = DnssecStatus.SECURE,
) -> LegacyDnsSnapshot:
    endpoints = () if result is not LegacyDnsResult.POSITIVE else (OriginEndpoint(address, 443),)
    return LegacyDnsSnapshot(
        result=result,
        requested_name=requested_name,
        origin_name=origin_name,
        endpoints=endpoints,
        ttl_seconds=60,
        dnssec_status=dnssec_status,
        observed_at=observed_at,
    )


class MutableLegacyProvider:
    def __init__(self, snapshot: LegacyDnsSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def set_snapshot(self, snapshot: LegacyDnsSnapshot) -> None:
        self.snapshot = snapshot

    def __call__(self, request, now):
        self.calls += 1
        assert request.service_name == self.snapshot.requested_name
        assert now == self.snapshot.observed_at
        return self.snapshot


class GeneratedIds:
    def __init__(self) -> None:
        self.counter = 0

    def __call__(self, length: int) -> bytes:
        self.counter += 1
        return bytes((self.counter,)) * length


def configured_legacy_node(
    *,
    provider: MutableLegacyProvider | None = None,
    validator=lambda _request, _endpoint: True,
    policies: tuple[LegacyServicePolicy, ...] | None = None,
    pool: SyntheticAddressPool | None = None,
    store: ResolutionContextStore | None = None,
) -> tuple[NameNode, MutableLegacyProvider, ResolutionContextStore]:
    snapshot_provider = provider or MutableLegacyProvider(legacy_snapshot())
    context_store = store or ResolutionContextStore(max_entries=8)
    node = NameNode(
        StaticRegistry(None),
        (),
        policies or (legacy_policy(),),
        snapshot_provider,
        validator,
        LegacyOriginCache(max_entries=8),
        pool
        or SyntheticAddressPool(
            "127.80.0.0/29",
            "fd00:6e62:7372::/125",
            ttl_seconds=60,
        ),
        context_store,
        GeneratedIds(),
    )
    return node, snapshot_provider, context_store


def test_legacy_refresh_changes_internal_originset_not_synthetic_mapping() -> None:
    node, provider, store = configured_legacy_node()

    first = node.resolve("LEGACY.EXAMPLE.", now=100)
    first_binding = store.lookup(first.synthetic_ipv4, now=100)
    provider.set_snapshot(legacy_snapshot(address="192.0.2.20", observed_at=101))
    second = node.resolve("legacy.example", now=101)
    second_binding = store.lookup(second.synthetic_ipv6, now=101)

    assert first.classification is NameClassification.LEGACY_SERVICE
    assert second.synthetic_ipv4 == first.synthetic_ipv4
    assert second.synthetic_ipv6 == first.synthetic_ipv6
    assert first_binding is not None and first_binding.originset is not None
    assert second_binding is not None and second_binding.originset is not None
    assert second_binding.originset.content_digest != first_binding.originset.content_digest
    assert second_binding.route_intent.record_sequence == 1
    assert not hasattr(second, "originset")
    assert "192.0.2.20" not in repr(second)


def test_temporary_legacy_failure_uses_internal_last_known_good_only_within_grace() -> None:
    node, provider, store = configured_legacy_node()
    first = node.resolve("legacy.example", now=100)
    first_binding = store.lookup(first.synthetic_ipv4, now=100)
    provider.set_snapshot(
        legacy_snapshot(
            observed_at=101,
            result=LegacyDnsResult.TEMPORARY_FAILURE,
            dnssec_status=DnssecStatus.INDETERMINATE,
        )
    )

    second = node.resolve("legacy.example", now=101)
    second_binding = store.lookup(second.synthetic_ipv4, now=101)

    assert first_binding is not None and second_binding is not None
    assert second_binding.originset == first_binding.originset
    assert second.synthetic_ipv4 == first.synthetic_ipv4

    provider.set_snapshot(
        legacy_snapshot(
            observed_at=500,
            result=LegacyDnsResult.TEMPORARY_FAILURE,
            dnssec_status=DnssecStatus.INDETERMINATE,
        )
    )
    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("legacy.example", now=500)
    assert caught.value.code is ErrorCode.NBSR_E_ORIGIN_UNAVAILABLE


@pytest.mark.parametrize(
    "snapshot",
    (
        legacy_snapshot(
            result=LegacyDnsResult.AUTHENTICATED_NEGATIVE,
            dnssec_status=DnssecStatus.SECURE,
        ),
        legacy_snapshot(dnssec_status=DnssecStatus.BOGUS),
    ),
)
def test_invalid_legacy_state_fails_closed_without_origin_disclosure(snapshot) -> None:
    node, _, store = configured_legacy_node(provider=MutableLegacyProvider(snapshot))

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("legacy.example", now=100)

    assert caught.value.code is ErrorCode.NBSR_E_ORIGIN_UNAVAILABLE
    assert "192.0.2" not in str(caught.value)
    assert store.lookup("127.80.0.1", now=100) is None


def test_legacy_policy_denial_fails_closed_without_binding() -> None:
    node, _, store = configured_legacy_node(validator=lambda _request, _endpoint: False)

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("legacy.example", now=100)

    assert caught.value.code is ErrorCode.NBSR_E_ORIGIN_UNAVAILABLE
    assert store.lookup("127.80.0.1", now=100) is None


@pytest.mark.parametrize(
    "replacement",
    (
        legacy_snapshot(address="192.0.2.20", observed_at=100),
        legacy_snapshot(observed_at=101, dnssec_status=DnssecStatus.INSECURE),
    ),
)
def test_legacy_equivocation_or_dnssec_downgrade_invalidates_new_use(replacement) -> None:
    node, provider, _ = configured_legacy_node()
    node.resolve("legacy.example", now=100)
    provider.set_snapshot(replacement)

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("legacy.example", now=replacement.observed_at)

    assert caught.value.code is ErrorCode.NBSR_E_ORIGIN_UNAVAILABLE


def test_unknown_name_does_not_invoke_legacy_provider() -> None:
    node, provider, _ = configured_legacy_node()

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("unknown.example", now=100)

    assert caught.value.code is ErrorCode.NBSR_E_NAME_NOT_FOUND
    assert provider.calls == 0


@pytest.mark.parametrize("limited_resource", ("pool", "store"))
def test_legacy_capacity_failure_does_not_return_an_origin(limited_resource: str) -> None:
    second_policy = legacy_policy(
        canonical_name="second.example",
        service_id="second.service",
        origin_name="second-origin.example",
    )

    class PerNameProvider:
        def __call__(self, request, now):
            return legacy_snapshot(
                requested_name=request.service_name,
                origin_name=request.origin_name,
                observed_at=now,
            )

    pool = SyntheticAddressPool(
        "127.80.0.1/32" if limited_resource == "pool" else "127.80.0.0/29",
        "fd00:6e62:7372::1/128" if limited_resource == "pool" else "fd00:6e62:7372::/125",
        ttl_seconds=60,
    )
    store = ResolutionContextStore(max_entries=1 if limited_resource == "store" else 8)
    node = NameNode(
        StaticRegistry(None),
        (),
        (legacy_policy(), second_policy),
        PerNameProvider(),
        lambda _request, _endpoint: True,
        LegacyOriginCache(max_entries=8),
        pool,
        store,
        GeneratedIds(),
    )
    node.resolve("legacy.example", now=100)

    with pytest.raises(ProtocolViolation) as caught:
        node.resolve("second.example", now=101)

    assert caught.value.code is ErrorCode.NBSR_E_HANDLE_EXHAUSTED
    assert "192.0.2.10" not in str(caught.value)


@pytest.mark.parametrize(
    ("nbsr_policies", "legacy_policies"),
    (
        ((nbsr_policy(), nbsr_policy()), ()),
        ((), (legacy_policy(), legacy_policy())),
        ((nbsr_policy(canonical_name="shared.example"),), (legacy_policy(canonical_name="shared.example"),)),
    ),
)
def test_name_node_rejects_duplicate_or_overlapping_policy_names(nbsr_policies, legacy_policies) -> None:
    with pytest.raises(ProtocolViolation):
        NameNode(
            StaticRegistry(None),
            nbsr_policies,
            legacy_policies,
            CountingLegacyProvider(),
            lambda _request, _endpoint: True,
            LegacyOriginCache(max_entries=8),
            SyntheticAddressPool(
                "127.80.0.0/29",
                "fd00:6e62:7372::/125",
                ttl_seconds=60,
            ),
            ResolutionContextStore(max_entries=8),
            GeneratedIds(),
        )
