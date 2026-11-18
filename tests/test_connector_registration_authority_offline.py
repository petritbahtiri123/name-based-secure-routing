"""Public deterministic signed fixtures; no generated keys, sockets or real trust."""

from dataclasses import replace
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.connector_registration_authority_offline import OfflineRegistrationAuthority, PROFILE
from nbsr.federation.cose import FederationAuthority
from nbsr.federation.delegation import SignedFederationObject
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.ownership import derive_service_id
from nbsr.federation.registry import AuthorityClass as AC, KeyLifecycle as KL, KeyPurpose as KP, ObjectType as OT
from nbsr.protocol.cbor import encode_deterministic as enc, decode_deterministic as dec
from nbsr.protocol.cose import sign1

# Same openly known test seed as tests/federation/test_cose_authority.py.
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUB = KEY.public_key().public_bytes_raw()
A, C, D = b"A" * 32, b"C" * 32, b"D" * 32
SERVICE = derive_service_id(A, "service.example")


def ref(kind, operator):
    return {1: int(kind), 2: operator, 3: b"key", 4: operator}


def fixture(**changes):
    scope = {1: "service.example", 2: SERVICE, 3: b"tenant", 4: C, 5: D, 6: "eu", 7: [[443, 443]], 8: [6], 9: [24576], 10: False, 11: 0}
    root = {
        1: 3,
        2: 1,
        3: ref(AC.NAME_OWNER, A),
        4: 1,
        5: 1,
        6: 900,
        7: 2000,
        32: "service.example",
        33: ref(AC.NAME_OWNER, A),
        34: SERVICE,
        35: None,
        36: 0,
        37: None,
    }
    delegation = {
        1: 4,
        2: 1,
        3: ref(AC.NAME_OWNER, A),
        4: 1,
        5: 1,
        6: 900,
        7: 1900,
        32: ref(AC.NAME_OWNER, A),
        33: ref(AC.DELEGATE, C),
        34: scope,
        36: None,
        37: None,
    }
    kar = {
        1: 2,
        2: 1,
        3: ref(AC.OPERATOR_IDENTITY_ROOT, C),
        4: 1,
        5: 1,
        6: 900,
        7: 1800,
        32: C,
        33: b"transport-key",
        34: PUB,
        35: 14,
        36: int(KL.ACTIVE),
        37: ref(AC.OPERATOR_IDENTITY_ROOT, C),
        38: False,
        39: None,
    }
    if "kar" in changes:
        kar.update(changes["kar"])
    if "root" in changes:
        root.update(changes["root"])
    if "delegation" in changes:
        delegation.update(changes["delegation"])
    authorities = tuple(
        FederationAuthority(b"key", KEY.public_key(), op, purpose, KL.ACTIVE, 1, 1, 800, 2100, False)
        for op, purpose in ((C, KP.IDENTITY_ROOT), (A, KP.NAME_OWNERSHIP), (A, KP.DELEGATION))
    )

    def signed(payload, authority):
        raw = enc(payload)
        return SignedFederationObject(sign1(raw, b"key", KEY), authority, raw)

    key_record, ownership, grant = (signed(p, a) for p, a in zip((kar, root, delegation), authorities, strict=True))
    inventory = frozenset((OT(p[1]), sha256(enc(p)).digest()) for p in (kar, root, delegation))
    refs = sorted([[int(t), digest] for t, digest in inventory], key=enc)
    body = {
        0: 1,
        1: "register",
        2: "connector-a",
        3: SERVICE,
        4: C,
        5: D,
        6: "gateway-a",
        7: b"transport-key",
        8: sha256(PUB).digest(),
        9: sha256(enc(kar)).digest(),
        10: refs,
        11: sha256(enc(refs)).digest(),
        12: b"P" * 32,
        13: 60,
        14: 1000,
        15: None,
    }
    kwargs = dict(
        profile=PROFILE,
        policy_request=enc(body),
        scope=enc(scope),
        record_inventory=inventory,
        signer_inventory=authorities,
        revision=1,
        freshness_expires=1700,
        freshness_ref=b"F" * 32,
    )
    context = dict(
        connection=1,
        session=b"s" * 16,
        request_id=b"s" * 8 + (1).to_bytes(8, "big"),
        peer_key=PUB,
        key_authorization=key_record,
        chain=(ownership, grant),
        now=1000,
        revision=1,
    )
    return kwargs, enc(body), context


def test_signed_registration_receipt_is_reusable_only_for_its_exact_current_binding():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    assert receipt.admission_ceiling == 1700
    assert receipt.profile == PROFILE and receipt.action == 24576
    assert receipt.request_digest == sha256(raw).digest()
    assert adapter.validate(receipt, raw, **ctx) is receipt
    assert {entry[0] for entry in receipt.provenance} >= {"signed-record", "fixture-freshness"}
    with pytest.raises(FederationValidationError):
        adapter.validate(replace(receipt), raw, **ctx)
    adapter.advance_revision(2)
    with pytest.raises(FederationValidationError):
        adapter.validate(receipt, raw, **(ctx | {"revision": 2}))


def test_signed_renewal_revalidates_authority_without_granting_owner_or_application_rights():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    body = dec(raw)
    body[1] = "renew"
    body[15] = b"R" * 32
    receipt = adapter.verify(enc(body), **ctx)
    assert receipt.admission_ceiling == 1700  # not now + the registration lease


@pytest.mark.parametrize(
    "field,value",
    [(2, "other"), (3, b"X" * 32), (4, b"X" * 32), (5, b"X" * 32), (6, "other"), (7, b"other"), (8, b"X" * 32), (12, b"X" * 32)],
)
def test_exact_principal_service_gateway_policy_pins(field, value):
    kwargs, raw, ctx = fixture()
    body = dec(raw)
    body[field] = value
    with pytest.raises(FederationValidationError):
        OfflineRegistrationAuthority(**kwargs).verify(enc(body), **ctx)


@pytest.mark.parametrize(
    "field,value",
    [
        ("connection", 2),
        ("session", b"t" * 16),
        ("request_id", b"s" * 8 + (2).to_bytes(8, "big")),
        ("peer_key", b"X" * 32),
        ("revision", 2),
    ],
)
def test_receipt_cannot_be_substituted_between_requests_sessions_or_revisions(field, value):
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    with pytest.raises(FederationValidationError):
        adapter.validate(receipt, raw, **(ctx | {field: value}))


def test_signature_corruption_and_wrong_signer_purpose_are_rejected():
    kwargs, raw, ctx = fixture()
    record = ctx["key_authorization"]
    bad = replace(record, message=record.message[:-1] + bytes([record.message[-1] ^ 1]))
    with pytest.raises(FederationValidationError):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **(ctx | {"key_authorization": bad}))
    for authority in (
        replace(record.authority, purpose=KP.DELEGATION),
        replace(record.authority, operator_id=A),
        replace(record.authority, kid=b"other"),
    ):
        with pytest.raises(FederationValidationError):
            OfflineRegistrationAuthority(**kwargs).verify(raw, **(ctx | {"key_authorization": replace(record, authority=authority)}))


@pytest.mark.parametrize(
    "mutation", [{35: 11}, {34: b"X" * 32}, {36: int(KL.NEXT)}, {38: True, 39: {1: 2, 2: b"transport-key", 3: None}}, {7: 999}]
)
def test_pinned_signed_key_record_still_requires_current_transport_authority(mutation):
    kwargs, raw, ctx = fixture(kar=mutation)
    with pytest.raises(FederationValidationError):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)


def test_namespace_inventory_and_complete_signed_ancestry_are_mandatory():
    kwargs, raw, ctx = fixture()
    for change in ({"profile": "other"}, {"record_inventory": frozenset()}):
        with pytest.raises(FederationValidationError):
            OfflineRegistrationAuthority(**(kwargs | change)).verify(raw, **ctx)
    for chain in ((), ctx["chain"][1:], (True,), (dec(ctx["chain"][0].expected_payload), ctx["chain"][1])):
        with pytest.raises(FederationValidationError):
            OfflineRegistrationAuthority(**kwargs).verify(raw, **(ctx | {"chain": chain}))


def test_expiry_and_revision_invalidation_do_not_resurrect_receipts():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    with pytest.raises(FederationValidationError):
        adapter.validate(receipt, raw, **(ctx | {"now": 1700}))
    adapter.advance_revision(2, revoked_records=frozenset({next(iter(kwargs["record_inventory"]))[1]}))
    with pytest.raises(FederationValidationError):
        adapter.verify(raw, **(ctx | {"revision": 2}))
    with pytest.raises(FederationValidationError):
        adapter.advance_revision(1)


def test_no_bare_or_synthetic_receipt_is_provenance():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    for receipt in (True, object(), {"verified": True}):
        with pytest.raises(FederationValidationError):
            adapter.validate(receipt, raw, **ctx)


@pytest.mark.parametrize("index", [0, 1])
def test_every_ancestry_signature_is_checked(index):
    kwargs, raw, ctx = fixture()
    chain = list(ctx["chain"])
    item = chain[index]
    chain[index] = replace(item, message=item.message[:-1] + bytes([item.message[-1] ^ 1]))
    with pytest.raises(FederationValidationError, match="COSE"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **(ctx | {"chain": tuple(chain)}))


@pytest.mark.parametrize("field,value", [(7, [[80, 443]]), (8, [6, 17]), (1, "other.example")])
def test_valid_signatures_do_not_authorize_widened_or_different_scope(field, value):
    kwargs, raw, ctx = fixture()
    scope = dec(kwargs["scope"])
    scope[field] = value
    kwargs["scope"] = enc(scope)
    with pytest.raises(FederationValidationError):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)


def test_signed_grant_for_another_action_or_delegatee_is_not_registration_authority():
    kwargs, raw, ctx = fixture()
    scope = dec(kwargs["scope"])
    scope[9] = [1]
    for change in ({34: scope}, {33: ref(AC.DELEGATE, b"X" * 32)}):
        kwargs, raw, ctx = fixture(delegation=change)
        with pytest.raises(FederationValidationError):
            OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)


def test_signed_ownership_revocation_is_not_overridden_by_local_inventory():
    kwargs, raw, ctx = fixture(root={37: {1: 3, 2: SERVICE, 3: None}})
    with pytest.raises(FederationValidationError, match="revoked"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)


def test_signed_delegation_revocation_is_not_overridden_by_local_inventory():
    kwargs, raw, ctx = fixture(delegation={37: {1: 4, 2: C, 3: None}})
    with pytest.raises(FederationValidationError, match="revoked"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)


def test_before_at_after_ceiling_and_clock_rollback():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    assert adapter.validate(receipt, raw, **(ctx | {"now": 1699})) is receipt
    for now in (999, 1700, 1701, True):
        with pytest.raises(FederationValidationError):
            adapter.validate(receipt, raw, **(ctx | {"now": now}))


def test_stale_receipts_cannot_cross_adapter_or_reissuance():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    other = OfflineRegistrationAuthority(**kwargs)
    other.verify(raw, **ctx)
    with pytest.raises(FederationValidationError):
        other.validate(receipt, raw, **ctx)
    current = adapter.verify(raw, **ctx)
    with pytest.raises(FederationValidationError):
        adapter.validate(receipt, raw, **ctx)
    assert adapter.validate(current, raw, **ctx) is current


@pytest.mark.parametrize("observed", [1699, 1700])
def test_observed_time_cannot_roll_back_even_after_expiry_or_revision(observed):
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    if observed == 1700:
        with pytest.raises(FederationValidationError, match="expired"):
            adapter.validate(receipt, raw, **(ctx | {"now": observed}))
    else:
        assert adapter.validate(receipt, raw, **(ctx | {"now": observed})) is receipt
    with pytest.raises(FederationValidationError, match="clock rollback"):
        adapter.validate(receipt, raw, **(ctx | {"now": 1001}))
    adapter.advance_revision(2)
    with pytest.raises(FederationValidationError, match="clock rollback"):
        adapter.verify(raw, **(ctx | {"revision": 2}))


def test_signed_but_unlisted_record_and_missing_request_dependency_reject():
    kwargs, raw, ctx = fixture()
    _, _, other = fixture(delegation={7: 1850})
    with pytest.raises(FederationValidationError, match="inventory"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **(ctx | {"chain": other["chain"]}))
    body = dec(raw)
    body[10] = body[10][1:]
    body[11] = sha256(enc(body[10])).digest()
    with pytest.raises(FederationValidationError, match="dependencies"):
        OfflineRegistrationAuthority(**kwargs).verify(enc(body), **ctx)


def test_receipt_request_digest_prevents_even_valid_body_substitution():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    body = dec(raw)
    body[13] = 30
    with pytest.raises(FederationValidationError, match="changed"):
        adapter.validate(receipt, enc(body), **ctx)


@pytest.mark.parametrize(
    "field,value", [("revision", True), ("freshness_expires", True), ("record_inventory", True), ("signer_inventory", True)]
)
def test_boolean_or_untyped_trust_configuration_is_not_a_receipt_source(field, value):
    kwargs, _, _ = fixture()
    with pytest.raises(FederationValidationError):
        OfflineRegistrationAuthority(**(kwargs | {field: value}))


def test_denial_snapshots_only_narrow_and_never_clear_tombstones():
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    digest = next(iter(kwargs["record_inventory"]))[1]
    adapter.advance_revision(2, revoked_records=frozenset({digest}))
    adapter.advance_revision(3)
    with pytest.raises(FederationValidationError):
        adapter.verify(raw, **(ctx | {"revision": 3}))
    with pytest.raises(FederationValidationError):
        adapter.advance_revision(4, revoked_records=frozenset({b"?" * 32}))

# Stage 3 existing-contract negatives only. Supplied fixture trust is not
# provisioning, runtime freshness, durable restart or threshold admission.
def test_stage3_matching_signed_chain_and_request_cannot_replace_configured_inventory():
    # A02: deleting the exact configured inventory join would accept this swap.
    kwargs, _, _ = fixture()
    replacement, raw, ctx = fixture(delegation={7: 1850})
    with pytest.raises(FederationValidationError, match="inventory|dependencies"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)
    # Control: the independently supplied fixture inventory is the changed input.
    receipt = OfflineRegistrationAuthority(**replacement).verify(raw, **ctx)
    assert receipt.request_digest == sha256(raw).digest()


@pytest.mark.parametrize("missing", [0, 1, 2])
def test_stage3_every_used_signer_must_belong_to_pinned_inventory(missing):
    # A03: removing signer membership validation would accept a missing signer.
    kwargs, raw, ctx = fixture()
    kwargs["signer_inventory"] = tuple(a for i, a in enumerate(kwargs["signer_inventory"]) if i != missing)
    with pytest.raises(FederationValidationError, match="signer absent"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **ctx)


@pytest.mark.parametrize("denials", [frozenset({b"?" * 32}), frozenset({True}), {b"?" * 32}])
def test_stage3_invalid_denial_update_preserves_current_receipt(denials):
    # A06 local mutation boundary only: assigning revision/clearing the receipt
    # before validating denial input would incorrectly destroy the valid receipt.
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    with pytest.raises(FederationValidationError, match="unknown denial dependency"):
        adapter.advance_revision(2, revoked_records=denials)
    assert adapter.validate(receipt, raw, **ctx) is receipt
    # A valid successor still works: the rejected update did not consume revision2.
    adapter.advance_revision(2)
    with pytest.raises(FederationValidationError):
        adapter.validate(receipt, raw, **(ctx | {"revision": 2}))


def test_stage3_changed_revision_cannot_reissue_denied_dependency():
    # A07/A16 fixture scope: advancing revisions must not clear retained denials.
    kwargs, raw, ctx = fixture()
    adapter = OfflineRegistrationAuthority(**kwargs)
    receipt = adapter.verify(raw, **ctx)
    digest = sha256(ctx["key_authorization"].expected_payload).digest()
    adapter.advance_revision(2, revoked_records=frozenset({digest}))
    for revision in (2, 3, 4):
        if revision > 2:
            adapter.advance_revision(revision)
        with pytest.raises(FederationValidationError):
            adapter.validate(receipt, raw, **(ctx | {"revision": revision}))
        with pytest.raises(FederationValidationError, match="denied"):
            adapter.verify(raw, **(ctx | {"revision": revision}))


@pytest.mark.parametrize("signer_index", [0, 1, 2], ids=["key", "ownership", "delegation"])
@pytest.mark.parametrize("field,value", [("generation", 2), ("sequence", 2), ("not_before", 850), ("expires_at", 2050)])
def test_stage3_same_key_signer_metadata_requires_exact_pinned_identity(signer_index, field, value):
    # Local fixture trust only. Narrowing signer_identity to kid/key would admit
    # this substitution even though the configured signer identity did not change.
    kwargs, raw, ctx = fixture()
    evidence = (ctx["key_authorization"], *ctx["chain"])
    original = evidence[signer_index]
    changed_authority = replace(original.authority, **{field: value})
    changed = replace(original, authority=changed_authority)
    assert changed.message == original.message
    assert changed.expected_payload == original.expected_payload
    assert changed.authority.kid == original.authority.kid
    assert changed.authority.public_key.public_bytes_raw() == original.authority.public_key.public_bytes_raw()
    assert changed.authority.not_before <= ctx["now"] < changed.authority.expires_at
    replaced = tuple(changed if i == signer_index else item for i, item in enumerate(evidence))
    changed_ctx = ctx | {"key_authorization": replaced[0], "chain": replaced[1:]}
    with pytest.raises(FederationValidationError, match="signer absent from exact fixture inventory"):
        OfflineRegistrationAuthority(**kwargs).verify(raw, **changed_ctx)

    # Positive control: changing the explicit fixture inventory, not signatures,
    # makes the otherwise-valid evidence match. This is not runtime provisioning.
    matched = tuple(changed_authority if i == signer_index else item for i, item in enumerate(kwargs["signer_inventory"]))
    receipt = OfflineRegistrationAuthority(**(kwargs | {"signer_inventory": matched})).verify(raw, **changed_ctx)
    assert receipt.request_digest == sha256(raw).digest()
    assert receipt.admission_ceiling == 1700


@pytest.mark.parametrize("change", [None, "revision", "denial"], ids=["commit", "stale-receipt", "denied-dependency"])
def test_signed_fixture_receipt_revalidated_through_offline_coordinator(change):
    # Test-local projection only: neither this exporter nor OfflineDecision is a
    # runtime authority provider, authenticated transport, or provisioning API.
    from nbsr import connector_registration_offline as api

    kwargs, raw, ctx = fixture()
    authority = OfflineRegistrationAuthority(**kwargs)
    revision = [ctx["revision"]]
    issued = []
    calls = []
    projected = []

    class Transport:
        session = ctx["session"]
        closed = False

        def export(self, label, context):
            return sha256(b"public synthetic exporter" + label + context).digest()

        def close(self):
            self.closed = True

    transport = Transport()

    def verifier(request, current, now):
        # The integer connection ID belongs only to this fixture's exact object.
        assert current is transport and current.session == ctx["session"]
        assert request == raw
        context = ctx | {"now": now, "revision": revision[0]}
        if not issued:
            receipt = authority.verify(request, **context)
            issued.append(receipt)
            calls.append(("verify", receipt))
        else:
            receipt = issued[0]
            calls.append(("validate", receipt))
            assert authority.validate(receipt, request, **context) is receipt
        assert receipt.connection == ctx["connection"]
        assert receipt.session == current.session and receipt.request_id == ctx["request_id"]
        assert receipt.request_digest == sha256(request).digest()
        # References are projected only after this exact raw request is verified.
        decision = api.OfflineDecision(
            request_digest=receipt.request_digest,
            connection=current,
            session_id=receipt.session,
            expires_at=receipt.admission_ceiling,
            governing_profile="explicit-signed-fixture-projection",
            verified_record_refs=tuple(item[1] for item in dec(request)[10]),
            revision=receipt.revision,
        )
        projected.append(decision)
        return decision

    gateway = api.Coordinator(
        [api.ServiceConfig.from_request(dec(raw))], verifier, lambda: ctx["now"],
        epoch=b"e" * 16, nonce=lambda: b"n" * 32, registration_id=lambda: b"r" * 16,
        clock_skew_seconds=0, revision_source=lambda: revision[0],
    )
    challenge = gateway.request(transport, ctx["request_id"], 1, raw)
    context = api.exporter_context(transport.session, ctx["request_id"], raw, challenge)
    proof = enc({0: 1, 1: sha256(raw).digest(), 2: challenge[2], 3: transport.export(api.EXPORTER_LABEL, context)})
    state = gateway.connections[id(transport)]
    assert len(issued) == 1 and state.pending == ctx["request_id"]
    assert gateway.handle(transport) is None

    if change is not None:
        denied = frozenset({sha256(ctx["key_authorization"].expected_payload).digest()}) if change == "denial" else frozenset()
        authority.advance_revision(2, revoked_records=denied)
        revision[0] = 2
        with pytest.raises(FederationValidationError, match="receipt was not issued by this exact current verifier instance"):
            gateway.prove(transport, ctx["request_id"], 2, proof)
        assert state.pending is None and state.operations[ctx["request_id"]].result is None
        assert gateway.handle(transport) is None and gateway.counts()["owned"] == 0
        assert len(projected) == 1  # Failed revalidation cannot project a decision.
        assert gateway.close_attempt(transport) is True
    else:
        accepted = gateway.prove(transport, ctx["request_id"], 2, proof)
        receipt = issued[0]
        assert len(projected) == 2 and projected[0] == projected[1]
        assert projected[1].connection is transport
        assert projected[1].session_id == receipt.session
        assert projected[1].request_digest == receipt.request_digest
        assert projected[1].expires_at == receipt.admission_ceiling
        assert projected[1].revision == receipt.revision
        assert projected[1].verified_record_refs == tuple(item[1] for item in dec(raw)[10])
        assert accepted[1] == receipt.request_digest
        assert accepted[5] == ctx["now"] and accepted[6] == min(ctx["now"] + dec(raw)[13], receipt.admission_ceiling)
        assert accepted[8] == dec(raw)[11] and accepted[9] == dec(raw)[12]
        assert gateway.eligible(transport) is True
        assert gateway.close_owner(gateway.handle(transport)) is True
    assert calls == [("verify", issued[0]), ("validate", issued[0])]
    assert len(issued) == 1 and transport.closed is True
    assert id(transport) not in gateway.connections
    assert gateway.counts() == {"owned": 0, "eligible": 0, "pending": 0, "completed": 0}
