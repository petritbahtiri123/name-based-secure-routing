use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use ed25519_dalek::{Signer, SigningKey};
use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AdmissionReject, AuthorizedServicePolicy, ChannelLimits,
    ChannelRegistry, ControlSession, CoreV02Envelope, CoreV02Limits, DestinationAdmission,
    EdgeIdentity, EdgeRole, PeerPolicy, RouteGrantClaims, RouteGrantIssuer, RouteOpenRequest,
    SessionReject, TransportListener, build_client_config, build_server_config, connect,
    decode_control_envelope,
};
use sha2::{Digest, Sha256};

mod support;

const POLICY_A: [u8; 32] = [0xa0; 32];
const POLICY_B: [u8; 32] = [0xb0; 32];
const NOW: u64 = 1_893_456_000;
const SESSION_ID: [u8; 16] = [
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f,
];
const EDGE_NONCE: [u8; 32] = [
    0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f,
    0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f,
];
const ROUTE_GRANT_SEED: [u8; 32] = [
    0x9d, 0x61, 0xb1, 0x9d, 0xef, 0xfd, 0x5a, 0x60, 0xba, 0x84, 0x4a, 0xf4, 0x92, 0xec, 0x2c, 0xc4,
    0x44, 0x49, 0xc5, 0x69, 0x7b, 0x32, 0x69, 0x19, 0x70, 0x3b, 0xac, 0x03, 0x1c, 0xae, 0x7f, 0x60,
];
const SESSION_SEED: [u8; 32] = [
    0x4c, 0xcd, 0x08, 0x9b, 0x28, 0xff, 0x96, 0xda, 0x9d, 0xb6, 0xc3, 0x46, 0xec, 0x11, 0x4e, 0x0f,
    0x5b, 0x8a, 0x31, 0x9f, 0x35, 0xab, 0xa6, 0x24, 0xda, 0x8c, 0xf6, 0xed, 0x4f, 0xb8, 0xa6, 0xfb,
];
const KID: &[u8] = b"nbsr-test-route-grant-key";

fn admission_policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([
            (
                "service-a".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: POLICY_A,
                },
            ),
            (
                "service-b".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 43,
                    policy_hash: POLICY_B,
                },
            ),
        ]),
        now: NOW,
        client_session_public_key: [0x30; 32],
        edge_nonce: [0x80; 32],
    }
}

fn runtime_policy() -> AdmissionPolicy {
    let mut policy = admission_policy();
    policy.client_session_public_key = SigningKey::from_bytes(&SESSION_SEED)
        .verifying_key()
        .to_bytes();
    policy.edge_nonce = EDGE_NONCE;
    policy
}

fn request(
    id: u8,
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
) -> RouteOpenRequest {
    RouteOpenRequest {
        channel_id: [id; 16],
        grant: RouteGrantClaims {
            route_id: [id.wrapping_add(0x40); 16],
            service_id: service_id.into(),
            source_operator_id: "source.operator".into(),
            source_edge_id: "source.edge".into(),
            destination_operator_id: "destination.operator".into(),
            destination_edge_ids: vec!["destination.edge".into()],
            allowed_ports: vec![8443],
            client_session_key_thumbprint: [0x30; 32],
            not_before: 1_893_455_940,
            expires_at: 1_893_456_300,
            record_sequence,
            policy_hash,
            unique_nonce: [id.wrapping_add(0x80); 16],
        },
        requested_transport: "tcp".into(),
        requested_port: 8443,
        opened_at: 1_893_456_000,
        route_grant_digest: [id.wrapping_add(0xc0); 32],
    }
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

async fn connection_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy");
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("listener");
    let remote = listener.local_addr().expect("address");
    let (destination, source) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy, pki.source_material()).expect("client config"),
            remote,
        )
    );
    (
        listener,
        source.expect("source connection"),
        destination.expect("destination connection"),
    )
}

#[derive(Clone)]
struct SignedRoute {
    request_id: [u8; 16],
    channel_id: [u8; 16],
    route_id: [u8; 16],
    grant_digest: [u8; 32],
    open: CoreV02Envelope,
    accept: CoreV02Envelope,
}

fn signed_route(
    id: u8,
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
    sequence: u64,
) -> SignedRoute {
    let request_id = [id.wrapping_add(0x20); 16];
    let channel_id = [id; 16];
    let route_id = [id.wrapping_add(0x40); 16];
    let unique_nonce = [id.wrapping_add(0x80); 16];
    let grant_wire = signed_grant(
        route_id,
        unique_nonce,
        service_id,
        record_sequence,
        policy_hash,
    );
    let grant_digest = Sha256::digest(&grant_wire).into();
    let proof = SigningKey::from_bytes(&SESSION_SEED).sign(&route_open_transcript(
        request_id,
        channel_id,
        route_id,
        service_id,
        grant_digest,
    ));
    let open = decode(envelope(
        3,
        request_id,
        sequence,
        route_open_body(channel_id, &grant_wire, proof.to_bytes()),
    ));
    let accept = route_accept(request_id, sequence, channel_id, route_id, grant_digest);
    SignedRoute {
        request_id,
        channel_id,
        route_id,
        grant_digest,
        open,
        accept,
    }
}

fn signed_grant(
    route_id: [u8; 16],
    unique_nonce: [u8; 16],
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
) -> Vec<u8> {
    let session_public_key = SigningKey::from_bytes(&SESSION_SEED)
        .verifying_key()
        .to_bytes();
    let thumbprint: [u8; 32] = Sha256::digest(session_public_key).into();
    let mut payload = Vec::new();
    map(&mut payload, 17);
    field_uint(&mut payload, 0, 1);
    field_bytes(&mut payload, 1, &route_id);
    field_bytes(&mut payload, 2, &[0x11; 32]);
    field_text(&mut payload, 3, service_id);
    field_text(&mut payload, 4, "source.operator");
    field_text(&mut payload, 5, "source.edge");
    field_text(&mut payload, 6, "destination.operator");
    uint(&mut payload, 7);
    array(&mut payload, 1);
    text(&mut payload, "destination.edge");
    uint(&mut payload, 8);
    array(&mut payload, 1);
    text(&mut payload, "tcp");
    uint(&mut payload, 9);
    array(&mut payload, 1);
    uint(&mut payload, 8443);
    field_bytes(&mut payload, 10, &thumbprint);
    field_uint(&mut payload, 11, NOW - 60);
    field_uint(&mut payload, 12, NOW + 300);
    field_bytes(&mut payload, 13, &[0x33; 16]);
    field_uint(&mut payload, 14, record_sequence);
    field_bytes(&mut payload, 15, &policy_hash);
    field_bytes(&mut payload, 16, &unique_nonce);

    let mut protected = Vec::new();
    map(&mut protected, 2);
    uint(&mut protected, 1);
    nint(&mut protected, -8);
    field_bytes(&mut protected, 4, KID);

    let mut signature_structure = Vec::new();
    array(&mut signature_structure, 4);
    text(&mut signature_structure, "Signature1");
    bytes(&mut signature_structure, &protected);
    bytes(&mut signature_structure, &[]);
    bytes(&mut signature_structure, &payload);
    let signature = SigningKey::from_bytes(&ROUTE_GRANT_SEED).sign(&signature_structure);

    let mut wire = vec![0xd2];
    array(&mut wire, 4);
    bytes(&mut wire, &protected);
    map(&mut wire, 0);
    bytes(&mut wire, &payload);
    bytes(&mut wire, &signature.to_bytes());
    wire
}

fn route_open_transcript(
    request_id: [u8; 16],
    channel_id: [u8; 16],
    route_id: [u8; 16],
    service_id: &str,
    grant_digest: [u8; 32],
) -> Vec<u8> {
    let mut wire = Vec::new();
    array(&mut wire, 13);
    text(&mut wire, "NBSR-ROUTE-OPEN-v2");
    uint(&mut wire, 2);
    bytes(&mut wire, &SESSION_ID);
    bytes(&mut wire, &request_id);
    bytes(&mut wire, &channel_id);
    bytes(&mut wire, &route_id);
    text(&mut wire, service_id);
    text(&mut wire, "destination.edge");
    bytes(&mut wire, &EDGE_NONCE);
    text(&mut wire, "tcp");
    uint(&mut wire, 8443);
    bytes(&mut wire, &grant_digest);
    uint(&mut wire, NOW);
    wire
}

fn route_open_body(channel_id: [u8; 16], grant_wire: &[u8], proof_signature: [u8; 64]) -> Vec<u8> {
    let mut body = Vec::new();
    map(&mut body, 8);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &channel_id);
    field_bytes(&mut body, 2, grant_wire);
    field_bytes(&mut body, 3, &EDGE_NONCE);
    field_text(&mut body, 4, "tcp");
    field_uint(&mut body, 5, 8443);
    field_uint(&mut body, 6, NOW);
    field_bytes(&mut body, 7, &proof_signature);
    body
}

fn route_accept(
    request_id: [u8; 16],
    sequence: u64,
    channel_id: [u8; 16],
    route_id: [u8; 16],
    grant_digest: [u8; 32],
) -> CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &channel_id);
    field_bytes(&mut body, 2, &route_id);
    field_bytes(&mut body, 3, &grant_digest);
    field_uint(&mut body, 4, NOW);
    decode(envelope(4, request_id, sequence, body))
}

fn envelope(message_type: u64, request_id: [u8; 16], sequence: u64, body: Vec<u8>) -> Vec<u8> {
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message_type);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &SESSION_ID);
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    wire
}

fn decode(wire: Vec<u8>) -> CoreV02Envelope {
    decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid generated envelope")
}

fn field_uint(target: &mut Vec<u8>, key: u64, value: u64) {
    uint(target, key);
    uint(target, value);
}

fn field_bytes(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint(target, key);
    bytes(target, value);
}

fn field_text(target: &mut Vec<u8>, key: u64, value: &str) {
    uint(target, key);
    text(target, value);
}

fn uint(target: &mut Vec<u8>, value: u64) {
    argument(target, 0, value);
}

fn nint(target: &mut Vec<u8>, value: i64) {
    argument(target, 1, (-1 - value) as u64);
}

fn bytes(target: &mut Vec<u8>, value: &[u8]) {
    argument(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn text(target: &mut Vec<u8>, value: &str) {
    argument(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}

fn array(target: &mut Vec<u8>, len: u64) {
    argument(target, 4, len);
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
        0x1_0000..=0xffff_ffff => {
            target.push(initial | 26);
            target.extend_from_slice(&(value as u32).to_be_bytes());
        }
        _ => {
            target.push(initial | 27);
            target.extend_from_slice(&value.to_be_bytes());
        }
    }
}

fn channel(id: u8, service_id: &str) -> ActiveChannel {
    ActiveChannel {
        channel_id: [id; 16],
        route_id: [id.wrapping_add(0x40); 16],
        service_id: service_id.into(),
        route_grant_digest: [id.wrapping_add(0x80); 32],
        transport: "tcp".into(),
        port: 8443,
    }
}

#[test]
fn registry_enforces_lab_session_and_per_service_bounds() {
    let limits = ChannelLimits::default();
    assert_eq!(limits.max_channels_per_session, 32);
    assert_eq!(limits.max_channels_per_service, 8);

    let mut per_service = ChannelRegistry::new(limits);
    for id in 1..=8 {
        per_service
            .admit_pending(channel(id, "service-a"), [id; 16])
            .expect("first eight channels for one service");
        per_service
            .confirm_active(&[id; 16])
            .expect("pending channel activates");
    }
    assert_eq!(per_service.active_for_service("service-a"), 8);
    assert_eq!(
        per_service.admit_pending(channel(9, "service-a"), [9; 16]),
        Err(AdmissionReject::OverCapacity)
    );

    let mut per_session = ChannelRegistry::new(limits);
    for id in 1..=32 {
        let service_id = format!("service-{id}");
        per_session
            .admit_pending(channel(id, &service_id), [id; 16])
            .expect("first 32 session channels");
        per_session
            .confirm_active(&[id; 16])
            .expect("pending channel activates");
    }
    assert_eq!(per_session.active_len(), 32);
    assert_eq!(
        per_session.admit_pending(channel(33, "service-33"), [33; 16]),
        Err(AdmissionReject::OverCapacity)
    );
}

#[test]
fn registry_retains_channel_and_nonce_replay_history_after_removal() {
    let mut registry = ChannelRegistry::new(ChannelLimits::default());
    registry
        .admit_pending(channel(1, "service-a"), [0xa1; 16])
        .expect("fresh channel");
    registry
        .confirm_active(&[1; 16])
        .expect("activate fresh channel");
    assert!(registry.remove(&[1; 16]).is_some());
    assert_eq!(registry.active_len(), 0);

    assert_eq!(
        registry.admit_pending(channel(1, "service-b"), [0xa2; 16]),
        Err(AdmissionReject::Replay)
    );
    assert_eq!(
        registry.admit_pending(channel(2, "service-b"), [0xa1; 16]),
        Err(AdmissionReject::Replay)
    );
}

#[test]
fn admission_keeps_independently_authorized_channels_pending_until_confirmation() {
    let mut admission = DestinationAdmission::new(admission_policy());

    let first = admission
        .admit(request(1, "service-a", 42, POLICY_A))
        .expect("authorized service A");
    let second = admission
        .admit(request(2, "service-b", 43, POLICY_B))
        .expect("independently authorized service B");
    assert_eq!(first.service_id, "service-a");
    assert_eq!(second.service_id, "service-b");
    assert_eq!(admission.active_channels(), 0);
}

#[test]
fn same_service_requires_fresh_grant_and_service_cannot_inherit_another_policy() {
    let mut admission = DestinationAdmission::new(admission_policy());
    for id in 1..=2 {
        admission
            .admit(request(id, "service-a", 42, POLICY_A))
            .expect("fresh grant and nonce for same service");
    }
    assert_eq!(admission.active_channels(), 0);

    assert_eq!(
        admission.admit(request(3, "service-b", 42, POLICY_A)),
        Err(AdmissionReject::GrantInvalid)
    );
    assert_eq!(admission.active_channels(), 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn one_hello_session_repeats_isolated_signed_route_exchanges() {
    let (listener, source, destination) = connection_pair().await;
    let issuer_key = SigningKey::from_bytes(&ROUTE_GRANT_SEED)
        .verifying_key()
        .to_bytes();
    let mut session = ControlSession::new(
        &destination,
        DestinationAdmission::new(runtime_policy()),
        vec![RouteGrantIssuer {
            kid: KID.to_vec(),
            public_key: issuer_key,
        }],
    );
    let client_hello = decode(vector("artifacts/valid/envelopes/client-hello.cbor"));
    let edge_hello = decode(vector("artifacts/valid/envelopes/edge-hello.cbor"));
    session
        .accept_client_hello(&client_hello)
        .expect("one CLIENT_HELLO");
    session
        .confirm_edge_hello(&edge_hello)
        .expect("one EDGE_HELLO");

    let service_a = signed_route(1, "service-a", 42, POLICY_A, 2);
    session
        .accept_route_open(&service_a.open)
        .expect("service A route open");
    assert_eq!(session.active_channels(), 0);
    session
        .confirm_route_accept(&service_a.accept)
        .expect("service A route accept");
    assert!(session.stream_gate(service_a.channel_id).is_ok());

    let service_b = signed_route(2, "service-b", 43, POLICY_B, 3);
    session
        .accept_route_open(&service_b.open)
        .expect("service B route open");
    assert_eq!(session.active_channels(), 1);
    assert_eq!(
        session.stream_gate(service_b.channel_id).err(),
        Some(SessionReject::UnexpectedMessage)
    );

    let wrong_accepts = [
        route_accept(
            [0xee; 16],
            3,
            service_b.channel_id,
            service_b.route_id,
            service_b.grant_digest,
        ),
        route_accept(
            service_b.request_id,
            3,
            service_a.channel_id,
            service_b.route_id,
            service_b.grant_digest,
        ),
        route_accept(
            service_b.request_id,
            3,
            service_b.channel_id,
            service_a.route_id,
            service_b.grant_digest,
        ),
        route_accept(
            service_b.request_id,
            3,
            service_b.channel_id,
            service_b.route_id,
            service_a.grant_digest,
        ),
    ];
    for wrong in &wrong_accepts {
        assert!(session.confirm_route_accept(wrong).is_err());
        assert_eq!(session.active_channels(), 1);
        assert!(session.stream_gate(service_a.channel_id).is_ok());
    }
    session
        .confirm_route_accept(&service_b.accept)
        .expect("correct service B acceptance still works");
    assert!(session.confirm_route_accept(&service_b.accept).is_err());
    assert_eq!(session.active_channels(), 2);

    let second_a = signed_route(3, "service-a", 42, POLICY_A, 4);
    session
        .accept_route_open(&second_a.open)
        .expect("fresh second service A grant");
    session
        .confirm_route_accept(&second_a.accept)
        .expect("fresh second service A acceptance");

    let policy_substitution = signed_route(4, "service-b", 42, POLICY_A, 5);
    assert_eq!(
        session.accept_route_open(&policy_substitution.open),
        Err(SessionReject::Admission(AdmissionReject::GrantInvalid))
    );
    assert_eq!(session.active_channels(), 3);
    for channel_id in [
        service_a.channel_id,
        service_b.channel_id,
        second_a.channel_id,
    ] {
        assert!(session.stream_gate(channel_id).is_ok());
    }

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}
