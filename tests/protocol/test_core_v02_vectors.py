from __future__ import annotations

from hashlib import sha256

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.registry import MessageType
from scripts.core_v02_vectors.crypto import (
    verify_cose_sign1,
    verify_route_open,
)
from scripts.core_v02_vectors.fixtures import FIXTURES
from scripts.core_v02_vectors.generate import build_valid_package
from scripts.core_v02_vectors.reference import (
    ConformanceState,
    ReferenceContext,
    apply_envelope,
    verify_envelope,
)


VALID_IDS = {
    "route-grant-payload",
    "route-grant-sign1",
    "client-hello-body",
    "client-hello",
    "edge-hello-body",
    "edge-hello",
    "route-open-proof-transcript",
    "route-open-proof-signature",
    "route-open",
    "route-accept",
    "route-reject",
    "stream-open",
    "stream-accept",
    "stream-reject",
}


def _context() -> ReferenceContext:
    return ReferenceContext(
        expected_core_version=2,
        source_operator_id=FIXTURES.source_operator_id,
        source_edge_id=FIXTURES.source_edge_id,
        destination_operator_id=FIXTURES.destination_operator_id,
        destination_edge_id=FIXTURES.destination_edge_id,
        route_grant_issuer_public_key=FIXTURES.route_grant_public_key,
        route_grant_kid=FIXTURES.kid,
        client_session_public_key=FIXTURES.session_public_key,
        now=FIXTURES.opened_at,
        accepted_record_sequence=FIXTURES.record_sequence,
        max_clock_skew_seconds=60,
        expected_policy_hash=FIXTURES.policy_hash,
    )


def test_valid_package_contains_exact_approved_artifact_set() -> None:
    package = build_valid_package()

    assert {artifact.entry.id for artifact in package.artifacts} == VALID_IDS
    assert len(package.artifacts) == 14
    assert all(artifact.entry.vector_class == "valid" for artifact in package.artifacts)
    assert all(artifact.entry.expected_outcome == "accept" for artifact in package.artifacts)


def test_valid_cbor_artifacts_are_deterministic_and_hash_exact() -> None:
    package = build_valid_package()

    for artifact in package.artifacts:
        assert len(artifact.wire) == artifact.entry.length
        assert sha256(artifact.wire).hexdigest() == artifact.entry.sha256
        if artifact.entry.artifact_type in {
            "core-object-cbor",
            "control-envelope-cbor",
            "proof-transcript-cbor",
        }:
            assert artifact.wire == encode_deterministic(decode_deterministic(artifact.wire))


def test_valid_route_grant_cose_and_route_open_proof_verify() -> None:
    artifacts = build_valid_package().artifact_map()
    payload = verify_cose_sign1(
        artifacts["route-grant-sign1"],
        FIXTURES.route_grant_public_key,
        FIXTURES.kid,
    )
    assert payload == artifacts["route-grant-payload"]
    verify_route_open(
        artifacts["route-open-proof-transcript"],
        artifacts["route-open-proof-signature"],
        FIXTURES.session_public_key,
    )


def test_valid_envelopes_apply_through_stream_accept() -> None:
    artifacts = build_valid_package().artifact_map()
    state = ConformanceState()
    for vector_id in (
        "client-hello",
        "edge-hello",
        "route-open",
        "route-accept",
        "stream-open",
        "stream-accept",
    ):
        envelope = verify_envelope(artifacts[vector_id], _context())
        state = apply_envelope(state, envelope)

    assert state.transport_session_active
    assert FIXTURES.channel_id in state.active_channel_ids
    assert 4 in state.active_stream_ids


def test_route_and_stream_rejections_embed_safe_protocol_error() -> None:
    artifacts = build_valid_package().artifact_map()

    route_reject = verify_envelope(artifacts["route-reject"], _context())
    stream_reject = verify_envelope(artifacts["stream-reject"], _context())

    assert route_reject.message_type is MessageType.ROUTE_REJECT
    assert route_reject.protocol_error is not None
    assert stream_reject.message_type is MessageType.STREAM_REJECT
    assert stream_reject.protocol_error is not None
