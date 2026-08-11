use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Envelope,
    CoreV02Limits, DestinationAdmission, EdgeIdentity, EdgeRole, PeerPolicy, RouteGrantIssuer,
    STREAM_CREDIT_PROFILE_ID, SessionReject, StreamCreditPreface, StreamCreditReject,
    TransportError, TransportListener, TrustProfileId, build_client_config, build_server_config,
    connect, decode_control_envelope,
};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

fn control_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    let policy = AdmissionPolicy {
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
    };
    let issuer = RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    };
    ControlSession::new(
        connection,
        DestinationAdmission::new(policy).expect("valid admission policy"),
        vec![issuer],
        TrustProfileId::new("test-profile").expect("trust profile"),
    )
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

fn credited_session(
    connection: &nbsr_transport::AuthenticatedConnection,
) -> (ControlSession, ActiveChannel) {
    let mut session = control_session(connection);
    let client_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let edge_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/edge-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let route_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-open.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let route_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-accept.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    session.accept_client_hello(&client_hello).unwrap();
    session.confirm_edge_hello(&edge_hello).unwrap();
    let channel = session.accept_route_open(&route_open).unwrap();
    assert_eq!(
        session
            .select_stream_credit_profile(
                channel.channel_id,
                true,
                Some(STREAM_CREDIT_PROFILE_ID),
                false,
            )
            .unwrap(),
        nbsr_transport::StreamCreditProfile::V1
    );
    session.confirm_route_accept(&route_accept).unwrap();
    connection
        .bind_channel(&mut session, channel.channel_id)
        .unwrap();
    (session, channel)
}

async fn prime_control_stream(
    source: &nbsr_transport::AuthenticatedConnection,
    destination: &nbsr_transport::AuthenticatedConnection,
) {
    let hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let mut source_control = source.open_control_stream().await.unwrap();
    source_control.send_envelope(&hello).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
}

fn route_revoke(channel: &ActiveChannel) -> CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &channel.channel_id);
    field_bytes(&mut body, 2, &channel.route_id);
    field_bytes(&mut body, 3, &channel.route_grant_digest);
    field_uint(&mut body, 4, 1_893_456_000);

    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, 13);
    field_bytes(&mut wire, 2, &[0xa1; 16]);
    field_bytes(&mut wire, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint(&mut wire, 4, 3);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default()).unwrap()
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

fn map(target: &mut Vec<u8>, value: u64) {
    argument(target, 5, value);
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

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn credited_stream_waits_for_same_stream_accept_then_echoes_without_stream_open() {
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (mut source_session, channel) = credited_session(&source);
    let (mut destination_session, destination_channel) = credited_session(&destination);
    let channel_id = channel.channel_id;
    assert_eq!(channel_id, destination_channel.channel_id);

    let mut opening =
        Box::pin(source.open_credited_session_stream(&mut source_session, channel_id));
    assert!(
        tokio::time::timeout(Duration::from_millis(25), &mut opening)
            .await
            .is_err()
    );

    let mut accepted = destination
        .accept_credited_session_stream(&mut destination_session, channel_id)
        .await
        .expect("destination admits bounded preface");
    let mut opened = opening.await.expect("source receives same-stream ACCEPT");
    assert_eq!(opened.id(), 4);
    assert_eq!(accepted.id(), 4);

    let payload = b"credited payload is unavailable before ACCEPT";
    let (at_destination, at_source) =
        tokio::join!(accepted.echo_once(), opened.send_and_receive(payload),);
    assert_eq!(at_destination.unwrap(), payload);
    assert_eq!(at_source.unwrap(), payload);

    source_session.release_stream(channel_id, 4).unwrap();
    destination_session.release_stream(channel_id, 4).unwrap();

    let (second_destination, second_source) = tokio::join!(
        destination.accept_credited_session_stream(&mut destination_session, channel_id),
        source.open_credited_session_stream(&mut source_session, channel_id),
    );
    let second_destination = second_destination.expect("distinct destination credit");
    let second_source = second_source.expect("distinct source credit");
    assert_eq!(second_destination.id(), 8);
    assert_eq!(second_source.id(), 8);
    source_session.release_stream(channel_id, 8).unwrap();
    destination_session.release_stream(channel_id, 8).unwrap();
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn malformed_early_bytes_reject_before_admission_and_do_not_consume_state() {
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (mut source_session, channel) = credited_session(&source);
    let (mut destination_session, _) = credited_session(&destination);
    let channel_id = channel.channel_id;
    let hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();

    let malformed_sender = async {
        let mut stream = source.open_control_stream().await.unwrap();
        stream.send_envelope(&hello).await.unwrap();
        stream.receive_envelope(CoreV02Limits::default()).await
    };
    let (destination_reject, source_reject) = tokio::join!(
        destination.accept_credited_session_stream(&mut destination_session, channel_id),
        malformed_sender,
    );
    assert_eq!(
        destination_reject.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert_eq!(source_reject, Err(TransportError::ControlStreamFailed));

    let (accepted, opened) = tokio::join!(
        destination.accept_credited_session_stream(&mut destination_session, channel_id),
        source.open_credited_session_stream(&mut source_session, channel_id),
    );
    assert_eq!(accepted.unwrap().id(), 8);
    assert_eq!(opened.unwrap().id(), 8);
    destination_session
        .authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        )
        .expect("malformed stream ID and the next credit remained unused");

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wrong_channel_rejects_one_attempt_but_future_credits_remain_valid() {
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (mut source_session, channel) = credited_session(&source);
    let (mut destination_session, _) = credited_session(&destination);
    let channel_id = channel.channel_id;

    let (destination_reject, source_reject) = tokio::join!(
        destination.accept_credited_session_stream(&mut destination_session, [0xee; 16]),
        source.open_credited_session_stream(&mut source_session, channel_id),
    );
    assert_eq!(
        destination_reject.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert_eq!(
        source_reject.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert!(
        source_session
            .application_stream_permit(channel_id, 4)
            .is_err()
    );
    assert_eq!(
        source_session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        ),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );

    let (accepted, opened) = tokio::join!(
        destination.accept_credited_session_stream(&mut destination_session, channel_id),
        source.open_credited_session_stream(&mut source_session, channel_id),
    );
    assert_eq!(accepted.unwrap().id(), 8);
    assert_eq!(opened.unwrap().id(), 8);
    destination_session
        .authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 0,
                quic_stream_id: 12,
            },
            12,
        )
        .expect("rejected destination attempt did not consume slot zero");

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn distinct_credits_admit_independently_and_same_slot_commits_once() {
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (mut source_one, channel) = credited_session(&source);
    let channel_id = channel.channel_id;
    let (mut source_two, _) = credited_session(&source);
    let (mut destination_session, _) = credited_session(&destination);

    let destination_attempts = async {
        let first = destination
            .accept_credited_session_stream(&mut destination_session, channel_id)
            .await;
        let second = destination
            .accept_credited_session_stream(&mut destination_session, channel_id)
            .await;
        (first, second)
    };
    let (destination_results, first_source, second_source) = tokio::join!(
        destination_attempts,
        source.open_credited_session_stream(&mut source_one, channel_id),
        source.open_credited_session_stream(&mut source_two, channel_id),
    );

    let successes = [
        destination_results.0.is_ok(),
        destination_results.1.is_ok(),
        first_source.is_ok(),
        second_source.is_ok(),
    ];
    assert_eq!(successes.iter().filter(|success| **success).count(), 2);
    assert_ne!(first_source.is_ok(), second_source.is_ok());
    assert_ne!(destination_results.0.is_ok(), destination_results.1.is_ok());

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn revocation_after_preface_rejects_and_releases_live_state_but_retains_replay() {
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (mut source_session, channel) = credited_session(&source);
    let channel_id = channel.channel_id;
    let (mut destination_session, _) = credited_session(&destination);

    let mut opening =
        Box::pin(source.open_credited_session_stream(&mut source_session, channel_id));
    assert!(
        tokio::time::timeout(Duration::from_millis(25), &mut opening)
            .await
            .is_err()
    );
    let revoke = route_revoke(&channel);
    destination
        .accept_route_revoke(&mut destination_session, channel_id, &revoke)
        .expect("revoke before credited decision");

    assert_eq!(
        destination
            .accept_credited_session_stream(&mut destination_session, channel_id)
            .await
            .err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert_eq!(
        opening.await.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert!(
        source_session
            .application_stream_permit(channel_id, 4)
            .is_err()
    );
    assert_eq!(
        source_session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        ),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}
