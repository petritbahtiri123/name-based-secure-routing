#[path = "../src/connector_signature.rs"]
mod signature;
use serde_json::Value;
use signature::verify_exact;

fn fixtures() -> Vec<Value> {
    let data: Value =
        serde_json::from_str(include_str!("fixtures/connector-signature-primitives.json")).unwrap();
    data["cases"].as_array().unwrap().clone()
}
fn hex(value: &Value) -> Vec<u8> {
    value
        .as_str()
        .unwrap()
        .as_bytes()
        .chunks_exact(2)
        .map(|c| u8::from_str_radix(std::str::from_utf8(c).unwrap(), 16).unwrap())
        .collect()
}
fn check(row: &Value) -> Result<signature::CheckedSignature, &'static str> {
    verify_exact(
        &hex(&row["wire"]),
        &hex(&row["payload"]),
        &hex(&row["kid"]),
        &hex(&row["public_key"]).try_into().unwrap(),
    )
}

#[test]
fn existing_public_signatures_match_python_without_authority_claims() {
    let cases = fixtures();
    assert_eq!(cases.len(), 14);
    for row in cases {
        let verified = check(&row).unwrap_or_else(|e| panic!("{}: {e}", row["name"]));
        assert_eq!(verified.payload(), hex(&row["payload"]));
    }
}

#[test]
fn valid_wrong_purpose_signature_is_not_a_registration_authorization() {
    let row = fixtures()
        .into_iter()
        .find(|r| r["name"] == "signed-negative-wrong-key-purpose")
        .unwrap();
    // Existing authority fixture rejects this registrar-purpose signature over
    // a KAR. The cryptographic primitive must not be mistaken for that validator.
    assert_eq!(row["fixture_purpose"], 3);
    assert!(check(&row).is_ok());
}

#[test]
fn altered_signature_payload_key_and_expected_kid_reject() {
    for row in fixtures() {
        let wire = hex(&row["wire"]);
        let payload = hex(&row["payload"]);
        let kid = hex(&row["kid"]);
        let key: [u8; 32] = hex(&row["public_key"]).try_into().unwrap();
        let mut bad_wire = wire.clone();
        *bad_wire.last_mut().unwrap() ^= 1;
        assert!(verify_exact(&bad_wire, &payload, &kid, &key).is_err());
        let mut bad_payload = payload.clone();
        bad_payload[0] ^= 1;
        assert!(verify_exact(&wire, &bad_payload, &kid, &key).is_err());
        let mut bad_kid = kid.clone();
        bad_kid[0] ^= 1;
        assert!(verify_exact(&wire, &payload, &bad_kid, &key).is_err());
        let mut bad_key = key;
        bad_key[0] ^= 1;
        assert!(verify_exact(&wire, &payload, &kid, &bad_key).is_err());
    }
}

#[test]
fn truncation_trailing_bytes_wrong_tag_and_noncanonical_array_reject() {
    let row = &fixtures()[0];
    let wire = hex(&row["wire"]);
    let payload = hex(&row["payload"]);
    let kid = hex(&row["kid"]);
    let key = hex(&row["public_key"]).try_into().unwrap();
    for end in 0..wire.len() {
        assert!(verify_exact(&wire[..end], &payload, &kid, &key).is_err());
    }
    let mut trailing = wire.clone();
    trailing.push(0);
    assert!(verify_exact(&trailing, &payload, &kid, &key).is_err());
    let mut tag = wire.clone();
    tag[0] = 0xd1;
    assert!(verify_exact(&tag, &payload, &kid, &key).is_err());
    let mut array = vec![0xd2, 0x98, 4];
    array.extend(&wire[2..]);
    assert!(verify_exact(&array, &payload, &kid, &key).is_err());
}

#[test]
fn bounded_input_and_invalid_key_identity_reject() {
    let row = &fixtures()[0];
    let payload = hex(&row["payload"]);
    let key = hex(&row["public_key"]).try_into().unwrap();
    let wire = hex(&row["wire"]);
    assert!(verify_exact(&vec![0; 65537], &payload, b"kid", &key).is_err());
    assert!(verify_exact(&wire, &vec![0; 65537], b"kid", &key).is_err());
    for kid in [vec![], vec![1; 65]] {
        assert!(verify_exact(&wire, &payload, &kid, &key).is_err());
    }
}

#[test]
fn header_detachment_and_length_encoding_alternatives_reject() {
    let row = &fixtures()[0];
    let wire = hex(&row["wire"]);
    let payload = hex(&row["payload"]);
    let kid = hex(&row["kid"]);
    let key = hex(&row["public_key"]).try_into().unwrap();
    assert!((0x40..0x58).contains(&wire[2]));
    let protected_length = usize::from(wire[2] & 31);
    let unprotected_at = 3 + protected_length;
    assert_eq!(wire[unprotected_at], 0xa0);
    let payload_at = unprotected_at + 1;
    let mut candidates = Vec::new();
    let mut unprotected = wire.clone();
    unprotected.splice(unprotected_at..unprotected_at + 1, [0xa1, 1, 0]);
    candidates.push(unprotected);
    let mut detached = wire.clone();
    detached[payload_at] = 0xf6;
    candidates.push(detached);
    let mut indefinite = wire.clone();
    indefinite[2] = 0x5f;
    candidates.push(indefinite);
    let mut overlong = wire.clone();
    overlong.splice(2..3, [0x58, protected_length as u8]);
    candidates.push(overlong);
    let mut overlong_two = wire.clone();
    overlong_two.splice(2..3, [0x59, 0, protected_length as u8]);
    candidates.push(overlong_two);
    let mut wide = wire.clone();
    wide.splice(2..3, [0x5a, 0, 0, 0, protected_length as u8]);
    candidates.push(wide);
    let mut algorithm = wire.clone();
    assert_eq!(algorithm[5], 0x27);
    algorithm[5] = 0x26;
    candidates.push(algorithm);
    let mut extra_header = wire.clone();
    extra_header[3] = 0xa3;
    candidates.push(extra_header);
    for candidate in candidates {
        assert!(verify_exact(&candidate, &payload, &kid, &key).is_err());
    }
}
