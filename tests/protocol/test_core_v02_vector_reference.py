from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from nbsr.protocol.cbor import encode_deterministic
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
from scripts.core_v02_vectors.reference import (
    BODY_FIELDS,
    ConformanceState,
    ReferenceContext,
    UnknownCoreVersion,
    apply_envelope,
    verify_envelope,
)


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
    )


def _envelope(
    message_type: MessageType | int,
    body: dict[int, object],
    *,
    version: int = 2,
    request_id: bytes = FIXTURES.request_id,
    session_id: bytes = FIXTURES.session_id,
    sequence: int = 1,
) -> bytes:
    return encode_deterministic(
        {
            0: version,
            1: int(message_type),
            2: request_id,
            3: session_id,
            4: sequence,
            5: body,
        }
    )


def _route_grant() -> tuple[RouteGrant, bytes]:
    grant = RouteGrant(
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
    wire = encode_cose_sign1(
        encode_model(grant),
        FIXTURES.route_grant_seed,
        FIXTURES.kid,
    )
    return grant, wire


def _valid_messages() -> list[bytes]:
    grant, grant_wire = _route_grant()
    grant_digest = sha256(grant_wire).digest()
    request_two = FIXTURES.request_id[:-1] + bytes([FIXTURES.request_id[-1] + 1])
    request_three = FIXTURES.request_id[:-1] + bytes([FIXTURES.request_id[-1] + 2])
    transcript = encode_route_open_transcript(
        protocol_version=2,
        session_id=FIXTURES.session_id,
        request_id=request_two,
        channel_id=FIXTURES.channel_id,
        route_id=grant.route_id,
        service_id=grant.service_id,
        destination_edge_id=FIXTURES.destination_edge_id,
        edge_nonce=FIXTURES.edge_nonce,
        transport="tcp",
        port=FIXTURES.port,
        route_grant_digest=grant_digest,
        opened_at=FIXTURES.opened_at,
    )
    return [
        _envelope(
            MessageType.CLIENT_HELLO,
            {
                0: 1,
                1: FIXTURES.source_operator_id,
                2: FIXTURES.source_edge_id,
                3: FIXTURES.destination_operator_id,
                4: FIXTURES.destination_edge_id,
                5: FIXTURES.client_nonce,
                6: FIXTURES.session_public_key,
                7: FIXTURES.opened_at,
            },
        ),
        _envelope(
            MessageType.EDGE_HELLO,
            {
                0: 1,
                1: FIXTURES.source_edge_id,
                2: FIXTURES.destination_edge_id,
                3: FIXTURES.client_nonce,
                4: FIXTURES.edge_nonce,
                5: FIXTURES.client_session_key_thumbprint,
                6: FIXTURES.opened_at,
            },
        ),
        _envelope(
            MessageType.ROUTE_OPEN,
            {
                0: 1,
                1: FIXTURES.channel_id,
                2: grant_wire,
                3: FIXTURES.edge_nonce,
                4: "tcp",
                5: FIXTURES.port,
                6: FIXTURES.opened_at,
                7: sign_route_open(transcript, FIXTURES.session_seed),
            },
            request_id=request_two,
            sequence=2,
        ),
        _envelope(
            MessageType.ROUTE_ACCEPT,
            {
                0: 1,
                1: FIXTURES.channel_id,
                2: FIXTURES.route_id,
                3: grant_digest,
                4: FIXTURES.opened_at,
            },
            request_id=request_two,
            sequence=2,
        ),
        _envelope(
            MessageType.STREAM_OPEN,
            {
                0: 1,
                1: 4,
                2: FIXTURES.channel_id,
                3: FIXTURES.route_id,
                4: grant_digest,
                5: "tcp",
                6: FIXTURES.port,
            },
            request_id=request_three,
            sequence=3,
        ),
        _envelope(
            MessageType.STREAM_ACCEPT,
            {
                0: 1,
                1: 4,
                2: FIXTURES.channel_id,
                3: FIXTURES.route_id,
                4: FIXTURES.opened_at,
            },
            request_id=request_three,
            sequence=3,
        ),
    ]


def _assert_code(code: ErrorCode, call: object) -> None:
    with pytest.raises(ProtocolViolation) as exc_info:
        call()  # type: ignore[operator]
    assert exc_info.value.code is code


def test_v2_requires_protocol_version_two_and_known_message_code() -> None:
    valid = _valid_messages()[0]
    assert verify_envelope(valid, _context()).protocol_version == 2

    _assert_code(
        ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
        lambda: verify_envelope(
            _envelope(9, {0: 1}),
            _context(),
        ),
    )


def test_v1_and_v2_results_are_partitioned_and_mixed_version_is_downgrade() -> None:
    _assert_code(
        ErrorCode.NBSR_E_DOWNGRADE,
        lambda: verify_envelope(
            _envelope(MessageType.CLIENT_HELLO, {0: 1}, version=1),
            _context(),
        ),
    )
    _assert_code(
        ErrorCode.NBSR_E_DOWNGRADE,
        lambda: verify_envelope(
            _valid_messages()[0],
            replace(_context(), expected_core_version=1),
        ),
    )


def test_unknown_version_requires_generic_close_without_error_envelope() -> None:
    with pytest.raises(UnknownCoreVersion):
        verify_envelope(
            _envelope(MessageType.CLIENT_HELLO, {0: 1}, version=3),
            _context(),
        )


def test_all_eight_body_mappings_are_explicit_and_exact() -> None:
    assert BODY_FIELDS == {
        MessageType.CLIENT_HELLO: {
            0: "body_version",
            1: "source_operator_id",
            2: "source_edge_id",
            3: "destination_operator_id",
            4: "destination_edge_id",
            5: "client_nonce",
            6: "client_session_public_key",
            7: "sent_at",
        },
        MessageType.EDGE_HELLO: {
            0: "body_version",
            1: "source_edge_id",
            2: "destination_edge_id",
            3: "client_nonce",
            4: "edge_nonce",
            5: "client_session_key_thumbprint",
            6: "accepted_at",
        },
        MessageType.ROUTE_OPEN: {
            0: "body_version",
            1: "channel_id",
            2: "route_grant",
            3: "edge_nonce",
            4: "requested_transport",
            5: "requested_port",
            6: "opened_at",
            7: "proof_signature",
        },
        MessageType.ROUTE_ACCEPT: {
            0: "body_version",
            1: "channel_id",
            2: "route_id",
            3: "route_grant_digest",
            4: "accepted_at",
        },
        MessageType.ROUTE_REJECT: {
            0: "body_version",
            1: "channel_id",
            2: "route_id",
            3: "route_grant_digest",
            4: "protocol_error",
        },
        MessageType.STREAM_OPEN: {
            0: "body_version",
            1: "quic_stream_id",
            2: "channel_id",
            3: "route_id",
            4: "route_grant_digest",
            5: "transport",
            6: "port",
        },
        MessageType.STREAM_ACCEPT: {
            0: "body_version",
            1: "quic_stream_id",
            2: "channel_id",
            3: "route_id",
            4: "accepted_at",
        },
        MessageType.STREAM_REJECT: {
            0: "body_version",
            1: "quic_stream_id",
            2: "channel_id",
            3: "route_id",
            4: "protocol_error",
        },
    }


@pytest.mark.parametrize("message_index", range(6))
def test_each_valid_body_is_accepted(message_index: int) -> None:
    verify_envelope(_valid_messages()[message_index], _context())


def test_unknown_missing_and_boolean_integer_fields_are_rejected() -> None:
    valid_map = {
        0: 1,
        1: FIXTURES.source_operator_id,
        2: FIXTURES.source_edge_id,
        3: FIXTURES.destination_operator_id,
        4: FIXTURES.destination_edge_id,
        5: FIXTURES.client_nonce,
        6: FIXTURES.session_public_key,
        7: FIXTURES.opened_at,
    }
    for body in (
        {**valid_map, 99: b"unknown"},
        {key: value for key, value in valid_map.items() if key != 7},
        {**valid_map, 7: True},
    ):
        _assert_code(
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            lambda body=body: verify_envelope(
                _envelope(MessageType.CLIENT_HELLO, body),
                _context(),
            ),
        )


def test_state_progresses_only_through_accepted_chain() -> None:
    state = ConformanceState()
    for wire in _valid_messages():
        state = apply_envelope(
            state,
            verify_envelope(wire, _context()),
        )

    assert state.transport_session_active
    assert FIXTURES.channel_id in state.active_channel_ids
    assert 4 in state.active_stream_ids


def test_route_stream_and_replay_fail_closed_without_mutating_state() -> None:
    messages = _valid_messages()
    initial = ConformanceState()
    _assert_code(
        ErrorCode.NBSR_E_ROUTE_DENIED,
        lambda: apply_envelope(
            initial,
            verify_envelope(messages[2], _context()),
        ),
    )
    assert initial == ConformanceState()

    state = initial
    for wire in messages[:2]:
        state = apply_envelope(state, verify_envelope(wire, _context()))
    before_replay = state
    _assert_code(
        ErrorCode.NBSR_E_REPLAY,
        lambda: apply_envelope(
            before_replay,
            verify_envelope(messages[0], _context()),
        ),
    )
    assert state == before_replay

    for wire in messages[2:4]:
        state = apply_envelope(state, verify_envelope(wire, _context()))
    _assert_code(
        ErrorCode.NBSR_E_ROUTE_DENIED,
        lambda: apply_envelope(
            ConformanceState(),
            verify_envelope(messages[4], _context()),
        ),
    )
