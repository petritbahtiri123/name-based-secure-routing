from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType

from nbsr.federation.delegation import DelegationScope
from nbsr.federation.fields import FederationValidationError, _Record, _authority_reference, _bytes, _extensions, _fail, _uint
from nbsr.federation.registry import DecisionOutcome, ObjectType, ReasonCode
from nbsr.protocol.cbor import encode_deterministic


def _base(payload: dict[int, object], object_type: ObjectType, required: set[int], allowed: set[int]) -> None:
    if not required <= set(payload) or set(payload) - allowed or payload.get(1) != object_type or payload.get(2) != 1:
        _fail("payload has missing, unknown, or invalid fields")
    if 31 in payload:
        _extensions(payload[31])


@dataclass(frozen=True, slots=True)
class FederationAuthorityProof(_Record):
    REQUIRED = {1, 2, *range(32, 43)}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> FederationAuthorityProof:
        payload = cls._decode(raw)
        _base(payload, ObjectType.FederationAuthorityProof, cls.REQUIRED, cls.ALLOWED)
        for key, label in (
            (32, "proof ID"),
            (33, "authority root"),
            (35, "service ID"),
            (38, "destination Operator ID"),
            (39, "trust bundle"),
            (40, "checkpoint"),
            (41, "revocation commitment"),
        ):
            _bytes(payload[key], 1 if key == 32 else 32, 64 if key == 32 else 32, label)
        if (
            type(payload[34]) is not list
            or not 1 <= len(payload[34]) <= 64
            or any(type(item) is not bytes or len(item) != 32 for item in payload[34])
            or payload[34] != sorted(set(payload[34]))
        ):
            _fail("authority chain digests must be sorted unique")
        DelegationScope.from_mapping(payload[36])
        if payload[37] is not None:
            _bytes(payload[37], 32, 32, "source Operator ID")
        _uint(payload[42], 0, 253_402_300_799, "valid_until")
        return cls(MappingProxyType(payload))

    def verify(
        self,
        *,
        now: int,
        ownership_root_digest: bytes,
        chain_digests: set[bytes],
        service_id: bytes,
        canonical_name: str,
        source_operator_id: bytes,
        destination_operator_id: bytes,
        trust_bundle_digest: bytes,
        checkpoint_digest: bytes,
        revocation_commitment: bytes,
    ) -> None:
        expected = (
            ownership_root_digest,
            set(self._payload[34]),
            service_id,
            canonical_name,
            source_operator_id,
            destination_operator_id,
            trust_bundle_digest,
            checkpoint_digest,
            revocation_commitment,
        )
        actual = (
            self._payload[33],
            chain_digests,
            self._payload[35],
            self._payload[36][1],
            self._payload[37],
            self._payload[38],
            self._payload[39],
            self._payload[40],
            self._payload[41],
        )
        if expected != actual or type(now) is not int or now > self._payload[42]:
            _fail("authority proof binding, freshness, or dependency is invalid")

    def advance(self) -> None:
        _fail("authority proof is immutable one-shot evidence")


def _dependencies(value: object) -> tuple[tuple[int, bytes], ...]:
    if type(value) is not list or not 1 <= len(value) <= 256:
        _fail("dependency set is malformed")
    result = tuple((item[0], item[1]) for item in value if type(item) is list and len(item) == 2)
    if (
        len(result) != len(value)
        or any(type(kind) is not int or not 1 <= kind <= 18 or type(digest) is not bytes or len(digest) != 32 for kind, digest in result)
        or list(result) != sorted(set(result))
    ):
        _fail("dependency set must be sorted unique")
    return result


@dataclass(frozen=True, slots=True)
class FederationAuthorizationContext(_Record):
    REQUIRED = {1, 2, 3, 9, *range(32, 47)}
    ALLOWED = REQUIRED | {31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> FederationAuthorizationContext:
        payload = cls._decode(raw)
        _base(payload, ObjectType.FederationAuthorizationContext, cls.REQUIRED, cls.ALLOWED)
        _authority_reference(payload[3], "issuer")
        _uint(payload[9], 0, 253_402_300_799, "effective_at")
        _bytes(payload[32], 1, 64, "context ID")
        for key in range(33, 40):
            _bytes(payload[key], 32, 32, "context binding")
        DelegationScope.from_mapping(payload[40])
        _uint(payload[41], payload[9] + 1, 253_402_300_799, "valid_until")
        _uint(payload[42], 1, (1 << 64) - 1, "affected generation")
        _uint(payload[43], 1, (1 << 64) - 1, "affected sequence")
        dependencies = _dependencies(payload[44])
        _bytes(payload[45], 32, 32, "dependency digest")
        if hashlib.sha256(encode_deterministic([list(item) for item in dependencies])).digest() != payload[45]:
            _fail("dependency set digest is invalid")
        _bytes(payload[46], 32, 32, "route context digest")
        return cls(MappingProxyType(payload))

    @property
    def route_context_digest(self) -> bytes:
        return self._payload[46]

    @property
    def dependencies(self) -> frozenset[bytes]:
        return frozenset(item[1] for item in self._payload[44])

    def verify(
        self,
        *,
        now: int,
        source_operator_id: bytes,
        destination_operator_id: bytes,
        service_id: bytes,
        authority_proof_digest: bytes,
        trust_bundle_digest: bytes,
        checkpoint_digest: bytes,
        policy_digest: bytes,
        protocol: int,
        port: int,
        action: int,
        affected_version: tuple[int, int],
        route_context_digest: bytes,
    ) -> None:
        scope = self._payload[40]
        expected = (
            source_operator_id,
            destination_operator_id,
            service_id,
            authority_proof_digest,
            trust_bundle_digest,
            checkpoint_digest,
            policy_digest,
            affected_version,
            route_context_digest,
        )
        actual = (*[self._payload[key] for key in range(33, 40)], (self._payload[42], self._payload[43]), self._payload[46])
        in_port = any(start <= port <= end for start, end in scope[7])
        if (
            expected != actual
            or not self._payload[9] <= now <= self._payload[41]
            or protocol not in scope[8]
            or not in_port
            or action not in scope[9]
        ):
            _fail("authorization context binding is invalid")


@dataclass(frozen=True, slots=True)
class AuthorizationEvidence:
    operator_id: bytes
    peer_operator_id: bytes
    endpoint_operator_id: bytes
    service_id: bytes
    authority_proof: FederationAuthorityProof | None
    proof_pending_until: int | None
    ownership_root_digest: bytes
    chain_digests: frozenset[bytes]
    canonical_name: str
    revocation_commitment: bytes
    trust_bundle_digest: bytes
    trust_bundle_version: tuple[int, int]
    checkpoint_digest: bytes
    checkpoint_compatible: bool
    policy_digest: bytes
    allowed_protocols: frozenset[int]
    allowed_ports: frozenset[int]
    allowed_actions: frozenset[int]
    revoked_dependencies: frozenset[bytes]
    now: int


@dataclass(frozen=True, slots=True)
class FederationResult:
    outcome: DecisionOutcome
    reason: ReasonCode


class BilateralAuthorizer:
    def __init__(self, accepted_context_digests: frozenset[bytes] = frozenset()) -> None:
        self._decisions: dict[tuple[object, ...], FederationResult] = {}
        self._source_accepted: set[bytes] = set()
        self._previously_accepted = accepted_context_digests

    def authorize_source(
        self,
        authenticated_context: object,
        evidence: AuthorizationEvidence,
        *,
        protocol: int = 6,
        port: int = 443,
        action: int = 1,
        route_context_digest: bytes | None = None,
    ) -> FederationResult:
        context = self._authenticated_context(authenticated_context)
        if context.digest in self._previously_accepted:
            return FederationResult(DecisionOutcome.REJECT, ReasonCode.ERR_REPLAY)
        result = self._authorize(
            "source",
            context,
            evidence,
            context._payload[33],
            context._payload[34],
            protocol,
            port,
            action,
            context.route_context_digest if route_context_digest is None else route_context_digest,
        )
        if result.outcome is DecisionOutcome.ACCEPT:
            self._source_accepted.add(context.digest)
        return result

    def authorize_destination(
        self,
        authenticated_context: object,
        evidence: AuthorizationEvidence,
        *,
        protocol: int = 6,
        port: int = 443,
        action: int = 1,
        route_context_digest: bytes | None = None,
    ) -> FederationResult:
        context = self._authenticated_context(authenticated_context)
        if context.digest not in self._source_accepted:
            return FederationResult(DecisionOutcome.PENDING, ReasonCode.ERR_EVIDENCE_MISSING)
        return self._authorize(
            "destination",
            context,
            evidence,
            context._payload[34],
            context._payload[33],
            protocol,
            port,
            action,
            context.route_context_digest if route_context_digest is None else route_context_digest,
        )

    @staticmethod
    def _authenticated_context(value: object) -> FederationAuthorizationContext:
        from nbsr.federation.cose import AuthenticatedBilateralContext

        if not isinstance(value, AuthenticatedBilateralContext) or not isinstance(value.context, FederationAuthorizationContext):
            _fail("authorization context lacks bilateral COSE authentication")
        return value.context

    def _authorize(
        self,
        side: str,
        context: FederationAuthorizationContext,
        evidence: AuthorizationEvidence,
        own: bytes,
        peer: bytes,
        protocol: int,
        port: int,
        action: int,
        route_context_digest: bytes,
    ) -> FederationResult:
        replay_key = (
            side,
            context.digest,
            evidence.operator_id,
            evidence.endpoint_operator_id,
            protocol,
            port,
            action,
            route_context_digest,
            evidence.now,
        )
        if replay_key in self._decisions:
            return self._decisions[replay_key]
        proof = evidence.authority_proof
        if proof is None:
            outcome = (
                DecisionOutcome.PENDING
                if evidence.proof_pending_until is not None and evidence.now <= evidence.proof_pending_until
                else DecisionOutcome.REJECT
            )
            return FederationResult(outcome, ReasonCode.ERR_EVIDENCE_MISSING)
        try:
            proof.verify(
                now=evidence.now,
                ownership_root_digest=evidence.ownership_root_digest,
                chain_digests=set(evidence.chain_digests),
                service_id=evidence.service_id,
                canonical_name=evidence.canonical_name,
                source_operator_id=context._payload[33],
                destination_operator_id=context._payload[34],
                trust_bundle_digest=evidence.trust_bundle_digest,
                checkpoint_digest=evidence.checkpoint_digest,
                revocation_commitment=evidence.revocation_commitment,
            )
            context.verify(
                now=evidence.now,
                source_operator_id=context._payload[33],
                destination_operator_id=context._payload[34],
                service_id=evidence.service_id,
                authority_proof_digest=proof.digest,
                trust_bundle_digest=evidence.trust_bundle_digest,
                checkpoint_digest=evidence.checkpoint_digest,
                policy_digest=evidence.policy_digest,
                protocol=protocol,
                port=port,
                action=action,
                affected_version=(context._payload[42], context._payload[43]),
                route_context_digest=route_context_digest,
            )
        except FederationValidationError:
            return FederationResult(DecisionOutcome.REJECT, ReasonCode.ERR_AUTHORITY)
        invalid = (
            evidence.operator_id != own
            or evidence.peer_operator_id != peer
            or evidence.endpoint_operator_id != own
            or evidence.service_id != context._payload[35]
            or proof.digest != context._payload[36]
            or evidence.trust_bundle_digest != context._payload[37]
            or evidence.checkpoint_digest != context._payload[38]
            or not evidence.checkpoint_compatible
            or evidence.policy_digest != context._payload[39]
            or not context._payload[9] <= evidence.now <= min(context._payload[41], proof._payload[42])
            or protocol not in evidence.allowed_protocols
            or port not in evidence.allowed_ports
            or action not in evidence.allowed_actions
            or bool(context.dependencies & evidence.revoked_dependencies)
        )
        if invalid:
            return FederationResult(DecisionOutcome.REJECT, ReasonCode.ERR_AUTHORITY)
        result = FederationResult(DecisionOutcome.ACCEPT, ReasonCode.NONE)
        self._decisions[replay_key] = result
        return result
