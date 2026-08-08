from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation.authorization import AuthorizationEvidence, BilateralAuthorizer
from nbsr.federation.cose import AuthenticatedBilateralContext
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.registry import DecisionOutcome
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


SOURCE_ADMISSION_PURPOSE = "nbsr-federation-source-admission"
DESTINATION_ADMISSION_PURPOSE = "nbsr-federation-destination-admission"


@dataclass(frozen=True, slots=True)
class LocalAdmissionAuthority:
    kid: bytes
    private_key: Ed25519PrivateKey

    def __post_init__(self) -> None:
        if type(self.kid) is not bytes or not 1 <= len(self.kid) <= 64 or not isinstance(
            self.private_key, Ed25519PrivateKey
        ):
            raise FederationValidationError("local admission authority is invalid")


@dataclass(frozen=True, slots=True)
class LocalAdmissionAttestor:
    source: LocalAdmissionAuthority
    destination: LocalAdmissionAuthority

    def __post_init__(self) -> None:
        if type(self.source) is not LocalAdmissionAuthority or type(self.destination) is not LocalAdmissionAuthority:
            raise FederationValidationError("local admission authorities are invalid")
        if self.source.kid == self.destination.kid:
            raise FederationValidationError("source and destination admission authorities must be distinct")

    def authorize_and_attest(
        self,
        authorizer: BilateralAuthorizer,
        authenticated: AuthenticatedBilateralContext,
        source_evidence: AuthorizationEvidence,
        destination_evidence: AuthorizationEvidence,
        *,
        route_grant_digest: bytes,
        protocol: int,
        port: int,
    ) -> tuple[bytes, bytes]:
        source = authorizer.authorize_source(authenticated, source_evidence, protocol=protocol, port=port)
        if source.outcome is not DecisionOutcome.ACCEPT:
            raise FederationValidationError(f"source federation admission failed: {source.reason.name}")
        source_attestation = self._attest(SOURCE_ADMISSION_PURPOSE, self.source, authenticated, source_evidence, route_grant_digest, protocol, port)
        destination = authorizer.authorize_destination(authenticated, destination_evidence, protocol=protocol, port=port)
        if destination.outcome is not DecisionOutcome.ACCEPT:
            raise FederationValidationError(f"destination federation admission failed: {destination.reason.name}")
        destination_attestation = self._attest(DESTINATION_ADMISSION_PURPOSE, self.destination, authenticated, destination_evidence, route_grant_digest, protocol, port)
        return source_attestation, destination_attestation

    @staticmethod
    def _attest(purpose: str, authority: LocalAdmissionAuthority, authenticated: AuthenticatedBilateralContext, evidence: AuthorizationEvidence, route_grant_digest: bytes, protocol: int, port: int) -> bytes:
        context = authenticated.context
        payload = encode_deterministic({
            0: 1, 1: purpose,
            2: authenticated.source_authority.operator_id,
            3: authenticated.destination_authority.operator_id,
            4: evidence.service_id, 5: evidence.canonical_name,
            6: protocol, 7: port,
            8: route_grant_digest,
            9: authenticated.context.digest,
            10: context._payload[9], 11: context._payload[41],
            12: context._payload[42], 13: context._payload[43],
            14: sorted(context.dependencies),
        })
        return sign1(payload, authority.kid, authority.private_key)
