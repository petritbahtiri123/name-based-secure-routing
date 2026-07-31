use std::fs;
use std::path::PathBuf;

use nbsr_transport::{
    CoreV02Limits, CoreV02MessageType, CoreV02Reject, RouteGrantIssuer, decode_control_envelope,
    validate_route_grant_sign1,
};

fn vector(id: &str) -> Vec<u8> {
    let relative = match id {
        "client-hello" => "artifacts/valid/envelopes/client-hello.cbor",
        "edge-hello" => "artifacts/valid/envelopes/edge-hello.cbor",
        "route-open" => "artifacts/valid/envelopes/route-open.cbor",
        "route-accept" => "artifacts/valid/envelopes/route-accept.cbor",
        "stream-open" => "artifacts/valid/envelopes/stream-open.cbor",
        "stream-accept" => "artifacts/valid/envelopes/stream-accept.cbor",
        "cbor-duplicate-map-key" => "artifacts/invalid/structural/cbor-duplicate-map-key.bin",
        "cbor-float" => "artifacts/invalid/structural/cbor-float.bin",
        "cbor-indefinite-map" => "artifacts/invalid/structural/cbor-indefinite-map.bin",
        "cbor-nonpreferred-integer" => "artifacts/invalid/structural/cbor-nonpreferred-integer.bin",
        "cbor-over-total-bytes" => "artifacts/invalid/structural/cbor-over-total-bytes.bin",
        "cbor-trailing-bytes" => "artifacts/invalid/structural/cbor-trailing-bytes.bin",
        "cbor-truncated" => "artifacts/invalid/structural/cbor-truncated.bin",
        "cbor-unsupported-tag" => "artifacts/invalid/structural/cbor-unsupported-tag.bin",
        "cbor-wrong-map-order" => "artifacts/invalid/structural/cbor-wrong-map-order.bin",
        "version-one-on-v2" => "artifacts/invalid/version-dispatch/version-one-on-v2.cbor",
        "version-three-generic-close" => {
            "artifacts/invalid/version-dispatch/version-three-generic-close.cbor"
        }
        "route-grant-sign1" => "artifacts/valid/objects/route-grant-sign1.cose",
        "cose-bad-signature" => "artifacts/invalid/cose/cose-bad-signature.cbor",
        other => panic!("unknown vector id: {other}"),
    };
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("vectors/core-v0.2");
    fs::read(root.join(relative)).expect("checked-in Core v0.2 fixture")
}

fn trusted_issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    }
}

#[test]
fn valid_control_envelopes_decode_and_round_trip_byte_exactly() {
    let expected = [
        ("client-hello", CoreV02MessageType::ClientHello),
        ("edge-hello", CoreV02MessageType::EdgeHello),
        ("route-open", CoreV02MessageType::RouteOpen),
        ("route-accept", CoreV02MessageType::RouteAccept),
        ("stream-open", CoreV02MessageType::StreamOpen),
        ("stream-accept", CoreV02MessageType::StreamAccept),
    ];

    for (id, message_type) in expected {
        let bytes = vector(id);
        let envelope = decode_control_envelope(&bytes, CoreV02Limits::default())
            .unwrap_or_else(|error| panic!("{id} unexpectedly rejected: {error:?}"));
        assert_eq!(envelope.message_type(), message_type, "{id}");
        assert_eq!(envelope.encode(), bytes, "{id} changed while re-encoding");
    }
}

#[test]
fn structural_and_version_rejections_freeze_the_approved_error_mapping() {
    for id in [
        "cbor-duplicate-map-key",
        "cbor-float",
        "cbor-indefinite-map",
        "cbor-nonpreferred-integer",
        "cbor-trailing-bytes",
        "cbor-truncated",
        "cbor-unsupported-tag",
        "cbor-wrong-map-order",
    ] {
        assert_eq!(
            decode_control_envelope(&vector(id), CoreV02Limits::default()),
            Err(CoreV02Reject::ProfileUnsupported),
            "{id}",
        );
    }

    assert_eq!(
        decode_control_envelope(&vector("cbor-over-total-bytes"), CoreV02Limits::default()),
        Err(CoreV02Reject::OverCapacity),
    );
    assert_eq!(
        decode_control_envelope(&vector("version-one-on-v2"), CoreV02Limits::default()),
        Err(CoreV02Reject::Downgrade),
    );
    assert_eq!(
        decode_control_envelope(
            &vector("version-three-generic-close"),
            CoreV02Limits::default(),
        ),
        Err(CoreV02Reject::ProfileUnsupported),
    );
}

#[test]
fn route_grant_sign1_is_validated_only_in_the_supplied_trust_context() {
    let valid = validate_route_grant_sign1(&vector("route-grant-sign1"), &[trusted_issuer()])
        .expect("approved RouteGrant fixture must verify");
    assert_eq!(valid.issuer_kid, b"nbsr-test-route-grant-key");
    assert!(!valid.payload.is_empty());

    assert_eq!(
        validate_route_grant_sign1(&vector("route-grant-sign1"), &[]),
        Err(CoreV02Reject::GrantInvalid),
    );

    let mut tampered = vector("route-grant-sign1");
    let last = tampered.len() - 1;
    tampered[last] ^= 0x01;
    assert_eq!(
        validate_route_grant_sign1(&tampered, &[trusted_issuer()]),
        Err(CoreV02Reject::GrantInvalid),
    );
}
