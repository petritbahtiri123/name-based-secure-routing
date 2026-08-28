use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Envelope,
    CoreV02Limits, DestinationAdmission, EdgeIdentity, EdgeRole, PeerPolicy, RouteGrantIssuer,
    STREAM_CREDIT_PROFILE_ID, SessionReject, SharedControlSession, StreamCreditPreface,
    StreamCreditRefill, StreamCreditReject, TransportError, TransportListener, TrustProfileId,
    build_client_config, build_server_config, connect, decode_control_envelope,
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
) -> (SharedControlSession, ActiveChannel) {
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
    (SharedControlSession::new(session), channel)
}

async fn prime_control_stream(
    source: &nbsr_transport::AuthenticatedConnection,
    destination: &nbsr_transport::AuthenticatedConnection,
) -> (nbsr_transport::ControlStream, nbsr_transport::ControlStream) {
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
    (source_control, destination_control)
}

async fn credited_stream_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::ApplicationStream,
    nbsr_transport::ApplicationStream,
) {
    let (listener, source, destination) = connection_pair().await;
    let _controls = prime_control_stream(&source, &destination).await;
    let (source_session, source_channel) = credited_session(&source);
    let (destination_session, destination_channel) = credited_session(&destination);
    assert_eq!(source_channel.channel_id, destination_channel.channel_id);
    let (destination_stream, source_stream) = tokio::join!(
        destination
            .accept_credited_session_stream(&destination_session, destination_channel.channel_id,),
        source.open_credited_session_stream(&source_session, source_channel.channel_id),
    );
    (
        listener,
        source,
        destination,
        source_stream.expect("source credited stream"),
        destination_stream.expect("destination credited stream"),
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn send_ack_waits_for_finish_then_reports_transport_acknowledgment() {
    let (listener, source, destination, mut sending, mut receiving) = credited_stream_pair().await;
    assert!(
        tokio::time::timeout(Duration::from_millis(25), sending.wait_for_send_ack())
            .await
            .is_err(),
        "ACK wait must not report success before the send-side FIN"
    );
    let payload = b"acknowledged demo response";
    let (sent, received) = tokio::join!(sending.send_payload(payload), receiving.receive_payload());
    sent.unwrap();
    assert_eq!(received.unwrap(), payload);
    tokio::time::timeout(Duration::from_secs(2), sending.wait_for_send_ack())
        .await
        .expect("ACK wait is bounded")
        .expect("peer acknowledged the finished send stream");
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn send_ack_wait_is_cancellation_safe() {
    let (listener, source, destination, mut sending, mut receiving) = credited_stream_pair().await;
    assert!(
        tokio::time::timeout(Duration::from_millis(25), sending.wait_for_send_ack())
            .await
            .is_err(),
        "caller timeout must cancel a still-pending ACK wait"
    );
    let (sent, received) = tokio::join!(
        sending.send_payload(b"response after cancelled wait"),
        receiving.receive_payload(),
    );
    sent.unwrap();
    assert_eq!(received.unwrap(), b"response after cancelled wait");
    sending.wait_for_send_ack().await.unwrap();
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn send_ack_fails_closed_when_peer_closes_before_acknowledgment() {
    let (listener, source, destination, sending, _receiving) = credited_stream_pair().await;
    let (closed, ack) = tokio::join!(destination.close(), sending.wait_for_send_ack());
    closed.unwrap();
    assert_eq!(ack, Err(TransportError::ApplicationStreamFailed));
    source.close().await.unwrap();
    listener.close().await.unwrap();
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
    let _controls = prime_control_stream(&source, &destination).await;
    let (source_session, channel) = credited_session(&source);
    let (destination_session, destination_channel) = credited_session(&destination);
    let channel_id = channel.channel_id;
    assert_eq!(channel_id, destination_channel.channel_id);

    let mut opening = Box::pin(source.open_credited_session_stream(&source_session, channel_id));
    assert!(
        tokio::time::timeout(Duration::from_millis(25), &mut opening)
            .await
            .is_err()
    );

    let mut accepted = destination
        .accept_credited_session_stream(&destination_session, channel_id)
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

    source_session
        .update(|session| session.release_stream(channel_id, 4))
        .unwrap();
    destination_session
        .update(|session| session.release_stream(channel_id, 4))
        .unwrap();

    let (second_destination, second_source) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, channel_id),
        source.open_credited_session_stream(&source_session, channel_id),
    );
    let second_destination = second_destination.expect("distinct destination credit");
    let second_source = second_source.expect("distinct source credit");
    assert_eq!(second_destination.id(), 8);
    assert_eq!(second_source.id(), 8);
    source_session
        .update(|session| session.release_stream(channel_id, 8))
        .unwrap();
    destination_session
        .update(|session| session.release_stream(channel_id, 8))
        .unwrap();
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn live_v1_rejects_legacy_stream_open_then_credited_retry_succeeds() {
    let (listener, source, destination) = connection_pair().await;
    let (mut source_control, mut destination_control) =
        prime_control_stream(&source, &destination).await;
    let (source_session, channel) = credited_session(&source);
    let (destination_session, destination_channel) = credited_session(&destination);
    let channel_id = channel.channel_id;
    assert_eq!(channel_id, destination_channel.channel_id);

    let stream_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let before = destination_session.inspect(|session| {
        (
            session.stream_credit_snapshot(channel_id).unwrap(),
            session.audit_events().len(),
        )
    });
    source_control.send_envelope(&stream_open).await.unwrap();
    let received = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    assert_eq!(
        destination_session.update(|session| session.authorize_stream_open(channel_id, &received)),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::FallbackForbidden
        ))
    );
    assert_eq!(
        destination_session.inspect(|session| {
            (
                session.stream_credit_snapshot(channel_id).unwrap(),
                session.audit_events().len(),
            )
        }),
        before,
        "the received legacy control frame cannot consume credit, P1F replay, live capacity, or audit"
    );

    let (mut accepted, mut opened) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, channel_id),
        source.open_credited_session_stream(&source_session, channel_id),
    );
    let accepted = accepted.as_mut().expect("credited destination retry");
    let opened = opened.as_mut().expect("credited source retry");
    assert_eq!(accepted.id(), 4);
    assert_eq!(opened.id(), 4);
    let payload = b"credited retry after rejected legacy STREAM_OPEN";
    let (at_destination, at_source) =
        tokio::join!(accepted.echo_once(), opened.send_and_receive(payload));
    assert_eq!(at_destination.unwrap(), payload);
    assert_eq!(at_source.unwrap(), payload);

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn malformed_early_bytes_reject_before_admission_and_do_not_consume_state() {
    let (listener, source, destination) = connection_pair().await;
    let (source_session, channel) = credited_session(&source);
    let (destination_session, _) = credited_session(&destination);
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
        destination.accept_credited_session_stream(&destination_session, channel_id),
        malformed_sender,
    );
    assert_eq!(
        destination_reject.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert_eq!(source_reject, Err(TransportError::ControlStreamFailed));

    let (accepted, opened) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, channel_id),
        source.open_credited_session_stream(&source_session, channel_id),
    );
    assert_eq!(accepted.unwrap().id(), 4);
    assert_eq!(opened.unwrap().id(), 4);
    destination_session
        .update(|session| {
            session.authorize_credited_stream(
                StreamCreditPreface {
                    channel_id,
                    channel_generation: 1,
                    credit_epoch: 1,
                    credit_slot: 1,
                    quic_stream_id: 8,
                },
                8,
            )
        })
        .expect("malformed stream ID and the next credit remained unused");

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wrong_channel_rejects_one_attempt_but_future_credits_remain_valid() {
    let (listener, source, destination) = connection_pair().await;
    let _controls = prime_control_stream(&source, &destination).await;
    let (source_session, channel) = credited_session(&source);
    let (destination_session, _) = credited_session(&destination);
    let channel_id = channel.channel_id;

    let (destination_reject, source_reject) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, [0xee; 16]),
        source.open_credited_session_stream(&source_session, channel_id),
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
            .inspect(|session| session.application_stream_permit(channel_id, 4))
            .is_err()
    );
    assert_eq!(
        source_session.update(|session| session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        )),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );

    let (accepted, opened) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, channel_id),
        source.open_credited_session_stream(&source_session, channel_id),
    );
    assert_eq!(accepted.unwrap().id(), 8);
    assert_eq!(opened.unwrap().id(), 8);
    destination_session
        .update(|session| {
            session.authorize_credited_stream(
                StreamCreditPreface {
                    channel_id,
                    channel_generation: 1,
                    credit_epoch: 1,
                    credit_slot: 0,
                    quic_stream_id: 12,
                },
                12,
            )
        })
        .expect("rejected destination attempt did not consume slot zero");

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn shared_session_distinct_credit_progresses_after_timed_out_admission_is_aborted() {
    let (listener, source, destination) = connection_pair().await;
    let _controls = prime_control_stream(&source, &destination).await;
    let source = Arc::new(source);
    let (source_session, channel) = credited_session(&source);
    let channel_id = channel.channel_id;
    let (destination_session, _) = credited_session(&destination);

    let stalled_source = Arc::clone(&source);
    let stalled_session = source_session.clone();
    let mut stalled = tokio::spawn(async move {
        stalled_source
            .open_credited_session_stream(&stalled_session, channel_id)
            .await
    });
    tokio::time::timeout(Duration::from_secs(1), async {
        loop {
            if source_session
                .inspect(|session| session.application_stream_permit(channel_id, 4))
                .is_ok()
            {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("first source allocation commits before its peer decision");
    assert!(
        tokio::time::timeout(Duration::from_millis(25), &mut stalled)
            .await
            .is_err()
    );

    stalled.abort();
    let cancellation = match stalled.await {
        Err(error) => error,
        Ok(_) => panic!("aborted admission unexpectedly completed"),
    };
    assert!(cancellation.is_cancelled());
    let abandoned_destination = tokio::time::timeout(
        Duration::from_secs(1),
        destination.accept_credited_session_stream(&destination_session, channel_id),
    )
    .await
    .expect("peer resolves the aborted first admission");
    if let Ok(stream) = abandoned_destination {
        destination_session
            .update(|session| session.release_stream(channel_id, stream.id()))
            .unwrap();
    }

    let (second_destination, second_source) = tokio::time::timeout(Duration::from_secs(1), async {
        tokio::join!(
            destination.accept_credited_session_stream(&destination_session, channel_id),
            source.open_credited_session_stream(&source_session, channel_id),
        )
    })
    .await
    .expect("a distinct credit progresses after the timed-out admission aborts");
    assert_eq!(second_destination.unwrap().id(), 8);
    assert_eq!(second_source.unwrap().id(), 8);
    assert!(
        source_session
            .inspect(|session| session.application_stream_permit(channel_id, 4))
            .is_err(),
        "aborting the timed-out future releases its ordinary live entry"
    );
    assert!(
        source_session
            .inspect(|session| session.application_stream_permit(channel_id, 8))
            .is_ok(),
        "the independent admitted stream remains live"
    );
    assert_eq!(
        source_session.update(|session| session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 2,
                quic_stream_id: 4,
            },
            4,
        )),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        )),
        "cancellation retains the consumed credit and P1F stream ID"
    );
    source_session
        .update(|session| session.release_stream(channel_id, 8))
        .unwrap();
    destination_session
        .update(|session| session.release_stream(channel_id, 8))
        .unwrap();

    Arc::try_unwrap(source)
        .ok()
        .expect("all source task owners dropped")
        .close()
        .await
        .unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn revocation_before_destination_commit_rejects_and_retains_source_replay() {
    let (listener, source, destination) = connection_pair().await;
    let _controls = prime_control_stream(&source, &destination).await;
    let (source_session, channel) = credited_session(&source);
    let channel_id = channel.channel_id;
    let (destination_session, _) = credited_session(&destination);

    let mut opening = Box::pin(source.open_credited_session_stream(&source_session, channel_id));
    assert!(
        tokio::time::timeout(Duration::from_millis(25), &mut opening)
            .await
            .is_err()
    );
    let revoke = route_revoke(&channel);
    destination_session
        .update(|session| destination.accept_route_revoke(session, channel_id, &revoke))
        .expect("revoke before credited decision");

    assert_eq!(
        destination
            .accept_credited_session_stream(&destination_session, channel_id)
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
            .inspect(|session| session.application_stream_permit(channel_id, 4))
            .is_err()
    );
    assert_eq!(
        source_session.update(|session| session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        )),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn ordered_live_refill_follows_exhaustion_and_synchronizes_bounded_epochs() {
    let (listener, source, destination) = connection_pair().await;
    let (mut source_control, mut destination_control) =
        prime_control_stream(&source, &destination).await;
    assert_eq!(
        source.open_control_stream().await.err(),
        Some(TransportError::ControlStreamFailed)
    );
    assert_eq!(
        destination.accept_control_stream().await.err(),
        Some(TransportError::ControlStreamFailed)
    );
    let (source_session, channel) = credited_session(&source);
    let (destination_session, destination_channel) = credited_session(&destination);
    let channel_id = channel.channel_id;
    assert_eq!(channel_id, destination_channel.channel_id);

    for ordinal in 0..64_u64 {
        let (destination_stream, source_stream) = tokio::join!(
            destination.accept_credited_session_stream(&destination_session, channel_id),
            source.open_credited_session_stream(&source_session, channel_id),
        );
        let mut destination_stream = destination_stream.expect("destination credit");
        let mut source_stream =
            source_stream.expect("source credit remains usable through slot 63");
        let payload = [ordinal as u8; 1024];
        let (echoed, response) = tokio::join!(
            destination_stream.echo_once(),
            source_stream.send_and_receive(&payload),
        );
        assert_eq!(echoed.unwrap(), payload);
        assert_eq!(response.unwrap(), payload);
        let stream_id = source_stream.id();
        source_session
            .update(|session| session.release_stream(channel_id, stream_id))
            .unwrap();
        destination_session
            .update(|session| session.release_stream(channel_id, stream_id))
            .unwrap();
    }

    let (destination_exhausted, source_exhausted) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, channel_id),
        source.open_credited_session_stream(&source_session, channel_id),
    );
    assert_eq!(
        destination_exhausted.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    assert_eq!(
        source_exhausted.err(),
        Some(TransportError::ApplicationStreamRejected)
    );
    let before = source_session
        .inspect(|session| session.stream_credit_snapshot(channel_id))
        .unwrap();
    assert_eq!(before.current_epoch, 1);
    assert_eq!(before.remaining_credits, 0);
    assert_eq!(before.pending_refill, Some(2));
    assert_eq!(before.active_epochs, 1);
    assert_eq!(before.replay_entries, 64);

    let request = StreamCreditRefill {
        channel_id,
        epoch: before.pending_refill.unwrap(),
    };
    source_control
        .send_stream_credit_refill_request(request)
        .await
        .unwrap();
    let received = destination_control
        .receive_stream_credit_refill_request()
        .await
        .unwrap();
    assert_eq!(received, request);
    destination_session
        .update(|session| session.grant_stream_credit_refill(received.channel_id, received.epoch))
        .unwrap();
    destination_control
        .send_stream_credit_refill_grant(received)
        .await
        .unwrap();
    let granted = source_control
        .receive_stream_credit_refill_grant()
        .await
        .unwrap();
    assert_eq!(granted, request);
    source_session
        .update(|session| session.confirm_stream_credit_refill(granted.channel_id, granted.epoch))
        .unwrap();

    for session in [&source_session, &destination_session] {
        let activated = session
            .inspect(|session| session.stream_credit_snapshot(channel_id))
            .unwrap();
        assert_eq!(activated.current_epoch, 2);
        assert_eq!(activated.draining_epoch, Some(1));
        assert_eq!(activated.remaining_credits, 64);
        assert_eq!(activated.pending_refill, None);
        assert_eq!(activated.active_epochs, 2);
        session
            .update(|session| session.retire_stream_credit_epoch(channel_id, 1))
            .unwrap();
        assert_eq!(
            session
                .inspect(|session| session.stream_credit_snapshot(channel_id))
                .unwrap()
                .active_epochs,
            1
        );
    }

    let (destination_stream, source_stream) = tokio::join!(
        destination.accept_credited_session_stream(&destination_session, channel_id),
        source.open_credited_session_stream(&source_session, channel_id),
    );
    assert!(destination_stream.is_ok());
    assert!(source_stream.is_ok());

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}
