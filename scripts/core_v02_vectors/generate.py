from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Mapping

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.models import RouteGrant
from nbsr.protocol.registry import ErrorCode, MessageType
from nbsr.protocol.schemas import encode_model
from scripts.core_v02_vectors.crypto import (
    encode_cose_sign1,
    encode_route_open_transcript,
    sign_route_open,
)
from scripts.core_v02_vectors.fixtures import FIXTURES
from scripts.core_v02_vectors.manifest import (
    ScenarioEntry,
    ScenarioStep,
    VectorEntry,
    VectorManifest,
)
from scripts.core_v02_vectors.reference import (
    ConformanceState,
    ReferenceContext,
    UnknownCoreVersion,
    apply_envelope,
    verify_envelope,
)


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


def _invalid_entry(
    vector_id: str,
    wire: bytes,
    *,
    error: ErrorCode | None,
    stage: str,
    artifact_type: str,
    message_type: MessageType | None = None,
) -> GeneratedArtifact:
    extension = "bin" if artifact_type == "malformed-bytes" else "cbor"
    return GeneratedArtifact(
        entry=VectorEntry(
            id=vector_id,
            vector_class="invalid",
            artifact_type=artifact_type,
            artifact_path=f"artifacts/invalid/{stage}/{vector_id}.{extension}",
            length=len(wire),
            sha256=sha256(wire).hexdigest(),
            expected_outcome="close" if error is None else "reject",
            expected_error=error.name if error is not None else None,
            validation_stage=stage,
            message_type=message_type.name if message_type is not None else None,
            scenario_only=False,
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
        "independent verifier passes.\n\n"
        "**Status:** generated package pending human byte and checksum "
        "approval.\n"
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


def _decoded_map(wire: bytes) -> dict[int, object]:
    value = decode_deterministic(wire)
    if not isinstance(value, dict):
        raise AssertionError("fixture is not a map")
    return value


def _mutated_route_open(
    valid: GeneratedPackage,
    mutate: object,
) -> bytes:
    envelope = _decoded_map(valid.artifact_map()["route-open"])
    body = envelope[5]
    if not isinstance(body, dict):
        raise AssertionError("Route Open body is not a map")
    mutate(body)  # type: ignore[operator]
    return encode_deterministic(envelope)


def build_invalid_artifacts(
    valid: GeneratedPackage,
) -> tuple[GeneratedArtifact, ...]:
    malformed = (
        ("cbor-duplicate-map-key", b"\xa2\x00\x01\x00\x02"),
        ("cbor-indefinite-map", b"\xbf\xff"),
        ("cbor-nonpreferred-integer", b"\x18\x00"),
        ("cbor-wrong-map-order", b"\xa2\x01\x00\x00\x00"),
        ("cbor-float", b"\xf9\x00\x00"),
        ("cbor-unsupported-tag", b"\xc0\x00"),
        ("cbor-trailing-bytes", b"\x00\x00"),
        ("cbor-truncated", b"\xa1"),
    )
    artifacts = [
        _invalid_entry(
            vector_id,
            wire,
            error=ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            stage="structural",
            artifact_type="malformed-bytes",
        )
        for vector_id, wire in malformed
    ]
    artifacts.append(
        _invalid_entry(
            "cbor-over-total-bytes",
            b"\x00" + b"x" * 65_536,
            error=ErrorCode.NBSR_E_OVER_CAPACITY,
            stage="structural",
            artifact_type="malformed-bytes",
        )
    )

    client = _decoded_map(valid.artifact_map()["client-hello"])
    client[0] = True
    artifacts.append(
        _invalid_entry(
            "boolean-protocol-version",
            encode_deterministic(client),
            error=ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            stage="envelope-schema",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.CLIENT_HELLO,
        )
    )

    grant_wire = valid.artifact_map()["route-grant-sign1"]
    cose_parts = decode_deterministic(grant_wire[1:])
    if not isinstance(cose_parts, list):
        raise AssertionError("COSE fixture is not an array")

    artifacts.append(
        _invalid_entry(
            "cose-missing-tag",
            _mutated_route_open(
                valid,
                lambda body: body.__setitem__(2, grant_wire[1:]),
            ),
            error=ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            stage="cose",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.ROUTE_OPEN,
        )
    )
    wrong_algorithm = list(cose_parts)
    wrong_algorithm[0] = encode_deterministic({1: -7, 4: FIXTURES.kid})
    wrong_algorithm_wire = b"\xd2" + encode_deterministic(wrong_algorithm)
    artifacts.append(
        _invalid_entry(
            "cose-wrong-algorithm",
            _mutated_route_open(
                valid,
                lambda body: body.__setitem__(2, wrong_algorithm_wire),
            ),
            error=ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            stage="cose",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.ROUTE_OPEN,
        )
    )
    bad_signature = list(cose_parts)
    signature = bytearray(bad_signature[3])
    signature[32] ^= 1
    bad_signature[3] = bytes(signature)
    bad_signature_wire = b"\xd2" + encode_deterministic(bad_signature)
    artifacts.append(
        _invalid_entry(
            "cose-bad-signature",
            _mutated_route_open(
                valid,
                lambda body: body.__setitem__(2, bad_signature_wire),
            ),
            error=ErrorCode.NBSR_E_GRANT_INVALID,
            stage="cose",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.ROUTE_OPEN,
        )
    )

    expired_grant = replace(
        _route_grant(),
        not_before=FIXTURES.opened_at - 100,
        expires_at=FIXTURES.opened_at - 1,
    )
    expired_wire = encode_cose_sign1(
        encode_model(expired_grant),
        FIXTURES.route_grant_seed,
        FIXTURES.kid,
    )
    artifacts.append(
        _invalid_entry(
            "grant-expired",
            _mutated_route_open(
                valid,
                lambda body: body.__setitem__(2, expired_wire),
            ),
            error=ErrorCode.NBSR_E_GRANT_EXPIRED,
            stage="binding",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.ROUTE_OPEN,
        )
    )

    def _bad_proof(body: dict[int, object]) -> None:
        proof = bytearray(body[7])
        proof[32] ^= 1
        body[7] = bytes(proof)

    artifacts.append(
        _invalid_entry(
            "proof-bad-signature",
            _mutated_route_open(valid, _bad_proof),
            error=ErrorCode.NBSR_E_PROOF_INVALID,
            stage="proof",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.ROUTE_OPEN,
        )
    )
    artifacts.append(
        _invalid_entry(
            "route-port-not-authorized",
            _mutated_route_open(
                valid,
                lambda body: body.__setitem__(5, FIXTURES.port + 1),
            ),
            error=ErrorCode.NBSR_E_ROUTE_DENIED,
            stage="binding",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.ROUTE_OPEN,
        )
    )

    version_one = _decoded_map(valid.artifact_map()["client-hello"])
    version_one[0] = 1
    artifacts.append(
        _invalid_entry(
            "version-one-on-v2",
            encode_deterministic(version_one),
            error=ErrorCode.NBSR_E_DOWNGRADE,
            stage="version-dispatch",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.CLIENT_HELLO,
        )
    )
    version_three = _decoded_map(valid.artifact_map()["client-hello"])
    version_three[0] = 3
    artifacts.append(
        _invalid_entry(
            "version-three-generic-close",
            encode_deterministic(version_three),
            error=None,
            stage="version-dispatch",
            artifact_type="control-envelope-cbor",
            message_type=MessageType.CLIENT_HELLO,
        )
    )
    return tuple(sorted(artifacts, key=lambda item: item.entry.id))


def _scenario(
    scenario_id: str,
    steps: tuple[tuple[str, str, ErrorCode | None], ...],
    assertions: tuple[str, ...],
) -> ScenarioEntry:
    return ScenarioEntry(
        id=scenario_id,
        initial_core_version=2,
        steps=tuple(
            ScenarioStep(
                sequence=index,
                vector_id=vector_id,
                expected_outcome=outcome,
                expected_error=error.name if error is not None else None,
            )
            for index, (vector_id, outcome, error) in enumerate(steps, start=1)
        ),
        final_assertions=assertions,
    )


def _scenarios() -> tuple[ScenarioEntry, ...]:
    accepted = (
        ("client-hello", "accept", None),
        ("edge-hello", "accept", None),
        ("route-open", "accept", None),
        ("route-accept", "accept", None),
        ("stream-open", "accept", None),
        ("stream-accept", "accept", None),
    )
    return tuple(
        sorted(
            (
                _scenario(
                    "accepted-route-stream-chain",
                    accepted,
                    (
                        "transport-session-active",
                        "route-context-active",
                        "stream-active",
                        "no-origin-disclosure",
                    ),
                ),
                _scenario(
                    "generic-close-no-fallback",
                    (("version-three-generic-close", "close", None),),
                    (
                        "no-version-fallback",
                        "no-route-state",
                        "no-stream-state",
                    ),
                ),
                _scenario(
                    "no-origin-disclosure",
                    accepted[:2],
                    ("transport-session-active", "no-origin-disclosure"),
                ),
                _scenario(
                    "no-route-before-admission",
                    (
                        (
                            "route-open",
                            "reject",
                            ErrorCode.NBSR_E_ROUTE_DENIED,
                        ),
                    ),
                    ("no-route-state", "no-stream-state"),
                ),
                _scenario(
                    "no-stream-before-route-accept",
                    (
                        ("client-hello", "accept", None),
                        ("edge-hello", "accept", None),
                        (
                            "stream-open",
                            "reject",
                            ErrorCode.NBSR_E_ROUTE_DENIED,
                        ),
                    ),
                    ("transport-session-active", "no-stream-state"),
                ),
                _scenario(
                    "rejected-route-leaves-no-state",
                    (
                        ("client-hello", "accept", None),
                        ("edge-hello", "accept", None),
                        ("route-open", "accept", None),
                        ("route-reject", "accept", None),
                    ),
                    (
                        "transport-session-active",
                        "no-route-state",
                        "no-stream-state",
                    ),
                ),
                _scenario(
                    "request-replay-rejected",
                    (
                        ("client-hello", "accept", None),
                        (
                            "client-hello",
                            "reject",
                            ErrorCode.NBSR_E_REPLAY,
                        ),
                    ),
                    ("replay-state-unchanged", "no-route-state"),
                ),
                _scenario(
                    "version-mismatch-no-fallback",
                    (
                        (
                            "version-one-on-v2",
                            "reject",
                            ErrorCode.NBSR_E_DOWNGRADE,
                        ),
                    ),
                    (
                        "no-version-fallback",
                        "no-route-state",
                        "no-stream-state",
                    ),
                ),
            ),
            key=lambda item: item.id,
        )
    )


def build_package() -> GeneratedPackage:
    valid = build_valid_package()
    artifacts = tuple(
        sorted(
            (*valid.artifacts, *build_invalid_artifacts(valid)),
            key=lambda item: item.entry.id,
        )
    )
    manifest = replace(
        valid.manifest,
        vectors=tuple(item.entry for item in artifacts),
        scenarios=_scenarios(),
    )
    return GeneratedPackage(
        manifest=manifest,
        artifacts=artifacts,
        support_files=valid.support_files,
    )


def _reference_context() -> ReferenceContext:
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


def run_scenario(
    entry: ScenarioEntry,
    artifacts: Mapping[str, bytes],
) -> ConformanceState:
    state = ConformanceState()
    context = _reference_context()
    for step in entry.steps:
        if step.vector_id not in artifacts:
            raise ValueError(f"unknown scenario vector: {step.vector_id}")
        before = state
        try:
            envelope = verify_envelope(artifacts[step.vector_id], context)
            state = apply_envelope(state, envelope)
        except UnknownCoreVersion:
            if step.expected_outcome != "close" or step.expected_error is not None:
                raise AssertionError(f"unexpected close at step {step.sequence}")
            if state != before:
                raise AssertionError("close mutated conformance state")
            continue
        except ProtocolViolation as exc:
            if step.expected_outcome != "reject" or step.expected_error != exc.code.name:
                raise AssertionError(f"unexpected rejection at step {step.sequence}: {exc.code.name}") from exc
            if state != before:
                raise AssertionError("rejection mutated conformance state")
            continue
        if step.expected_outcome != "accept":
            raise AssertionError(f"step {step.sequence} was unexpectedly accepted")

    assertions = set(entry.final_assertions)
    if "transport-session-active" in assertions and not state.transport_session_active:
        raise AssertionError("transport session is not active")
    if "route-context-active" in assertions and not state.active_channel_ids:
        raise AssertionError("route context is not active")
    if "stream-active" in assertions and not state.active_stream_ids:
        raise AssertionError("stream is not active")
    if "no-route-state" in assertions and state.active_channel_ids:
        raise AssertionError("unexpected route state")
    if "no-stream-state" in assertions and state.active_stream_ids:
        raise AssertionError("unexpected stream state")
    if "no-origin-disclosure" in assertions:
        for step in entry.steps:
            if b"origin" in artifacts[step.vector_id].lower():
                raise AssertionError("origin-shaped data in scenario artifact")
    return state
