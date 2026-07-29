from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.models import RouteGrant
from nbsr.protocol.registry import ErrorCode, MessageType
from nbsr.protocol.schemas import encode_model
from scripts.core_v02_vectors.crypto import (
    encode_cose_sign1,
    encode_route_open_transcript,
    sign_route_open,
)
from scripts.core_v02_vectors.fixtures import FIXTURES
from scripts.core_v02_vectors.manifest import VectorEntry, VectorManifest


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    entry: VectorEntry
    wire: bytes


@dataclass(frozen=True, slots=True)
class GeneratedPackage:
    manifest: VectorManifest
    artifacts: tuple[GeneratedArtifact, ...]
    support_files: tuple[tuple[str, bytes], ...]

    def artifact_map(self) -> Mapping[str, bytes]:
        return {artifact.entry.id: artifact.wire for artifact in self.artifacts}

    def file_map(self) -> Mapping[str, bytes]:
        files = {artifact.entry.artifact_path: artifact.wire for artifact in self.artifacts}
        files.update(dict(self.support_files))
        return files


def _request_id(increment: int) -> bytes:
    return FIXTURES.request_id[:-1] + bytes([FIXTURES.request_id[-1] + increment])


def _envelope(
    message_type: MessageType,
    request_id: bytes,
    sequence: int,
    body: dict[int, object],
) -> bytes:
    return encode_deterministic(
        {
            0: 2,
            1: int(message_type),
            2: request_id,
            3: FIXTURES.session_id,
            4: sequence,
            5: body,
        }
    )


def _entry(
    vector_id: str,
    wire: bytes,
    *,
    artifact_type: str,
    path: str,
    stage: str,
    message_type: MessageType | None = None,
    scenario_only: bool = False,
) -> GeneratedArtifact:
    return GeneratedArtifact(
        entry=VectorEntry(
            id=vector_id,
            vector_class="valid",
            artifact_type=artifact_type,
            artifact_path=path,
            length=len(wire),
            sha256=sha256(wire).hexdigest(),
            expected_outcome="accept",
            expected_error=None,
            validation_stage=stage,
            message_type=message_type.name if message_type is not None else None,
            scenario_only=scenario_only,
        ),
        wire=wire,
    )


def _route_grant() -> RouteGrant:
    return RouteGrant(
        grant_version=1,
        route_id=FIXTURES.route_id,
        name_digest=FIXTURES.name_digest,
        service_id=FIXTURES.service_id,
        source_operator_id=FIXTURES.source_operator_id,
        source_edge_id=FIXTURES.source_edge_id,
        destination_operator_id=FIXTURES.destination_operator_id,
        destination_edge_set=(FIXTURES.destination_edge_id,),
        allowed_transports=("tcp",),
        allowed_ports=(FIXTURES.port,),
        client_session_key_thumbprint=FIXTURES.client_session_key_thumbprint,
        not_before=FIXTURES.not_before,
        expires_at=FIXTURES.expires_at,
        lease_id=FIXTURES.lease_id,
        record_sequence=FIXTURES.record_sequence,
        policy_hash=FIXTURES.policy_hash,
        unique_nonce=FIXTURES.unique_nonce,
    )


def _readme() -> bytes:
    return (
        "# NBSR Core v0.2 deterministic vectors\n\n"
        "This package is test-only and must not be imported by runtime code.\n"
        "Raw `.cbor`, `.cose`, and `.bin` files are authoritative.\n"
        "Regenerate with `python scripts/generate_core_v02_vectors.py --write "
        "vectors/core-v0.2` and verify with `--check`.\n\n"
        "The manifest uses closed enums and exact SHA-256/length assertions. "
        "Valid vectors contain no Origin Endpoint or IP literal. Test seeds "
        "are public and never production keys. These vectors make no "
        "production-readiness or cross-language claim until a second "
        "independent verifier passes.\n"
    ).encode()


def _support_files() -> tuple[tuple[str, bytes], ...]:
    return (
        ("README.md", _readme()),
        (
            "keys/test-only-route-grant-ed25519-seed.hex",
            (FIXTURES.route_grant_seed.hex() + "\n").encode(),
        ),
        (
            "keys/test-only-route-grant-ed25519-public.hex",
            (FIXTURES.route_grant_public_key.hex() + "\n").encode(),
        ),
        (
            "keys/test-only-session-ed25519-seed.hex",
            (FIXTURES.session_seed.hex() + "\n").encode(),
        ),
        (
            "keys/test-only-session-ed25519-public.hex",
            (FIXTURES.session_public_key.hex() + "\n").encode(),
        ),
    )


def build_valid_package() -> GeneratedPackage:
    grant = _route_grant()
    grant_payload = encode_model(grant)
    grant_wire = encode_cose_sign1(
        grant_payload,
        FIXTURES.route_grant_seed,
        FIXTURES.kid,
    )
    grant_digest = sha256(grant_wire).digest()
    request_one = _request_id(0)
    request_two = _request_id(1)
    request_three = _request_id(2)

    client_hello_body = {
        0: 1,
        1: FIXTURES.source_operator_id,
        2: FIXTURES.source_edge_id,
        3: FIXTURES.destination_operator_id,
        4: FIXTURES.destination_edge_id,
        5: FIXTURES.client_nonce,
        6: FIXTURES.session_public_key,
        7: FIXTURES.opened_at,
    }
    edge_hello_body = {
        0: 1,
        1: FIXTURES.source_edge_id,
        2: FIXTURES.destination_edge_id,
        3: FIXTURES.client_nonce,
        4: FIXTURES.edge_nonce,
        5: FIXTURES.client_session_key_thumbprint,
        6: FIXTURES.opened_at,
    }
    proof_transcript = encode_route_open_transcript(
        protocol_version=2,
        session_id=FIXTURES.session_id,
        request_id=request_two,
        channel_id=FIXTURES.channel_id,
        route_id=FIXTURES.route_id,
        service_id=FIXTURES.service_id,
        destination_edge_id=FIXTURES.destination_edge_id,
        edge_nonce=FIXTURES.edge_nonce,
        transport="tcp",
        port=FIXTURES.port,
        route_grant_digest=grant_digest,
        opened_at=FIXTURES.opened_at,
    )
    proof_signature = sign_route_open(
        proof_transcript,
        FIXTURES.session_seed,
    )
    route_open_body = {
        0: 1,
        1: FIXTURES.channel_id,
        2: grant_wire,
        3: FIXTURES.edge_nonce,
        4: "tcp",
        5: FIXTURES.port,
        6: FIXTURES.opened_at,
        7: proof_signature,
    }
    route_accept_body = {
        0: 1,
        1: FIXTURES.channel_id,
        2: FIXTURES.route_id,
        3: grant_digest,
        4: FIXTURES.opened_at,
    }
    route_error = {
        0: 1,
        1: int(ErrorCode.NBSR_E_ROUTE_DENIED),
        2: request_two,
        3: False,
    }
    route_reject_body = {
        0: 1,
        1: FIXTURES.channel_id,
        2: FIXTURES.route_id,
        3: grant_digest,
        4: route_error,
    }
    stream_open_body = {
        0: 1,
        1: 4,
        2: FIXTURES.channel_id,
        3: FIXTURES.route_id,
        4: grant_digest,
        5: "tcp",
        6: FIXTURES.port,
    }
    stream_accept_body = {
        0: 1,
        1: 4,
        2: FIXTURES.channel_id,
        3: FIXTURES.route_id,
        4: FIXTURES.opened_at,
    }
    stream_error = {
        0: 1,
        1: int(ErrorCode.NBSR_E_ROUTE_DENIED),
        2: request_three,
        3: False,
    }
    stream_reject_body = {
        0: 1,
        1: 4,
        2: FIXTURES.channel_id,
        3: FIXTURES.route_id,
        4: stream_error,
    }

    values = (
        _entry(
            "route-grant-payload",
            grant_payload,
            artifact_type="core-object-cbor",
            path="artifacts/valid/objects/route-grant-payload.cbor",
            stage="object-schema",
        ),
        _entry(
            "route-grant-sign1",
            grant_wire,
            artifact_type="cose-sign1",
            path="artifacts/valid/objects/route-grant-sign1.cose",
            stage="cose",
        ),
        _entry(
            "client-hello-body",
            encode_deterministic(client_hello_body),
            artifact_type="core-object-cbor",
            path="artifacts/valid/envelopes/client-hello-body.cbor",
            stage="message-schema",
            message_type=MessageType.CLIENT_HELLO,
        ),
        _entry(
            "client-hello",
            _envelope(MessageType.CLIENT_HELLO, request_one, 1, client_hello_body),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/client-hello.cbor",
            stage="message-schema",
            message_type=MessageType.CLIENT_HELLO,
        ),
        _entry(
            "edge-hello-body",
            encode_deterministic(edge_hello_body),
            artifact_type="core-object-cbor",
            path="artifacts/valid/envelopes/edge-hello-body.cbor",
            stage="message-schema",
            message_type=MessageType.EDGE_HELLO,
        ),
        _entry(
            "edge-hello",
            _envelope(MessageType.EDGE_HELLO, request_one, 1, edge_hello_body),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/edge-hello.cbor",
            stage="message-schema",
            message_type=MessageType.EDGE_HELLO,
        ),
        _entry(
            "route-open-proof-transcript",
            proof_transcript,
            artifact_type="proof-transcript-cbor",
            path="artifacts/valid/proofs/route-open-transcript.cbor",
            stage="proof",
        ),
        _entry(
            "route-open-proof-signature",
            proof_signature,
            artifact_type="ed25519-signature",
            path="artifacts/valid/proofs/route-open-signature.bin",
            stage="proof",
        ),
        _entry(
            "route-open",
            _envelope(MessageType.ROUTE_OPEN, request_two, 2, route_open_body),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/route-open.cbor",
            stage="binding",
            message_type=MessageType.ROUTE_OPEN,
        ),
        _entry(
            "route-accept",
            _envelope(
                MessageType.ROUTE_ACCEPT,
                request_two,
                2,
                route_accept_body,
            ),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/route-accept.cbor",
            stage="binding",
            message_type=MessageType.ROUTE_ACCEPT,
        ),
        _entry(
            "route-reject",
            _envelope(
                MessageType.ROUTE_REJECT,
                request_two,
                2,
                route_reject_body,
            ),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/route-reject.cbor",
            stage="message-schema",
            message_type=MessageType.ROUTE_REJECT,
            scenario_only=True,
        ),
        _entry(
            "stream-open",
            _envelope(
                MessageType.STREAM_OPEN,
                request_three,
                3,
                stream_open_body,
            ),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/stream-open.cbor",
            stage="binding",
            message_type=MessageType.STREAM_OPEN,
        ),
        _entry(
            "stream-accept",
            _envelope(
                MessageType.STREAM_ACCEPT,
                request_three,
                3,
                stream_accept_body,
            ),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/stream-accept.cbor",
            stage="binding",
            message_type=MessageType.STREAM_ACCEPT,
        ),
        _entry(
            "stream-reject",
            _envelope(
                MessageType.STREAM_REJECT,
                request_three,
                3,
                stream_reject_body,
            ),
            artifact_type="control-envelope-cbor",
            path="artifacts/valid/envelopes/stream-reject.cbor",
            stage="message-schema",
            message_type=MessageType.STREAM_REJECT,
            scenario_only=True,
        ),
    )
    ordered = tuple(sorted(values, key=lambda item: item.entry.id))
    manifest = VectorManifest(
        format_version=1,
        protocol="NBSR",
        protocol_version=2,
        alpn="nbsr-quic-1",
        hash="sha256",
        vectors=tuple(item.entry for item in ordered),
        scenarios=(),
    )
    return GeneratedPackage(
        manifest=manifest,
        artifacts=ordered,
        support_files=_support_files(),
    )
