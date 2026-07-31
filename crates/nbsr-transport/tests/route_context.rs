use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

use nbsr_transport::{
    AdmissionPolicy, AuthorizedServicePolicy, CoreV02Limits, DestinationAdmission,
    RouteGrantIssuer, decode_control_envelope,
};

fn vector(relative: &str) -> Vec<u8> {
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

fn fixture_policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "service.example".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: [
                    0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2,
                    0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2,
                    0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                ],
            },
        )]),
        now: 1_893_456_000,
        client_session_public_key: [
            0x3d, 0x40, 0x17, 0xc3, 0xe8, 0x43, 0x89, 0x5a, 0x92, 0xb7, 0x0a, 0xa7, 0x4d, 0x1b,
            0x7e, 0xbc, 0x9c, 0x98, 0x2c, 0xcf, 0x2e, 0xc4, 0x96, 0x8c, 0xc0, 0xcd, 0x55, 0xf1,
            0x2a, 0xf4, 0x66, 0x0c,
        ],
        edge_nonce: [
            0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d,
            0x8e, 0x8f, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b,
            0x9c, 0x9d, 0x9e, 0x9f,
        ],
    }
}

#[test]
fn decoded_route_open_and_trusted_signed_grant_create_the_fixture_channel() {
    let wire = vector("artifacts/valid/envelopes/route-open.cbor");
    let envelope =
        decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid RouteOpen");
    let mut admission = DestinationAdmission::new(fixture_policy());

    let accepted = admission
        .admit_route_open(&envelope, &[trusted_issuer()])
        .expect("fixture RouteOpen admission");

    assert_eq!(
        accepted.channel_id,
        [
            0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d,
            0x4e, 0x4f,
        ]
    );
    assert_eq!(
        accepted.route_id,
        (0x20..0x30).collect::<Vec<_>>().as_slice()
    );
    assert_eq!(accepted.service_id, "service.example");
    assert_eq!(admission.active_channels(), 0);
}

#[test]
fn decoded_route_open_without_trusted_grant_issuer_allocates_no_channel() {
    let wire = vector("artifacts/valid/envelopes/route-open.cbor");
    let envelope =
        decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid RouteOpen");
    let mut admission = DestinationAdmission::new(fixture_policy());

    assert!(admission.admit_route_open(&envelope, &[]).is_err());
    assert_eq!(admission.active_channels(), 0);
}
