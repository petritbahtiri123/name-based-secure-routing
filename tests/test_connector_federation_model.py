"""Offline adapter tests; fixture keys are public deterministic test material."""

from dataclasses import replace
import importlib
import importlib.util
from pathlib import Path

import pytest

from nbsr.connector_control_model import Binding, CompletionGrace
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation.authorization import FederationResult
from nbsr.federation.cose import authenticate_bilateral_context
from nbsr.federation.fields import FederationValidationError
from nbsr.protocol.cose import sign1
from nbsr.federation.registry import DecisionOutcome, EnforcementMode, ReasonCode

spec = importlib.util.spec_from_file_location(
    "connector_authorization_fixtures", Path(__file__).parent / "federation/test_authorization.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class Clock:
    now = 150

    def __call__(self):
        return self.now


class Transport:
    def __init__(self):
        self.session = object()
        self.closed = False

    def close(self):
        self.closed = True


def signed_fixture(context, *, tamper=False, purpose=None, destination_expires=5000):
    # Reuse the existing public deterministic seeds and authority fixture shape.
    # Only in-memory test signing occurs; no credential issuance or key storage.
    baseline = fixtures.authenticated_context(context)
    source = replace(baseline.source_authority, expires_at=5000)
    destination = replace(baseline.destination_authority, expires_at=destination_expires)
    if purpose is not None:
        source = replace(source, purpose=purpose)
    raw_source = sign1(context.canonical_bytes(), source.kid, Ed25519PrivateKey.from_private_bytes(bytes(range(32))))
    raw_destination = sign1(context.canonical_bytes(), destination.kid, Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))))
    if tamper:
        raw_destination = raw_destination[:-1] + bytes([raw_destination[-1] ^ 1])
    return authenticate_bilateral_context(raw_source, source, raw_destination, destination, 150)


@pytest.fixture
def rig():
    assert importlib.util.find_spec("nbsr.connector_federation_model") is not None, "adapter missing"
    api = importlib.import_module("nbsr.connector_federation_model")
    clock = Clock()
    proof = fixtures.proof(**{"42": 5000})
    context = fixtures.context(proof, **{"41": 5000})
    signed = signed_fixture(context)
    source = fixtures.evidence(authority_proof=proof)
    dest = replace(source, operator_id=fixtures.DEST, peer_operator_id=fixtures.SOURCE, endpoint_operator_id=fixtures.DEST)
    adapter = api.Adapter(
        Binding("fixture", "service", "gateway", "operator", "issuer", 1, "fixture"),
        clock,
        lease=4000,
        grace=CompletionGrace("federation-development-fixture", 30),
    )
    return adapter, clock, signed, source, dest


def opened(rig):
    adapter, _, signed, source, dest = rig
    attempt = adapter.open(Transport(), signed, source, dest)
    assert attempt is not None
    work = adapter.model.admit_work(attempt, deadline=4000)
    assert work is not None
    return attempt, work


def test_adapter_module_exists():
    assert importlib.util.find_spec("nbsr.connector_federation_model") is not None


def test_outage_restricts_new_use_without_cancelling_valid_work(rig):
    adapter, clock, _, _, _ = rig
    attempt, work = opened(rig)
    assert adapter.outage(attempt)
    clock.now = 449
    assert adapter.model.select() is None
    assert not work.cancelled and not attempt.transport.closed
    assert adapter.result.outcome is DecisionOutcome.ACCEPT
    clock.now = 450
    adapter.model.poll()
    assert adapter.result.outcome is DecisionOutcome.RESTRICTED
    assert adapter.result.enforcement is EnforcementMode.REAUTHENTICATE
    assert adapter.result.retry_at == 1050
    assert not work.cancelled


def test_stale_cache_drains_from_original_boundary(rig):
    adapter, clock, _, _, _ = rig
    attempt, work = opened(rig)
    adapter.outage(attempt)
    clock.now = 1050
    adapter.model.poll()
    assert adapter.result.enforcement is EnforcementMode.DRAIN
    assert work.deadline == 1080 and not work.cancelled
    clock.now = 1080
    adapter.model.poll()
    assert work.cancelled and attempt.transport.closed


def test_fresh_verified_recovery_restores_eligibility_without_replay(rig):
    adapter, clock, signed, source, dest = rig
    attempt, work = opened(rig)
    adapter.outage(attempt)
    clock.now = 700
    adapter.model.poll()
    assert adapter.recover(attempt, signed, replace(source, now=700), replace(dest, now=700))
    assert adapter.model.select() is attempt
    assert work.owner is attempt and work.deadline == 4000
    assert adapter.model.admit_work(attempt, deadline=4000) is None


@pytest.mark.parametrize("bad", ["bare", "destination", "expired", "context"])
def test_recovery_requires_full_exact_current_evidence(rig, bad):
    adapter, clock, signed, source, dest = rig
    attempt, work = opened(rig)
    adapter.outage(attempt)
    clock.now = 700
    source, dest = replace(source, now=700), replace(dest, now=700)
    if bad == "bare":
        signed = FederationResult(DecisionOutcome.ACCEPT, ReasonCode.NONE)
    elif bad == "destination":
        dest = replace(dest, service_id=b"x" * 32)
    elif bad == "expired":
        signed = replace(signed, source_authority=replace(signed.source_authority, expires_at=699))
    else:
        signed = fixtures.authenticated_context(fixtures.context())
    assert not adapter.recover(attempt, signed, source, dest)
    assert adapter.model.select() is None and not work.cancelled


def test_authority_expiry_dominates_fresh_cache(rig):
    adapter, clock, signed, source, dest = rig
    signed = replace(signed, source_authority=replace(signed.source_authority, expires_at=200))
    attempt = adapter.open(Transport(), signed, source, dest)
    work = adapter.model.admit_work(attempt, deadline=4000)
    adapter.outage(attempt)
    clock.now = 200
    adapter.model.poll()
    assert work.cancelled and attempt.transport.closed


@pytest.mark.parametrize("mode", [EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE])
def test_dependency_scoped_simulated_event_and_recovery_latch(rig, mode):
    adapter, clock, signed, source, dest = rig
    attempt, work = opened(rig)
    assert not adapter.simulate_dependency_event(attempt, signed.context.digest, {b"unrelated"}, mode)
    assert not work.cancelled and adapter.model.select() is attempt
    assert adapter.simulate_dependency_event(attempt, signed.context.digest, {fixtures.BUNDLE}, mode)
    assert work.cancelled is (mode is EnforcementMode.TERMINATE_ACTIVE_USE)
    assert not adapter.recover(attempt, signed, source, dest)
    clock.now = 180
    adapter.model.poll()
    assert work.cancelled and attempt.transport.closed


def test_wrong_owner_or_context_has_no_effect(rig):
    adapter, _, signed, _, _ = rig
    attempt, work = opened(rig)
    assert not adapter.outage(object())
    assert not adapter.simulate_dependency_event(attempt, b"x" * 32, {fixtures.BUNDLE}, EnforcementMode.TERMINATE_ACTIVE_USE)
    assert not adapter.simulate_dependency_event(object(), signed.context.digest, {fixtures.BUNDLE}, EnforcementMode.TERMINATE_ACTIVE_USE)
    assert not work.cancelled and adapter.model.select() is attempt


def test_terminate_failed_cleanup_retains_owner(rig):
    adapter, _, signed, _, _ = rig
    attempt, work = opened(rig)
    attempt.transport.close = lambda: None
    adapter.simulate_dependency_event(attempt, signed.context.digest, {fixtures.BUNDLE}, EnforcementMode.TERMINATE_ACTIVE_USE)
    assert work.cancelled and adapter.model.health()["owned"] == 1


@pytest.mark.parametrize("failure", ["signature", "purpose"])
def test_existing_crypto_boundary_rejects_invalid_fixture(failure):
    from nbsr.federation.registry import KeyPurpose

    with pytest.raises(FederationValidationError):
        signed_fixture(fixtures.context(), tamper=failure == "signature", purpose=KeyPurpose.DELEGATION if failure == "purpose" else None)


def test_bare_result_cannot_open_owner(rig):
    adapter, _, _, source, dest = rig
    transport = Transport()
    assert adapter.open(transport, FederationResult(DecisionOutcome.ACCEPT, ReasonCode.NONE), source, dest) is None
    assert transport.closed and adapter.model.health()["owned"] == 0


def test_outage_blocks_all_new_use_and_does_not_restart_deadlines(rig):
    adapter, clock, _, _, _ = rig
    attempt, work = opened(rig)
    ticket = adapter.model._acceptance
    adapter.outage(attempt)
    assert adapter.model.renew(attempt, ticket) is None
    assert not adapter.model.confirm(attempt, ticket)
    assert not adapter.model.renew_work(work)
    adapter.model.finish_work(work)
    assert adapter.model.admit_work(attempt, deadline=4000) is None
    clock.now = 1000
    adapter.outage(attempt)
    assert adapter.result.retry_at == 1050
    clock.now = 1050
    adapter.model.poll()
    assert attempt.transport.closed


def test_recovery_cannot_resurrect_started_drain(rig):
    adapter, clock, signed, source, dest = rig
    attempt, work = opened(rig)
    adapter.outage(attempt)
    clock.now = 1050
    adapter.model.poll()
    assert not adapter.recover(attempt, signed, replace(source, now=1050), replace(dest, now=1050))
    assert work.deadline == 1080


def test_session_substitution_rejects_recovery(rig):
    adapter, _, signed, source, dest = rig
    attempt, work = opened(rig)
    attempt.transport.session = object()
    assert not adapter.recover(attempt, signed, source, dest)
    assert work.cancelled and attempt.transport.closed


def test_duplicate_open_closes_only_rejected_new_transport(rig):
    adapter, _, signed, source, dest = rig
    attempt, work = opened(rig)
    duplicate = Transport()
    assert adapter.open(duplicate, signed, source, dest) is None
    assert duplicate.closed
    assert adapter.open(attempt.transport, signed, source, dest) is None
    assert not attempt.transport.closed and not work.cancelled


def test_recovery_crossing_staleness_boundary_cannot_reset_drain(rig):
    adapter, clock, signed, source, dest = rig
    attempt, work = opened(rig)
    adapter.outage(attempt)
    samples = iter((1049, 1050))
    adapter.clock = adapter.model.clock = lambda: next(samples, 1050)
    assert not adapter.recover(attempt, signed, replace(source, now=1050), replace(dest, now=1050))
    assert work.deadline == 1080 and adapter.model.select() is None


@pytest.mark.parametrize("limit", ["destination_signer", "proof"])
def test_gap_independent_expiry_boundary_before_at_after(rig, limit):
    adapter, clock, signed, source, dest = rig
    if limit == "destination_signer":
        signed = signed_fixture(signed.context, destination_expires=200)
    else:
        proof = fixtures.proof(**{"42": 200})
        signed = signed_fixture(fixtures.context(proof, **{"41": 5000}))
        source, dest = replace(source, authority_proof=proof), replace(dest, authority_proof=proof)
    attempt = adapter.open(Transport(), signed, source, dest)
    assert attempt is not None
    work = adapter.model.admit_work(attempt, deadline=4000)
    assert work.deadline == 200
    adapter.outage(attempt)
    clock.now = 199
    adapter.model.poll()
    assert not work.cancelled and not attempt.transport.closed
    for now in (200, 201):
        clock.now = now
        adapter.model.poll()
        assert work.cancelled and attempt.transport.closed and adapter.model.health()["owned"] == 0
        assert not adapter.recover(attempt, signed, replace(source, now=now), replace(dest, now=now))


def test_gap_destination_proof_must_match_authenticated_context(rig):
    adapter, _, signed, source, dest = rig
    transport = Transport()
    mismatched = replace(dest, authority_proof=fixtures.proof(**{"42": 200}))
    assert adapter.open(transport, signed, source, mismatched) is None
    assert transport.closed and adapter.model.health()["owned"] == 0


@pytest.mark.parametrize("mode", [EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE])
def test_gap_two_live_owners_have_independent_dependency_effects(rig, mode):
    adapter, clock, signed, source, dest = rig
    first, first_work = opened(rig)
    proof_b = fixtures.proof(**{"32": b"proof-b", "42": 5000})
    signed_b = signed_fixture(fixtures.context(proof_b, **{"41": 5000}))
    other = type(adapter)(replace(adapter.binding, connector="other-fixture"), clock, lease=4000, grace=adapter.grace)
    second = other.open(Transport(), signed_b, replace(source, authority_proof=proof_b), replace(dest, authority_proof=proof_b))
    second_work = other.model.admit_work(second, deadline=4000)
    affected = {source.authority_proof.digest}
    assert not other.simulate_dependency_event(first, signed.context.digest, affected, mode)
    assert not other.simulate_dependency_event(second, signed_b.context.digest, affected, mode)
    assert adapter.simulate_dependency_event(first, signed.context.digest, affected, mode)
    assert first_work.cancelled is (mode is EnforcementMode.TERMINATE_ACTIVE_USE)
    clock.now = 180
    adapter.model.poll()
    assert first_work.cancelled and first.transport.closed
    assert other.model.select() is second and not second_work.cancelled and not second.transport.closed
    other.model.finish_work(second_work)
    other.model.stop(second)
    assert other.model.health()["owned"] == 0


@pytest.mark.parametrize("side", ["source", "destination"])
@pytest.mark.parametrize("change", ["revoked_dependency", "policy", "checkpoint"])
def test_gap_recovery_rechecks_changed_evidence_at_same_time(rig, side, change):
    adapter, clock, signed, source, dest = rig
    attempt, work = opened(rig)
    clock.now = 700
    source, dest = replace(source, now=700), replace(dest, now=700)
    adapter.outage(attempt)
    assert adapter.recover(attempt, signed, source, dest)
    adapter.outage(attempt)
    changed = source if side == "source" else dest
    if change == "revoked_dependency":
        changed = replace(changed, revoked_dependencies=frozenset({fixtures.BUNDLE}))
    elif change == "policy":
        changed = replace(changed, policy_digest=b"x" * 32)
    else:
        changed = replace(changed, checkpoint_compatible=False)
    if side == "source":
        source = changed
    else:
        dest = changed
    assert not adapter.recover(attempt, signed, source, dest)
    assert adapter.model.select() is None and not work.cancelled
    assert work.deadline == 4000


@pytest.mark.parametrize("mode", [EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE])
def test_gap_timed_semantic_fixture_no_early_effect_or_expiry_resurrection(rig, mode):
    # Test-owned scheduling only: no adapter wire parser, event authentication,
    # target-class-to-runtime-owner mapping or threshold packaging is claimed.
    spec = importlib.util.spec_from_file_location("connector_revocation_fixtures", Path(__file__).parent / "federation/test_revocation.py")
    rev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rev)
    adapter, clock, signed, _, _ = rig
    attempt, work = opened(rig)
    record = rev.revocation(**{"6": 160, "7": 170, "36": mode.value})
    semantic = rev.threshold(record, 1)  # Existing explicitly synthetic evidence.
    record.authorize(semantic)
    clock.now = 159
    with pytest.raises(FederationValidationError):
        record.require_valid_at(clock.now)
    assert adapter.model.select() is attempt and not work.cancelled
    clock.now = 160
    record.require_valid_at(clock.now)
    assert adapter.simulate_dependency_event(attempt, signed.context.digest, {fixtures.BUNDLE}, mode)
    assert work.cancelled is (mode is EnforcementMode.TERMINATE_ACTIVE_USE)
    if mode is EnforcementMode.DENY_NEW_USE:
        assert work.deadline == 190
    clock.now = 170
    record.require_valid_at(clock.now)  # Existing record validity is inclusive.
    clock.now = 171
    with pytest.raises(FederationValidationError):
        record.require_valid_at(clock.now)
    assert adapter.model.select() is None
    clock.now = 190
    adapter.model.poll()
    assert work.cancelled and attempt.transport.closed
