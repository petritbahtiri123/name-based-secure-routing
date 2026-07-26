from __future__ import annotations

import pytest

from nbsr.protocol.registry import ErrorCode, MessageType, ProtocolVersion


def test_core_version_mapping_is_frozen() -> None:
    assert {item.name: int(item) for item in ProtocolVersion} == {
        "CORE_0_1": 1,
    }


def test_message_code_mapping_is_frozen() -> None:
    assert {item.name: int(item) for item in MessageType} == {
        "CLIENT_HELLO": 1,
        "EDGE_HELLO": 2,
        "ROUTE_OPEN": 3,
        "ROUTE_ACCEPT": 4,
        "ROUTE_REJECT": 5,
        "STREAM_OPEN": 6,
        "STREAM_ACCEPT": 7,
        "STREAM_REJECT": 8,
        "LEASE_RENEW": 9,
        "LEASE_RESULT": 10,
        "KEY_UPDATE_NOTICE": 11,
        "ROUTE_DRAIN": 12,
        "ROUTE_REVOKE": 13,
        "ROUTE_CLOSE": 14,
        "PING": 15,
        "PONG": 16,
        "ERROR": 17,
    }


def test_error_code_mapping_is_frozen() -> None:
    assert {item.name: int(item) for item in ErrorCode} == {
        "NBSR_E_NAME_INVALID": 1,
        "NBSR_E_NAME_NOT_FOUND": 2,
        "NBSR_E_RECORD_UNTRUSTED": 3,
        "NBSR_E_RECORD_STALE": 4,
        "NBSR_E_RECORD_REVOKED": 5,
        "NBSR_E_CONTEXT_REQUIRED": 6,
        "NBSR_E_HANDLE_EXHAUSTED": 7,
        "NBSR_E_ROUTE_DENIED": 8,
        "NBSR_E_GRANT_INVALID": 9,
        "NBSR_E_GRANT_EXPIRED": 10,
        "NBSR_E_PROOF_INVALID": 11,
        "NBSR_E_REPLAY": 12,
        "NBSR_E_PROFILE_UNSUPPORTED": 13,
        "NBSR_E_DOWNGRADE": 14,
        "NBSR_E_EDGE_UNAVAILABLE": 15,
        "NBSR_E_ORIGIN_UNAVAILABLE": 16,
        "NBSR_E_REVOKED": 17,
        "NBSR_E_OVER_CAPACITY": 18,
        "NBSR_E_INTERNAL": 19,
    }


@pytest.mark.parametrize(
    ("registry", "unknown"),
    (
        (ProtocolVersion, 0),
        (ProtocolVersion, 2),
        (MessageType, 0),
        (MessageType, 18),
        (ErrorCode, 0),
        (ErrorCode, 20),
    ),
)
def test_unknown_numeric_codes_are_rejected(
    registry: type[ProtocolVersion] | type[MessageType] | type[ErrorCode],
    unknown: int,
) -> None:
    with pytest.raises(ValueError):
        registry(unknown)
