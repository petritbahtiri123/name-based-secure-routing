from __future__ import annotations

from dataclasses import replace

import pytest

from nbsr.federation import DecisionOutcome, EnforcementMode, ReasonCode
from nbsr.federation.state import FederationEvent, FederationState, StaticRecoveryPolicy


D = b"d" * 32


def base(**changes: object) -> FederationEvent:
    value = FederationEvent(
        "service:a",
        1,
        1,
        D,
        "service",
        b"a" * 32,
        b"b" * 32,
        b"c" * 32,
        valid_until=10_000,
        dependencies=(D,),
        source_fresh_at=100,
    )
    return replace(value, **changes)


@pytest.mark.parametrize(
    "operation", ["existing_session", "same_pair_reuse", "known_service", "known_endpoint_failover", "existing_context"]
)
def test_fresh_cached_state_allows_only_previously_approved_operations(operation: str) -> None:
    state, _ = FederationState.empty().apply(base(), 100)
    unchanged, result = state.apply(base(operation=operation), 399)
    assert unchanged is state
    assert (result.outcome, result.enforcement) == (DecisionOutcome.ACCEPT, EnforcementMode.NONE)


def test_restricted_window_and_hard_expiry_forbid_authority_expansion() -> None:
    state, _ = FederationState.empty().apply(base(), 100)
    _, restricted = state.apply(base(operation="existing_session"), 700)
    assert (restricted.outcome, restricted.reason, restricted.enforcement, restricted.retry_at) == (
        DecisionOutcome.RESTRICTED,
        ReasonCode.ERR_FRESHNESS,
        EnforcementMode.REAUTHENTICATE,
        1_000,
    )
    for operation in (
        "new_authority",
        "new_trust",
        "first_discovery",
        "ownership_transfer",
        "new_delegation",
        "root_change",
        "key_activation",
        "recovery_completion",
        "operator_admission",
        "unknown_checkpoint",
    ):
        _, denied = state.apply(base(operation=operation), 700)
        assert (denied.outcome, denied.reason, denied.enforcement) == (
            DecisionOutcome.REJECT,
            ReasonCode.ERR_OUTAGE_POLICY,
            EnforcementMode.DENY_NEW_USE,
        )
    _, expired = state.apply(base(operation="existing_session"), 1_000)
    assert (expired.outcome, expired.reason, expired.enforcement) == (
        DecisionOutcome.REJECT,
        ReasonCode.ERR_OUTAGE_POLICY,
        EnforcementMode.DRAIN,
    )


def test_known_compromise_overrides_lkg_and_selectively_terminates_only_dependencies() -> None:
    state, _ = FederationState.empty().apply(base(), 100)
    revoked, result = state.apply(base(object_digest=b"r" * 32, generation=2, previous_digest=D, terminal=True, compromised=True), 200)
    assert result.enforcement is EnforcementMode.TERMINATE_ACTIVE_USE
    assert D in result.invalidated_dependencies
    _, unrelated = revoked.apply(base(key="service:other", object_digest=b"z" * 32, service_id=b"q" * 32), 201)
    assert unrelated.enforcement is not EnforcementMode.TERMINATE_ACTIVE_USE


def test_static_recovery_is_pre_authorized_exact_bounded_non_resetting_and_reconciled() -> None:
    policy = StaticRecoveryPolicy(
        policy_digest=b"p" * 32,
        operators=(b"a" * 32, b"b" * 32),
        service_id=b"c" * 32,
        scope="service:a",
        allowed_triggers=("federation_unavailable",),
        activated_at=1_000,
        expires_at=4_600,
    )
    state = FederationState.empty(static_policies=(policy,))
    event = base(operation="static_recovery", static_policy_digest=policy.policy_digest, outage_trigger="federation_unavailable")
    _, result = state.apply(event, 1_901)
    assert (result.outcome, result.reason, result.enforcement) == (
        DecisionOutcome.RESTRICTED,
        ReasonCode.ERR_OUTAGE_POLICY,
        EnforcementMode.DENY_NEW_USE,
    )
    for changed in (
        {"peer_operator_id": b"x" * 32},
        {"service_id": b"x" * 32},
        {"outage_trigger": "authorization_failed"},
        {"authority_expansion": True},
    ):
        _, denied = state.apply(replace(event, **changed), 1_901)
        assert denied.reason is ReasonCode.ERR_RECOVERY_INVALID
    _, expired = state.apply(event, 4_600)
    assert expired.reason is ReasonCode.ERR_RECOVERY_INVALID

    current, _ = state.apply(base(), 100)
    reconciled, result = current.apply(base(operation="reconcile", object_digest=b"n" * 32, generation=2, previous_digest=D), 2_000)
    assert result.outcome is DecisionOutcome.ACCEPT
    assert result.audit == ("federation-recovered", "static-operation-reconciled")
    assert reconciled.static_policies == state.static_policies


def test_known_revocation_blocks_static_recovery_immediately() -> None:
    policy = StaticRecoveryPolicy(
        b"p" * 32,
        (b"a" * 32, b"b" * 32),
        b"c" * 32,
        "service:a",
        ("federation_unavailable",),
        1_000,
        4_600,
    )
    state = FederationState.empty(static_policies=(policy,))
    revoked, _ = state.apply(base(terminal=True), 100)
    _, result = revoked.apply(
        base(operation="static_recovery", static_policy_digest=policy.policy_digest, outage_trigger="federation_unavailable"),
        1_901,
    )
    assert (result.outcome, result.reason, result.enforcement) == (
        DecisionOutcome.REJECT,
        ReasonCode.ERR_REVOKED,
        EnforcementMode.TERMINATE_ACTIVE_USE,
    )


def test_compromise_and_replay_precede_static_recovery() -> None:
    policy = StaticRecoveryPolicy(
        b"p" * 32,
        (b"a" * 32, b"b" * 32),
        b"c" * 32,
        "service:a",
        ("federation_unavailable",),
        1_000,
        4_600,
    )
    state, _ = FederationState.empty(static_policies=(policy,)).apply(base(replay_digest=D), 100)
    candidate = base(
        operation="static_recovery",
        static_policy_digest=policy.policy_digest,
        outage_trigger="federation_unavailable",
        replay_digest=D,
        compromised=True,
    )
    unchanged, result = state.apply(candidate, 1_901)
    assert unchanged is state
    assert (result.outcome, result.reason) == (DecisionOutcome.REJECT, ReasonCode.ERR_REPLAY)
