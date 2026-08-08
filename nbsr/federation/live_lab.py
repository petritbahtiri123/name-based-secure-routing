from __future__ import annotations

from dataclasses import dataclass

from nbsr.federation.authorization import AuthorizationEvidence, BilateralAuthorizer
from nbsr.federation.cose import AuthenticatedBilateralContext
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.local_attestation import LocalAdmissionAttestor
from nbsr.two_operator_lab import AdmissionCapability, AdmissionContext, TwoOperatorLab


_VERIFIED_LIVE_TOKEN = object()


@dataclass(frozen=True, slots=True)
class VerifiedLiveFederationRoute:
    source_operator_id: bytes
    destination_operator_id: bytes
    service_id: bytes
    federation_context_digest: bytes
    route_context_digest: bytes
    receipt: AdmissionCapability
    source_attestation: bytes
    destination_attestation: bytes
    _token: object

    def __post_init__(self) -> None:
        if self._token is not _VERIFIED_LIVE_TOKEN:
            raise FederationValidationError("verified live federation routes are issued only after bilateral admission")


class LiveFederationAdmission:
    """Compose bilateral Federation authority with the sealed WP7 admission path."""

    __slots__ = (
        "_authorizer",
        "_lab",
        "_source_operator_id",
        "_destination_operator_id",
        "_federation_service_id",
        "_wp7_service_id",
        "_attestor",
    )

    def __init__(
        self,
        authorizer: BilateralAuthorizer,
        lab: TwoOperatorLab,
        *,
        source_operator_id: bytes,
        destination_operator_id: bytes,
        federation_service_id: bytes,
        wp7_service_id: str,
        attestor: LocalAdmissionAttestor,
    ) -> None:
        if (
            type(authorizer) is not BilateralAuthorizer
            or type(lab) is not TwoOperatorLab
            or type(source_operator_id) is not bytes
            or len(source_operator_id) != 32
            or type(destination_operator_id) is not bytes
            or len(destination_operator_id) != 32
            or source_operator_id == destination_operator_id
            or type(federation_service_id) is not bytes
            or len(federation_service_id) != 32
            or type(wp7_service_id) is not str
            or wp7_service_id != lab.expected_context.service_id
            or type(attestor) is not LocalAdmissionAttestor
        ):
            raise FederationValidationError("live federation admission inputs are invalid")
        self._authorizer = authorizer
        self._lab = lab
        self._source_operator_id = source_operator_id
        self._destination_operator_id = destination_operator_id
        self._federation_service_id = federation_service_id
        self._wp7_service_id = wp7_service_id
        self._attestor = attestor

    def authorize(
        self,
        authenticated_context: AuthenticatedBilateralContext,
        source_evidence: AuthorizationEvidence,
        destination_evidence: AuthorizationEvidence,
        route: AdmissionContext,
        *,
        now_ms: int,
        protocol: int = 6,
        port: int = 443,
    ) -> VerifiedLiveFederationRoute:
        if (
            type(authenticated_context) is not AuthenticatedBilateralContext
            or type(source_evidence) is not AuthorizationEvidence
            or type(destination_evidence) is not AuthorizationEvidence
            or type(route) is not AdmissionContext
            or type(now_ms) is not int
            or now_ms < 0
        ):
            raise FederationValidationError("live federation admission context is invalid")
        source_id = authenticated_context.source_authority.operator_id
        destination_id = authenticated_context.destination_authority.operator_id
        if (
            source_id != self._source_operator_id
            or destination_id != self._destination_operator_id
            or route.source_operator != self._lab.source.operator_id
            or route.destination_operator != self._lab.destination.operator_id
            or route.service_id != self._wp7_service_id
            or source_evidence.service_id != self._federation_service_id
            or destination_evidence.service_id != self._federation_service_id
        ):
            raise FederationValidationError("Federation and WP7 route bindings disagree")
        source_attestation, destination_attestation = self._attestor.authorize_and_attest(
            self._authorizer,
            authenticated_context,
            source_evidence,
            destination_evidence,
            route_grant_digest=bytes.fromhex(route.route_grant_digest),
            protocol=protocol,
            port=port,
        )
        receipt = self._lab.admit(
            route,
            amount=1,
            source_started_ms=max(0, now_ms - 2),
            source_completed_ms=max(0, now_ms - 1),
            destination_started_ms=now_ms,
            destination_completed_ms=now_ms,
        )
        return VerifiedLiveFederationRoute(
            source_id,
            destination_id,
            source_evidence.service_id,
            authenticated_context.context.digest,
            authenticated_context.context.route_context_digest,
            receipt,
            source_attestation,
            destination_attestation,
            _VERIFIED_LIVE_TOKEN,
        )
