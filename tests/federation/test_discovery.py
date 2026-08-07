from __future__ import annotations


import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation import (
    AuthorityClass,
    FederationAuthority,
    FederationValidationError,
    KeyLifecycle,
    KeyPurpose,
    ObjectType,
    authenticate_task5_sign1,
)
from nbsr.federation.discovery import DiscoveryCandidate, EndpointDirectory, OperatorEndpointRecord
from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.cose import sign1


OPERATOR = b"O" * 32
TRANSPORT_KEY = b"T" * 32


def endpoint(**changes: object) -> OperatorEndpointRecord:
    payload = {
        1: ObjectType.OperatorEndpointRecord.value,
        2: 1,
        3: {1: AuthorityClass.OPERATOR_ENDPOINT.value, 2: OPERATOR, 3: b"endpoint-kid", 4: OPERATOR},
        4: 1,
        5: 1,
        6: 100,
        7: 200,
        32: OPERATOR,
        33: b"control-eu-1",
        34: "control.eu.operator.example",
        35: 1,
        36: "eu",
        37: 1,
        38: 443,
        39: 10,
        40: TRANSPORT_KEY,
        41: 1,
        42: None,
    }
    payload.update({int(key): value for key, value in changes.items()})
    return OperatorEndpointRecord.from_bytes(encode_deterministic(payload))


def authenticated_endpoint(record: OperatorEndpointRecord):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    authority = FederationAuthority(
        b"endpoint-kid", private.public_key(), OPERATOR, KeyPurpose.ENDPOINT_DISCOVERY, KeyLifecycle.ACTIVE, 1, 1, 0, 300, False
    )
    return authenticate_task5_sign1(
        sign1(record.canonical_bytes(), b"endpoint-kid", private),
        authority,
        ObjectType.OperatorEndpointRecord,
        150,
        expected_key_purpose=KeyPurpose.ENDPOINT_DISCOVERY,
    )


@pytest.mark.parametrize("source", ["DNS", "HTTPS", "STATIC"])
def test_discovery_inputs_are_candidate_metadata_not_authority(source: str) -> None:
    candidate = DiscoveryCandidate(source, OPERATOR, "control.eu.operator.example", 443, TRANSPORT_KEY)
    directory = EndpointDirectory()
    assert directory.consider(candidate) == ()
    assert not candidate.authoritative
    assert directory.resolve(OPERATOR, b"control-eu-1", now=150) == ()


def test_signed_endpoint_is_exactly_bound_and_never_exposes_origin() -> None:
    record = endpoint()
    candidate = DiscoveryCandidate("DNS", OPERATOR, record.locator, 443, TRANSPORT_KEY)
    directory = EndpointDirectory()
    directory.publish(authenticated_endpoint(record), expected_operator_id=OPERATOR, expected_transport_key_digest=TRANSPORT_KEY, now=150)
    resolved = directory.consider(candidate, now=150)
    assert resolved == (record,)
    assert record.role == 1 and record.region == "eu" and record.transport_profile == 1 and record.port == 443
    assert not hasattr(record, "origin_endpoint")
    assert "origin" not in record.locator


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"authenticated": None}, "authenticated"),
        ({"expected_operator_id": b"X" * 32}, "Operator ID"),
        ({"expected_transport_key_digest": b"X" * 32}, "transport key"),
        ({"now": 201}, "validity"),
    ],
)
def test_endpoint_publication_fails_closed(kwargs: dict[str, object], message: str) -> None:
    authenticated = kwargs.pop("authenticated", authenticated_endpoint(endpoint()))
    defaults = dict(expected_operator_id=OPERATOR, expected_transport_key_digest=TRANSPORT_KEY, now=150)
    defaults.update(kwargs)
    with pytest.raises(FederationValidationError, match=message):
        EndpointDirectory().publish(authenticated, **defaults)


def test_endpoint_rotation_revocation_and_non_resurrection() -> None:
    current = endpoint()
    rotated = endpoint(**{"5": 2, "8": current.digest, "33": b"control-eu-2", "40": b"N" * 32})
    directory = EndpointDirectory()
    directory.publish(authenticated_endpoint(current), expected_operator_id=OPERATOR, expected_transport_key_digest=TRANSPORT_KEY, now=150)
    directory.publish(authenticated_endpoint(rotated), expected_operator_id=OPERATOR, expected_transport_key_digest=b"N" * 32, now=150)
    assert directory.resolve(OPERATOR, b"control-eu-2", now=150) == (rotated,)
    revoked = endpoint(
        **{
            "5": 3,
            "8": rotated.digest,
            "33": b"control-eu-2",
            "40": b"N" * 32,
            "41": 4,
            "42": {1: 10, 2: b"control-eu-2", 3: rotated.digest},
        }
    )
    directory.publish(authenticated_endpoint(revoked), expected_operator_id=OPERATOR, expected_transport_key_digest=b"N" * 32, now=150)
    assert directory.resolve(OPERATOR, b"control-eu-2", now=150) == ()
    with pytest.raises(FederationValidationError, match="terminal"):
        directory.publish(authenticated_endpoint(rotated), expected_operator_id=OPERATOR, expected_transport_key_digest=b"N" * 32, now=150)


def test_exact_match_is_anti_enumeration_and_has_no_fallbacks() -> None:
    record = endpoint()
    directory = EndpointDirectory()
    directory.publish(authenticated_endpoint(record), expected_operator_id=OPERATOR, expected_transport_key_digest=TRANSPORT_KEY, now=150)
    assert directory.resolve(OPERATOR, b"control", now=150) == ()
    assert directory.resolve(b"X" * 32, b"control-eu-1", now=150) == ()
    assert directory.resolve_origin("service.example") == ()
    assert directory.static_trust_fallback(OPERATOR) == ()


def test_endpoint_schema_rejects_invalid_role_profile_region_port_lifecycle_and_origin_locator() -> None:
    for change in ({"35": 9}, {"36": "EU"}, {"37": 9}, {"38": 0}, {"41": 9}, {"34": "origin.service.example"}):
        with pytest.raises(FederationValidationError):
            endpoint(**change)
