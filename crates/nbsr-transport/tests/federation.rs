use nbsr_transport::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Envelope, CoreV02Limits,
    DestinationAdmission, LocalFederationAdmissionAttestations,
    LocalFederationAdmissionAuthorities, RouteGrantIssuer, decode_control_envelope,
};
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

#[test]
fn source_attestation_cannot_satisfy_destination_admission() {
    let mut attestations = local_attestations();
    attestations.destination = attestations.source.clone();
    let mut admission =
        DestinationAdmission::new_federated(federated_policy(), local_authorities())
            .expect("policy");
    assert!(
        admission
            .admit_federated_route_open(
                &f75_envelope(),
                &[trusted_issuer()],
                1_893_456_000,
                &attestations
            )
            .is_err()
    );
}

#[test]
fn route_open_v2_decodes_the_closed_f75_binding() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let body = fs::read(root.join("vectors/wp8-f75-route-open/route-open-body.cbor"))
        .expect("checked-in F75 body");
    let mut envelope = Vec::new();
    map(&mut envelope, 6);
    field_uint(&mut envelope, 0, 2);
    field_uint(&mut envelope, 1, 3);
    field_bytes(
        &mut envelope,
        2,
        &[
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
            0x0e, 0x10,
        ],
    );
    field_bytes(&mut envelope, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint(&mut envelope, 4, 1);
    uint(&mut envelope, 5);
    envelope.extend_from_slice(&body);

    let decoded = decode_control_envelope(&envelope, CoreV02Limits::default())
        .expect("approved ROUTE_OPEN v2");
    let binding = decoded.federation_binding().expect("federation binding");
    assert_eq!(binding.binding_version, 1);
    assert_eq!(binding.federation_extension_id, 1);
    assert_eq!(binding.federation_extension_version, 1);
    assert_eq!(binding.federation_profile_id, "nbsr-federation-dev-v1");
    assert_eq!(
        binding.route_grant_digest,
        [
            0xf6, 0x09, 0x00, 0x54, 0xa8, 0x32, 0xc5, 0x59, 0xb2, 0x8b, 0xba, 0x38, 0x6f, 0x78,
            0x61, 0x65, 0x57, 0xce, 0x13, 0xaf, 0x39, 0xe1, 0xa9, 0x5d, 0x3d, 0xff, 0x9e, 0x1f,
            0x7b, 0xa9, 0x68, 0x60
        ]
    );
    assert_eq!(
        binding.federation_context_digest,
        [
            0x58, 0x6b, 0x97, 0xa3, 0xd9, 0x53, 0x9c, 0x42, 0x0a, 0xdc, 0xf8, 0xcf, 0xbc, 0x87,
            0xfd, 0xf3, 0xc0, 0x8e, 0x25, 0x8c, 0xb5, 0x12, 0x78, 0x34, 0x36, 0x49, 0x9d, 0xfb,
            0xa3, 0x7f, 0x06, 0x99
        ]
    );
}

#[test]
fn federated_route_open_requires_matching_typed_authority_and_f75_signature() {
    let envelope = f75_envelope();
    let mut admission =
        DestinationAdmission::new_federated(federated_policy(), local_authorities())
            .expect("policy");

    let channel = admission
        .admit_federated_route_open(
            &envelope,
            &[trusted_issuer()],
            1_893_456_000,
            &local_attestations(),
        )
        .expect("F75 federated admission");

    assert_eq!(channel.service_id, "service.example");
    assert_eq!(admission.active_channels(), 0);
}

#[test]
fn federated_route_open_rejects_context_substitution_and_legacy_fallback() {
    let envelope = f75_envelope();
    let mut changed = local_attestations();
    let last = changed.destination.len() - 1;
    changed.destination[last] ^= 1;
    let mut admission =
        DestinationAdmission::new_federated(federated_policy(), local_authorities())
            .expect("policy");
    assert!(
        admission
            .admit_federated_route_open(&envelope, &[trusted_issuer()], 1_893_456_000, &changed)
            .is_err()
    );
    assert_eq!(admission.active_channels(), 0);

    assert!(
        admission
            .admit_route_open(&envelope, &[trusted_issuer()], 1_893_456_000)
            .is_err()
    );
    assert_eq!(admission.active_channels(), 0);
}

#[test]
fn non_federated_v1_cannot_enter_the_federated_gate() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let wire = fs::read(root.join("vectors/core-v0.2/artifacts/valid/envelopes/route-open.cbor"))
        .expect("Core v1 body fixture");
    let envelope =
        decode_control_envelope(&wire, CoreV02Limits::default()).expect("Core ROUTE_OPEN v1");
    let mut admission =
        DestinationAdmission::new_federated(federated_policy(), local_authorities())
            .expect("policy");
    assert!(
        admission
            .admit_federated_route_open(
                &envelope,
                &[trusted_issuer()],
                1_893_456_000,
                &local_attestations()
            )
            .is_err()
    );
    assert_eq!(admission.active_channels(), 0);
}

#[test]
fn control_session_exposes_only_an_explicit_federated_route_gate() {
    let _gate = ControlSession::accept_federated_route_open;
}

fn f75_envelope() -> CoreV02Envelope {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let body = fs::read(root.join("vectors/wp8-f75-route-open/route-open-body.cbor"))
        .expect("checked-in F75 body");
    let mut envelope = Vec::new();
    map(&mut envelope, 6);
    field_uint(&mut envelope, 0, 2);
    field_uint(&mut envelope, 1, 3);
    field_bytes(
        &mut envelope,
        2,
        &[
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
            0x0e, 0x10,
        ],
    );
    field_bytes(&mut envelope, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint(&mut envelope, 4, 1);
    uint(&mut envelope, 5);
    envelope.extend_from_slice(&body);
    decode_control_envelope(&envelope, CoreV02Limits::default()).expect("approved ROUTE_OPEN v2")
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

fn local_attestations() -> LocalFederationAdmissionAttestations {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    LocalFederationAdmissionAttestations {
        source: fs::read(root.join("vectors/wp8-local-admission/source.cose")).unwrap(),
        destination: fs::read(root.join("vectors/wp8-local-admission/destination.cose")).unwrap(),
    }
}

fn local_authorities() -> LocalFederationAdmissionAuthorities {
    LocalFederationAdmissionAuthorities::new(
        b"local-source".to_vec(),
        [
            0xf8, 0x0c, 0xcc, 0xdc, 0xe4, 0xae, 0x1c, 0x07, 0xae, 0x20, 0x8a, 0x2a, 0xdf, 0x99,
            0xa3, 0x10, 0xae, 0x42, 0x07, 0xe0, 0x30, 0x6f, 0xa0, 0x23, 0x61, 0x10, 0xb0, 0x68,
            0x27, 0xbb, 0xb8, 0xd0,
        ],
        b"local-destination".to_vec(),
        [
            0xd7, 0x59, 0x79, 0x3b, 0xbc, 0x13, 0xa2, 0x81, 0x9a, 0x82, 0x7c, 0x76, 0xad, 0xb6,
            0xfb, 0xa8, 0xa4, 0x9a, 0xee, 0x00, 0x7f, 0x49, 0xf2, 0xd0, 0x99, 0x2d, 0x99, 0xb8,
            0x25, 0xad, 0x2c, 0x48,
        ],
    )
    .unwrap()
}

fn federated_policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r"
            .into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg"
            .into(),
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

fn field_uint(target: &mut Vec<u8>, key: u64, value: u64) {
    uint(target, key);
    uint(target, value);
}

fn field_bytes(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint(target, key);
    argument(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn uint(target: &mut Vec<u8>, value: u64) {
    argument(target, 0, value);
}

fn map(target: &mut Vec<u8>, len: u64) {
    argument(target, 5, len);
}

fn argument(target: &mut Vec<u8>, major: u8, value: u64) {
    let initial = major << 5;
    match value {
        0..=23 => target.push(initial | value as u8),
        24..=0xff => target.extend_from_slice(&[initial | 24, value as u8]),
        0x100..=0xffff => {
            target.push(initial | 25);
            target.extend_from_slice(&(value as u16).to_be_bytes());
        }
        _ => panic!("test integer is unexpectedly large"),
    }
}
