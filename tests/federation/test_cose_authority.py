from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.federation.cose import FederationAuthority, verify_federation_sign1
from nbsr.federation.fields import FederationValidationError, KeyAuthorizationRecord
from nbsr.federation.registry import KeyLifecycle, KeyPurpose, ObjectType
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC_KEY = PRIVATE_KEY.public_key()
KID = b"root-kid"


def _payload() -> bytes:
    package = json.loads((ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json").read_text(encoding="utf-8"))
    fixture = next(item for item in package["fixtures"] if item["name"] == "valid-root-authorized-genesis")
    return bytes.fromhex(fixture["canonical_cbor_hex"])


def _authority(**changes: object) -> FederationAuthority:
    payload = decode_deterministic(_payload())
    values = {
        "kid": KID,
        "public_key": PUBLIC_KEY,
        "operator_id": payload[32],
        "purpose": KeyPurpose.IDENTITY_ROOT,
        "lifecycle": KeyLifecycle.ACTIVE,
        "generation": 1,
        "sequence": 1,
        "not_before": 900,
        "expires_at": 2100,
        "revoked": False,
    }
    values.update(changes)
    return FederationAuthority(**values)


def test_root_authorized_tagged_sign1_binds_exact_payload_operator_and_purpose() -> None:
    payload = _payload()
    verified = verify_federation_sign1(
        sign1(payload, KID, PRIVATE_KEY),
        _authority(),
        ObjectType.KeyAuthorizationRecord,
        1000,
        expected_payload=payload,
    )
    assert isinstance(verified, KeyAuthorizationRecord)
    assert verified.canonical_bytes() == payload


@pytest.mark.parametrize(
    "authority",
    [
        _authority(kid=b"other"),
        _authority(operator_id=b"x" * 32),
        _authority(purpose=KeyPurpose.ENDPOINT_DISCOVERY),
        _authority(lifecycle=KeyLifecycle.REVOKED),
        _authority(revoked=True),
        _authority(expires_at=999),
        _authority(generation=0),
        _authority(sequence=0),
    ],
)
def test_sign1_rejects_wrong_or_ineligible_authority(authority: FederationAuthority) -> None:
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(sign1(_payload(), KID, PRIVATE_KEY), authority, ObjectType.KeyAuthorizationRecord, 1000)


def test_sign1_rejects_untagged_wrong_alg_empty_kid_and_payload_substitution() -> None:
    message = sign1(_payload(), KID, PRIVATE_KEY)
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(message[1:], _authority(), ObjectType.KeyAuthorizationRecord, 1000)

    body = decode_deterministic(message[1:])
    body[0] = encode_deterministic({1: -7, 4: KID})
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(b"\xd2" + encode_deterministic(body), _authority(), ObjectType.KeyAuthorizationRecord, 1000)

    with pytest.raises(ValueError):
        sign1(_payload(), b"", PRIVATE_KEY)

    with pytest.raises(FederationValidationError):
        verify_federation_sign1(
            message,
            _authority(),
            ObjectType.KeyAuthorizationRecord,
            1000,
            expected_payload=_payload() + b"\x00",
        )


def test_sign1_rejects_wrong_object_type_and_cross_purpose_payload() -> None:
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(sign1(_payload(), KID, PRIVATE_KEY), _authority(), ObjectType.OperatorRegistryRecord, 1000)

    payload = decode_deterministic(_payload())
    payload[35] = KeyPurpose.ENDPOINT_DISCOVERY.value
    cross_purpose = encode_deterministic(payload)
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(sign1(cross_purpose, KID, PRIVATE_KEY), _authority(), ObjectType.KeyAuthorizationRecord, 1000)


def test_sign1_binds_payload_authorizing_authority_to_exact_signer() -> None:
    payload = decode_deterministic(_payload())
    payload[37] = dict(payload[37])
    payload[37][2] = b"different-root"
    forged_authority_claim = encode_deterministic(payload)
    with pytest.raises(FederationValidationError):
        verify_federation_sign1(
            sign1(forged_authority_claim, KID, PRIVATE_KEY),
            _authority(),
            ObjectType.KeyAuthorizationRecord,
            1000,
        )
