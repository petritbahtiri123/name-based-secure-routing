"""Local composition check for an explicitly witness-required normal event.

Uses real existing COSE, witness and checkpoint continuity verifiers under public
test configuration. This is not a trust provider, inclusion verifier, durable
floor, or permission to waive other governing obligations.
"""

from dataclasses import dataclass

from nbsr.federation import FederationValidationError, KeyPurpose, ObjectType
from nbsr.federation.cose import FederationAuthority, authenticate_witness_sign1, verify_federation_sign1
from nbsr.federation.transparency import TransparencyVerifier, verify_witness_threshold
from nbsr.protocol.cbor import decode_deterministic
from scripts.normal_revocation_conformance import check_case, outcome


@dataclass(frozen=True)
class WitnessFixtureInputs:
    checkpoint_message: bytes
    log_authority: FederationAuthority
    witness_messages: tuple[tuple[bytes, FederationAuthority, str], ...]
    configured_witnesses: dict[bytes, tuple[str, bytes]]
    replay_contexts: dict[bytes, bytes]
    required: int
    maximum_staleness: int
    previous_checkpoint_message: bytes | None = None
    consistency_message: bytes | None = None


def check_witness_bound_case(case: dict, evidence: WitnessFixtureInputs | None) -> dict:
    """No caller status string can substitute for the required signed evidence."""
    if type(evidence) is not WitnessFixtureInputs:
        return outcome("PENDING", "ERR_EVIDENCE_MISSING")
    if type(evidence.required) is not int or evidence.required not in (2, 3):
        return outcome("REJECT", "ERR_AUTHORITY")
    if type(evidence.maximum_staleness) is not int or evidence.maximum_staleness < 0:
        return outcome("REJECT", "ERR_SCHEMA")
    try:
        now = case["validation_context"]["now"]

        def signed(message, kind):
            return verify_federation_sign1(
                message,
                evidence.log_authority,
                kind,
                now,
                expected_key_purpose=KeyPurpose.TRANSPARENCY_LOG,
            )

        checkpoint = signed(evidence.checkpoint_message, ObjectType.TransparencyCheckpoint)
        # The continuity verifier's idempotent branch does not check freshness;
        # required evidence freshness must be checked before every use.
        checkpoint.require_fresh(now, maximum_staleness=evidence.maximum_staleness)
        previous = (
            None
            if evidence.previous_checkpoint_message is None
            else signed(evidence.previous_checkpoint_message, ObjectType.TransparencyCheckpoint)
        )
        consistency = None if evidence.consistency_message is None else signed(evidence.consistency_message, ObjectType.ConsistencyProof)
        if TransparencyVerifier(previous).accept_checkpoint(
            checkpoint, now=now, consistency=consistency, maximum_staleness=evidence.maximum_staleness
        ) not in ("ACCEPT", "IDEMPOTENT"):
            return outcome("REJECT", "ERR_AUTHORITY")
        payload = decode_deterministic(bytes.fromhex(case["record_hex"]))
        reference = payload[39]
        if (reference[1], reference[2], reference[3], payload[33]) != (
            checkpoint.log_id,
            checkpoint.digest,
            checkpoint.tree_size,
            checkpoint.scope.to_mapping(),
        ):
            return outcome("REJECT", "ERR_SCOPE")
        witnesses = [
            authenticate_witness_sign1(message, authority, organization, now)
            for message, authority, organization in evidence.witness_messages
        ]
        verify_witness_threshold(
            witnesses,
            checkpoint,
            evidence.required,
            now=now,
            replay_contexts=evidence.replay_contexts,
            configured_witnesses=evidence.configured_witnesses,
        )
        # Remaining fixture obligations still have to pass. This wrapper never
        # replaces a missing obligation with a satisfied marker.
        return check_case(case)
    except (FederationValidationError, ValueError, TypeError, KeyError):
        return outcome("REJECT", "ERR_AUTHORITY")
