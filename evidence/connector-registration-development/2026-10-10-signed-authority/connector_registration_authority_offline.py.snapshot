"""Signed-fixture verification only; not a runtime authority or receipt transport.

Fixture signer claims/inventory are explicit local trust inputs. Real COSE checks
do not authenticate their origin. Instance-local issuance identity prevents an
ordinary caller from substituting a dataclass; Python object identity is NOT an
adversarial process boundary. No keys, sockets, discovery, timers or revocation
receipt producer are implemented here. Only one latest receipt is retained.
"""

from dataclasses import dataclass, replace
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.connector_registration_offline import MAX_TIME, bstr, decode_body, operation_counter, uint
from nbsr.federation.cose import FederationAuthority, verify_federation_sign1
from nbsr.federation.delegation import DelegationScope, DelegationVerifier, SignedFederationObject
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.profile import FederationProfile
from nbsr.federation.registry import KeyLifecycle, KeyPurpose, ObjectType
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.errors import ProtocolViolation

PROFILE = "connector-registration-development-v1"
ACTION = 24576  # Only the selected fixture profile; never a global action ID.


def require(condition, message):
    if not condition:
        raise FederationValidationError(message)


def signer_identity(a):
    require(type(a) is FederationAuthority, "explicit fixture signer required")
    require(
        isinstance(a.public_key, Ed25519PublicKey)
        and type(a.purpose) is KeyPurpose
        and type(a.lifecycle) is KeyLifecycle
        and type(a.revoked) is bool
        and type(a.kid) is bytes
        and 1 <= len(a.kid) <= 64
        and bstr(a.operator_id, 32)
        and uint(a.generation, 1)
        and uint(a.sequence, 1)
        and uint(a.not_before, 0, MAX_TIME)
        and uint(a.expires_at, a.not_before, MAX_TIME),
        "invalid fixture signer identity",
    )
    return (
        a.kid,
        a.public_key.public_bytes_raw(),
        a.operator_id,
        a.purpose,
        a.lifecycle,
        a.generation,
        a.sequence,
        a.not_before,
        a.expires_at,
        a.revoked,
    )


@dataclass(frozen=True, slots=True)
class OfflineVerifiedReceipt:
    profile: str
    action: int
    connection: int
    session: bytes
    request_id: bytes
    peer_thumbprint: bytes
    request_digest: bytes
    revision: int
    issued_at: int
    admission_ceiling: int
    provenance: tuple


class OfflineRegistrationAuthority:
    """Serialized, single-profile fixture verifier; no runtime imports or fallback."""

    def __init__(self, *, profile, policy_request, scope, record_inventory, signer_inventory, revision, freshness_expires, freshness_ref):
        require(type(profile) is str and profile == PROFILE, "unsupported fixture profile")
        require(
            uint(revision, 1) and uint(freshness_expires, 0, MAX_TIME) and bstr(freshness_ref, 32),
            "explicit fixture freshness/revision required",
        )
        require(type(record_inventory) is frozenset and 3 <= len(record_inventory) <= 64, "exact fixture record inventory required")
        require(
            all(
                type(item) is tuple
                and len(item) == 2
                and type(item[0]) is ObjectType
                and item[0] in (ObjectType.KeyAuthorizationRecord, ObjectType.NameOwnershipRecord, ObjectType.DelegationRecord)
                and bstr(item[1], 32)
                for item in record_inventory
            ),
            "invalid record inventory",
        )
        require(type(signer_inventory) is tuple and 1 <= len(signer_inventory) <= 64, "fixture signer inventory required")
        self._signers = frozenset(signer_identity(a) for a in signer_inventory)
        self._inventory = record_inventory
        self._policy = self._body(policy_request)
        self._scope = DelegationScope.from_bytes(scope)
        selected = self._scope.to_mapping()
        require(
            selected[2] == self._policy[3]
            and selected[4] == self._policy[4]
            and selected[5] == self._policy[5]
            and selected[9] == [ACTION]
            and selected[10] is False
            and selected[11] == 0,
            "fixture scope must be exact registration-only scope",
        )
        self._revision = revision
        self._freshness_expires = freshness_expires
        self._freshness_ref = freshness_ref
        self._revoked = frozenset()
        self._issued = None
        self._observed_now = 0

    @staticmethod
    def _body(raw):
        require(type(raw) is bytes, "serialized request required")
        try:
            return decode_body("REQUEST", raw)
        except (ProtocolViolation, TypeError, ValueError) as exc:
            raise FederationValidationError("invalid registration request") from exc

    def advance_revision(self, revision, *, revoked_records=frozenset()):
        """Explicit offline denial snapshot, never authenticated revocation delivery.

        This can only invalidate receipts and add denials. It cannot clear a
        tombstone, import an event, extend signed validity or publish authority.
        """
        require(uint(revision, self._revision + 1), "revision must increase")
        require(
            type(revoked_records) is frozenset
            and all(bstr(v, 32) for v in revoked_records)
            and revoked_records <= {digest for _, digest in self._inventory},
            "unknown denial dependency",
        )
        self._revision = revision
        self._revoked |= revoked_records
        self._issued = None

    def _signed(self, signed, kind):
        require(type(signed) is SignedFederationObject, "signed evidence required, not a parsed record")
        require(type(signed.message) is bytes and type(signed.expected_payload) is bytes, "serialized signed evidence required")
        require(signed.current_record is None and signed.transition is None, "this bounded fixture inventory supports genesis records only")
        require(signer_identity(signed.authority) in self._signers, "signer absent from exact fixture inventory")
        digest = sha256(signed.expected_payload).digest()
        require((kind, digest) in self._inventory, "record absent from exact fixture inventory")
        require(digest not in self._revoked, "fixture dependency denied")
        return digest

    def _evaluate(self, raw, *, connection, session, request_id, peer_key, key_authorization, chain, now, revision, issuing):
        require(
            uint(connection, 1)
            and bstr(session, 16, True)
            and bstr(request_id, 16, True)
            and bstr(peer_key, 32)
            and uint(now, 0, MAX_TIME)
            and uint(revision, 1)
            and revision == self._revision,
            "invalid or stale registration binding",
        )
        require(now >= self._observed_now, "clock rollback")
        # Caller-supplied logical time is a fixture input. Retain observations
        # even when authority validation fails, so expiry cannot be undone.
        self._observed_now = now
        try:
            operation_counter(session, request_id)
        except ProtocolViolation as exc:
            raise FederationValidationError("request/session correlation") from exc
        body = self._body(raw)
        require(not issuing or body[14] == now, "fixture request freshness")
        require(all(body[k] == self._policy[k] for k in (2, 3, 4, 5, 6, 7, 8, 12)), "principal/service/gateway/policy pin")
        require(sha256(peer_key).digest() == body[8], "peer public key does not match request")
        require(type(chain) is tuple and 2 <= len(chain) <= FederationProfile.max_chain_objects, "complete signed ancestry required")
        key_digest = self._signed(key_authorization, ObjectType.KeyAuthorizationRecord)
        records = [(ObjectType.KeyAuthorizationRecord, key_digest)]
        for index, item in enumerate(chain):
            kind = ObjectType.NameOwnershipRecord if index == 0 else ObjectType.DelegationRecord
            records.append((kind, self._signed(item, kind)))
        require(len(set(records)) == len(records) and frozenset(records) == self._inventory, "complete exact fixture inventory required")
        refs = sorted([[int(kind), digest] for kind, digest in records], key=encode_deterministic)
        require(
            body[9] == key_digest and body[10] == refs and body[11] == sha256(encode_deterministic(refs)).digest(),
            "complete request dependencies must match verified inventory",
        )
        key = verify_federation_sign1(
            key_authorization.message,
            key_authorization.authority,
            ObjectType.KeyAuthorizationRecord,
            now,
            expected_payload=key_authorization.expected_payload,
            expected_key_purpose=KeyPurpose.FEDERATION_TRANSPORT,
        )
        require(
            key.operator_id == body[4]
            and key.key_id == body[7]
            and key.public_key == peer_key
            and key.key_lifecycle == KeyLifecycle.ACTIVE
            and not key._payload[38],
            "transport key not currently authorized for exact peer",
        )
        leaf = DelegationVerifier.verify(chain, self._scope, now)
        require(leaf.delegatee_id == body[4], "delegation does not grant the connector operator")
        # Existing validators retain their inclusive record boundaries. The
        # registration eligibility ceiling below is deliberately exclusive.
        provenance = []
        all_signed = (key_authorization, *chain)
        for (kind, digest), signed in zip(records, all_signed, strict=True):
            # Bytes were authenticated above; use the existing record decoders
            # through the verifier to obtain current validity, not request claims.
            purpose = {
                ObjectType.KeyAuthorizationRecord: KeyPurpose.FEDERATION_TRANSPORT,
                ObjectType.NameOwnershipRecord: KeyPurpose.NAME_OWNERSHIP,
                ObjectType.DelegationRecord: KeyPurpose.DELEGATION,
            }[kind]
            record = verify_federation_sign1(
                signed.message, signed.authority, kind, now, expected_payload=signed.expected_payload, expected_key_purpose=purpose
            )
            provenance.append(("signed-record", int(kind), digest, record.expires_at))
            provenance.append(("fixture-signer", int(signed.authority.purpose), digest, signed.authority.expires_at))
        provenance.append(("fixture-freshness", PROFILE, self._freshness_ref, self._freshness_expires))
        ceiling = min(item[3] for item in provenance)
        require(now < ceiling, "admission ceiling expired")
        return OfflineVerifiedReceipt(
            PROFILE, ACTION, connection, session, request_id, body[8], sha256(raw).digest(), revision, now, ceiling, tuple(provenance)
        )

    def verify(self, raw, **context):
        receipt = self._evaluate(raw, **context, issuing=True)
        self._issued = receipt
        return receipt

    def validate(self, receipt, raw, **context):
        require(
            type(receipt) is OfflineVerifiedReceipt and receipt is self._issued,
            "receipt was not issued by this exact current verifier instance",
        )
        require(uint(context.get("now"), receipt.issued_at, MAX_TIME), "clock rollback or invalid time")
        current = self._evaluate(raw, **context, issuing=False)
        require(replace(current, issued_at=receipt.issued_at) == receipt, "receipt binding or authority changed")
        return receipt
