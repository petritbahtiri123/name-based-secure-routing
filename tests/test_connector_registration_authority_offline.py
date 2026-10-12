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
