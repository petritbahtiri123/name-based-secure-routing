from __future__ import annotations

from collections.abc import Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from nbsr.protocol.cbor import DEFAULT_LIMITS, decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1, verify_sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.models import (
    ControlEnvelope,
    ProtocolError,
    Revocation,
    RevocationMode,
    RevocationReason,
    RevocationTargetType,
    RouteGrant,
    RouteIntent,
    ServiceRecord,
)
from nbsr.protocol.registry import ErrorCode, MessageType
from nbsr.protocol.schemas import (
    decode_envelope,
    decode_error,
    decode_revocation,
    decode_route_grant,
    decode_route_intent,
    decode_service_record,
    encode_model,
)


PROPERTY_SETTINGS = settings(
    max_examples=300,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
KID = b"property-test-key"

_TEXT_ID = st.from_regex(r"[a-z][a-z0-9]{0,15}", fullmatch=True)
_CANONICAL_NAME = _TEXT_ID.map(lambda label: f"{label}.example")
_ID16 = st.binary(min_size=16, max_size=16)
_DIGEST32 = st.binary(min_size=32, max_size=32)
_KEY_ID = st.binary(min_size=1, max_size=64)
_SEQUENCE = st.integers(min_value=1, max_value=2**64 - 1)
_PORTS = st.lists(
    st.integers(min_value=1, max_value=65_535),
    min_size=1,
    max_size=8,
    unique=True,
).map(lambda values: tuple(sorted(values, key=encode_deterministic)))
_TEXT_IDS = st.lists(
    _TEXT_ID,
    min_size=1,
    max_size=4,
    unique=True,
).map(lambda values: tuple(sorted(values, key=encode_deterministic)))


@st.composite
def _service_records(draw: st.DrawFn) -> ServiceRecord:
    start = draw(st.integers(min_value=0, max_value=253_401_696_000))
    lifetime = draw(st.integers(min_value=1, max_value=604_800))
    return ServiceRecord(
        1,
        draw(_CANONICAL_NAME),
        draw(_SEQUENCE),
        draw(_KEY_ID),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_IDS),
        draw(_TEXT_ID),
        ("tcp",),
        draw(_PORTS),
        ("nbsr-quic-1",),
        draw(st.sampled_from(("legacy", "dual-published", "nbsr-preferred", "nbsr-secure-only"))),
        start,
        start + lifetime,
        draw(_TEXT_ID),
    )


@st.composite
def _route_intents(draw: st.DrawFn) -> RouteIntent:
    start = draw(st.integers(min_value=0, max_value=253_402_300_499))
    return RouteIntent(
        1,
        draw(_DIGEST32),
        draw(_CANONICAL_NAME),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_IDS),
        ("tcp",),
        draw(_PORTS),
        start,
        start + draw(st.integers(min_value=1, max_value=300)),
        draw(_SEQUENCE),
        draw(_DIGEST32),
        draw(_ID16),
        draw(_ID16),
    )


@st.composite
def _route_grants(draw: st.DrawFn) -> RouteGrant:
    start = draw(st.integers(min_value=0, max_value=253_402_300_199))
    return RouteGrant(
        1,
        draw(_ID16),
        draw(_DIGEST32),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_ID),
        draw(_TEXT_IDS),
        ("tcp",),
        draw(_PORTS),
        draw(_DIGEST32),
        start,
        start + draw(st.integers(min_value=1, max_value=600)),
        draw(_ID16),
        draw(_SEQUENCE),
        draw(_DIGEST32),
        draw(_ID16),
    )


@st.composite
def _revocations(draw: st.DrawFn) -> Revocation:
    target_type = draw(st.sampled_from(tuple(RevocationTargetType)))
    reason = draw(st.sampled_from(tuple(RevocationReason)))
    start = draw(st.integers(min_value=0, max_value=253_402_300_798))
    expires_at = None
    if reason is not RevocationReason.KEY_COMPROMISE:
        expires_at = draw(st.one_of(st.none(), st.integers(min_value=start + 1, max_value=253_402_300_799)))
    target_sequence = draw(st.one_of(st.none(), _SEQUENCE)) if target_type is RevocationTargetType.SERVICE_RECORD else None
    return Revocation(
        1,
        draw(_ID16),
        draw(_KEY_ID),
        draw(_SEQUENCE),
        target_type,
        draw(_DIGEST32),
        draw(st.sampled_from(tuple(RevocationMode))),
        start,
        expires_at,
        target_sequence,
        reason,
    )


@st.composite
def _protocol_errors(draw: st.DrawFn) -> ProtocolError:
    retryable = draw(st.booleans())
    retry_after = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=3_600))) if retryable else None
    return ProtocolError(
        1,
        draw(st.sampled_from(tuple(ErrorCode))),
        draw(_ID16),
        retryable,
        retry_after,
    )


_CORE_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**64), max_value=2**64 - 1),
    st.binary(max_size=32),
    _TEXT_ID,
)
_CORE_VALUE = st.recursive(
    _CORE_SCALAR,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.integers(min_value=0, max_value=32), children, max_size=4),
    ),
    max_leaves=12,
)


@st.composite
def _control_envelopes(draw: st.DrawFn) -> ControlEnvelope:
    extensions = draw(
        st.dictionaries(
            st.integers(min_value=1000, max_value=1010),
            _CORE_VALUE,
            max_size=3,
        )
    )
    return ControlEnvelope(
        1,
        draw(st.sampled_from(tuple(MessageType))),
        draw(_ID16),
        draw(_ID16),
        draw(_SEQUENCE),
        draw(st.dictionaries(st.integers(min_value=0, max_value=32), _CORE_VALUE, max_size=6)),
        extensions=extensions,
    )


_MODEL_AND_DECODER = st.one_of(
    _service_records().map(lambda model: (model, decode_service_record)),
    _route_intents().map(lambda model: (model, decode_route_intent)),
    _route_grants().map(lambda model: (model, decode_route_grant)),
    _revocations().map(lambda model: (model, decode_revocation)),
    _protocol_errors().map(lambda model: (model, decode_error)),
    _control_envelopes().map(lambda model: (model, decode_envelope)),
)


@PROPERTY_SETTINGS
@given(_MODEL_AND_DECODER)
def test_bounded_models_round_trip_deterministically(
    model_and_decoder: tuple[object, Callable[[bytes], object]],
) -> None:
    model, decoder = model_and_decoder
    wire = encode_model(model)

    decoded = decoder(wire)

    assert decoded == model
    assert encode_model(decoded) == wire


@PROPERTY_SETTINGS
@given(st.binary(max_size=DEFAULT_LIMITS.max_total_bytes))
def test_arbitrary_bytes_return_bounded_value_or_protocol_violation(wire: bytes) -> None:
    try:
        value = decode_deterministic(wire)
    except ProtocolViolation as exc:
        assert exc.code in {
            ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
            ErrorCode.NBSR_E_OVER_CAPACITY,
        }
    else:
        assert encode_deterministic(value) == wire


def _signed_models() -> tuple[tuple[object, Callable[[bytes], object], ErrorCode], ...]:
    return (
        (
            ServiceRecord(
                1,
                "api.example",
                1,
                KID,
                "service",
                "operator",
                ("edge",),
                "connector",
                ("tcp",),
                (443,),
                ("nbsr-quic-1",),
                "nbsr-secure-only",
                100,
                200,
                "revocation",
            ),
            decode_service_record,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ),
        (
            RouteGrant(
                1,
                bytes(range(16)),
                bytes(range(32)),
                "service",
                "operator",
                "source",
                "destination",
                ("edge",),
                ("tcp",),
                (443,),
                bytes(reversed(range(32))),
                100,
                200,
                bytes(reversed(range(16))),
                1,
                b"p" * 32,
                b"n" * 16,
            ),
            decode_route_grant,
            ErrorCode.NBSR_E_GRANT_INVALID,
        ),
        (
            Revocation(
                1,
                bytes(range(16)),
                KID,
                1,
                RevocationTargetType.SERVICE_RECORD,
                bytes(range(32)),
                RevocationMode.DENY_NEW_USE,
                100,
                None,
                1,
                RevocationReason.ADMINISTRATIVE,
            ),
            decode_revocation,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ),
    )


@pytest.mark.parametrize(("model", "_decoder", "failure_code"), _signed_models())
@PROPERTY_SETTINGS
@given(
    segment=st.sampled_from(("protected", "payload", "signature")),
    offset=st.integers(min_value=0, max_value=65_535),
)
def test_signed_object_byte_mutations_fail_closed(
    model: object,
    _decoder: Callable[[bytes], object],
    failure_code: ErrorCode,
    segment: str,
    offset: int,
) -> None:
    message = sign1(encode_model(model), KID, PRIVATE_KEY)
    body = decode_deterministic(message[1:])
    positions = {"protected": 0, "payload": 2, "signature": 3}
    position = positions[segment]
    mutated = bytearray(body[position])
    mutated[offset % len(mutated)] ^= 1
    body[position] = bytes(mutated)
    malformed = b"\xd2" + encode_deterministic(body)

    with pytest.raises(ProtocolViolation) as rejected:
        verify_sign1(malformed, {KID: PRIVATE_KEY.public_key()}, failure_code)

    assert rejected.value.code is failure_code
