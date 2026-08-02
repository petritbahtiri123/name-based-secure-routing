"""Limits and fair ownership contracts for the deterministic WP7 lab."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from nbsr.two_operator_lab import (
    MAX_UINT64,
    AdmissionContext,
    LabRejected,
    LimitProfile,
    ResourceLimiter,
    TokenBucket,
)


def digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def context(**changes: object) -> AdmissionContext:
    values: dict[str, object] = {
        "source_operator": "isp-a",
        "destination_operator": "isp-b",
        "tenant_id": "tenant-a",
        "subscriber_pseudonym": digest("subscriber-a"),
        "name_id": "payments",
        "route_id": "route-a",
        "service_id": "payments",
        "channel_id": "channel-a",
        "tunnel_id": "tunnel-a",
        "source_edge_id": "source-edge-a",
        "destination_edge_id": "destination-edge-b",
        "route_grant_digest": digest("grant-a"),
        "source_policy_digest": digest("source-policy"),
        "destination_policy_digest": digest("destination-policy"),
        "source_gateway_digest": digest("source-gateway"),
        "destination_gateway_digest": digest("destination-gateway"),
        "source_continuity_digest": digest("source-continuity"),
        "destination_continuity_digest": digest("destination-continuity"),
        "source_policy_version": 1,
        "destination_policy_version": 1,
    }
    values.update(changes)
    return AdmissionContext(**values)  # type: ignore[arg-type]


def profile(**changes: object) -> LimitProfile:
    values: dict[str, object] = {
        "client_capacity": 8,
        "name_capacity": 8,
        "route_capacity": 8,
        "service_capacity": 8,
        "channel_capacity": 8,
        "tunnel_capacity": 8,
        "operator_capacity": 8,
        "refill_per_ms": 1,
        "max_buckets": 64,
        "max_active_allocations": 32,
    }
    values.update(changes)
    return LimitProfile(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("scope", "field", "value"),
    [
        ("client", "subscriber_pseudonym", digest("subscriber-b")),
        ("name", "name_id", "invoices"),
        ("route", "route_id", "route-b"),
        ("service", "service_id", "invoices"),
        ("channel", "channel_id", "channel-b"),
        ("tunnel", "tunnel_id", "tunnel-b"),
    ],
)
def test_each_context_scope_has_an_independent_bucket(scope: str, field: str, value: object) -> None:
    limits = ResourceLimiter(profile(**{f"{scope}_capacity": 1}))
    original = context()
    sibling = replace(original, **{field: value})

    limits.consume(original, amount=1, now_ms=10)
    limits.consume(sibling, amount=1, now_ms=10)

    with pytest.raises(LabRejected, match=f"{scope} limit"):
        limits.consume(original, amount=1, now_ms=10)


def test_operator_buckets_are_independent_for_each_owned_operator() -> None:
    limits = ResourceLimiter(profile(operator_capacity=1))
    first = context()
    other_source = replace(
        first,
        source_operator="isp-c",
        destination_operator="isp-d",
        subscriber_pseudonym=digest("subscriber-c"),
    )

    limits.consume(first, amount=1, now_ms=10)
    limits.consume(other_source, amount=1, now_ms=10)

    with pytest.raises(LabRejected, match="operator limit"):
        limits.consume(first, amount=1, now_ms=10)


def test_context_consumption_inherits_every_applicable_scope_limit() -> None:
    limits = ResourceLimiter(profile(name_capacity=1))
    first = context()
    same_name_other_service = replace(first, service_id="billing", route_id="route-b", channel_id="channel-b", tunnel_id="tunnel-b")

    limits.consume(first, amount=1, now_ms=10)

    with pytest.raises(LabRejected, match="name limit"):
        limits.consume(same_name_other_service, amount=1, now_ms=10)


def test_token_bucket_refills_by_integer_milliseconds_and_saturates_at_burst_capacity() -> None:
    bucket = TokenBucket(capacity=5, refill_per_ms=2, now_ms=100)

    bucket.consume(amount=5, now_ms=100)
    with pytest.raises(LabRejected, match="token bucket"):
        bucket.consume(amount=1, now_ms=100)
    bucket.consume(amount=2, now_ms=101)
    assert bucket.tokens == 0

    bucket.consume(amount=5, now_ms=MAX_UINT64)
    assert bucket.tokens == 0


def test_token_bucket_rejects_uint64_overflow_and_clock_rollback_without_wraparound() -> None:
    bucket = TokenBucket(capacity=5, refill_per_ms=MAX_UINT64, now_ms=MAX_UINT64 - 1)
    bucket.consume(amount=5, now_ms=MAX_UINT64 - 1)
    bucket.consume(amount=5, now_ms=MAX_UINT64)

    with pytest.raises(LabRejected, match="clock"):
        bucket.consume(amount=1, now_ms=MAX_UINT64 - 1)
    with pytest.raises(LabRejected, match="uint64"):
        bucket.consume(amount=MAX_UINT64 + 1, now_ms=MAX_UINT64)


def test_multi_scope_denial_is_atomic_before_any_bucket_is_consumed() -> None:
    limits = ResourceLimiter(profile(client_capacity=3, name_capacity=2))
    first = context()
    new_name = replace(first, name_id="invoices")
    limits.consume(first, amount=1, now_ms=10)

    with pytest.raises(LabRejected, match="client limit"):
        limits.consume(new_name, amount=3, now_ms=10)

    limits.consume(new_name, amount=2, now_ms=10)


def test_active_allocations_enforce_dynamic_per_subscriber_fair_share() -> None:
    limits = ResourceLimiter(profile(client_capacity=3, operator_capacity=4))
    subscriber_a = context()
    subscriber_a_second = replace(subscriber_a, channel_id="channel-b", tunnel_id="tunnel-b")
    subscriber_a_third = replace(subscriber_a, channel_id="channel-c", tunnel_id="tunnel-c")
    subscriber_b = replace(subscriber_a, subscriber_pseudonym=digest("subscriber-b"), channel_id="channel-d", tunnel_id="tunnel-d")

    limits.allocate(subscriber_a)
    limits.allocate(subscriber_a_second)
    limits.allocate(subscriber_b)

    with pytest.raises(LabRejected, match="fair share"):
        limits.allocate(subscriber_a_third)

    assert limits.active_allocation_count == 3


def test_same_source_operator_cannot_exceed_its_aggregate_allocation_capacity() -> None:
    limits = ResourceLimiter(profile(client_capacity=3, operator_capacity=2))
    first = context()
    second = replace(first, subscriber_pseudonym=digest("subscriber-b"), channel_id="channel-b", tunnel_id="tunnel-b")
    third = replace(first, subscriber_pseudonym=digest("subscriber-c"), channel_id="channel-c", tunnel_id="tunnel-c")

    limits.allocate(first)
    limits.allocate(second)

    with pytest.raises(LabRejected, match="source operator allocation capacity"):
        limits.allocate(third)

    assert limits.active_allocation_count == 2


def test_unrelated_source_operator_allocations_do_not_reduce_a_subscriber_fair_share() -> None:
    limits = ResourceLimiter(profile(client_capacity=4, operator_capacity=4))
    isp_a_first = context()
    isp_a_second = replace(isp_a_first, channel_id="channel-b", tunnel_id="tunnel-b")
    unrelated = [
        replace(
            isp_a_first,
            source_operator="isp-c",
            destination_operator="isp-d",
            subscriber_pseudonym=digest(f"subscriber-c-{index}"),
            channel_id=f"channel-c-{index}",
            tunnel_id=f"tunnel-c-{index}",
        )
        for index in range(1, 4)
    ]

    limits.allocate(isp_a_first)
    for candidate in unrelated:
        limits.allocate(candidate)
    limits.allocate(isp_a_second)

    assert limits.active_allocation_count == 5


def test_destination_operator_capacity_and_fairness_are_independent_of_other_destinations() -> None:
    capped = ResourceLimiter(profile(client_capacity=3, operator_capacity=2))
    first = context()
    second = replace(
        first,
        source_operator="isp-c",
        subscriber_pseudonym=digest("subscriber-c"),
        channel_id="channel-c",
        tunnel_id="tunnel-c",
    )
    third = replace(
        first,
        source_operator="isp-d",
        subscriber_pseudonym=digest("subscriber-d"),
        channel_id="channel-d",
        tunnel_id="tunnel-d",
    )
    capped.allocate(first)
    capped.allocate(second)

    with pytest.raises(LabRejected, match="destination operator allocation capacity"):
        capped.allocate(third)

    isolated = ResourceLimiter(profile(client_capacity=4, operator_capacity=4))
    destination_b_first = context()
    destination_b_second = replace(destination_b_first, channel_id="channel-b", tunnel_id="tunnel-b")
    other_destination = [
        replace(
            destination_b_first,
            source_operator=f"isp-c-{index}",
            destination_operator="isp-d",
            subscriber_pseudonym=digest(f"subscriber-d-{index}"),
            channel_id=f"channel-d-{index}",
            tunnel_id=f"tunnel-d-{index}",
        )
        for index in range(1, 4)
    ]
    isolated.allocate(destination_b_first)
    for candidate in other_destination:
        isolated.allocate(candidate)
    isolated.allocate(destination_b_second)

    assert isolated.active_allocation_count == 5


def test_noisy_subscriber_cannot_consume_a_sibling_quota_or_allocation() -> None:
    limits = ResourceLimiter(profile(client_capacity=1, operator_capacity=2))
    noisy = context()
    sibling = replace(noisy, subscriber_pseudonym=digest("subscriber-b"), channel_id="channel-b", tunnel_id="tunnel-b")

    limits.consume(noisy, amount=1, now_ms=10)
    with pytest.raises(LabRejected, match="client limit"):
        limits.consume(noisy, amount=1, now_ms=10)
    limits.consume(sibling, amount=1, now_ms=10)
    limits.allocate(noisy)
    limits.allocate(sibling)


def test_bounded_active_allocation_map_fails_closed_without_growth() -> None:
    limits = ResourceLimiter(profile(max_active_allocations=1))
    first = context()
    second = replace(first, subscriber_pseudonym=digest("subscriber-b"), channel_id="channel-b", tunnel_id="tunnel-b")
    limits.allocate(first)

    with pytest.raises(LabRejected, match="allocation capacity"):
        limits.allocate(second)

    assert limits.active_allocation_count == 1
