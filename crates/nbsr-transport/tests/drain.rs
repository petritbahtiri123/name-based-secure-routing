use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuditIntegrity, AuthorizedServicePolicy, ChannelState,
    ControlSession, CoreV02Limits, CoreV02MessageType, CoreV02Reject, DestinationAdmission,
    DrainDeadline, DrainEnforcement, DrainReject, EdgeIdentity, EdgeRole, PeerPolicy,
    RouteCloseBody, RouteDrainBody, RouteGrantIssuer, RouteRevokeBody, SessionDrainState,
    SessionReject, TransportListener, build_client_config, build_server_config, connect,
    decode_control_envelope,
};
use sha2::{Digest, Sha256};

mod support;

const REQUEST_ID: [u8; 16] = [0x11; 16];
const SESSION_ID: [u8; 16] = [
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f,
];
const CHANNEL_ID: [u8; 16] = [0x33; 16];
const ROUTE_ID: [u8; 16] = [0x44; 16];
const GRANT_DIGEST: [u8; 32] = [0x55; 32];

#[test]
fn exact_closed_lifecycle_bodies_decode_with_literal_lengths() {
    let drain_wire = lifecycle_envelope(
        REQUEST_ID,
        12,
        9,
        (CHANNEL_ID, ROUTE_ID, GRANT_DIGEST),
        100,
        Some(30),
    );
    assert_eq!(drain_wire.len(), 124);
    let drain = decode_control_envelope(&drain_wire, CoreV02Limits::default())
        .expect("closed ROUTE_DRAIN body");
    assert_eq!(drain.message_type(), CoreV02MessageType::RouteDrain);
    assert_eq!(
        drain.route_drain_body().expect("typed drain body"),
        RouteDrainBody {
            channel_id: CHANNEL_ID,
            route_id: ROUTE_ID,
            route_grant_digest: GRANT_DIGEST,
            requested_at: 100,
            drain_seconds: 30,
        }
    );

    let revoke_wire = lifecycle_envelope(
        REQUEST_ID,
        13,
        10,
        (CHANNEL_ID, ROUTE_ID, GRANT_DIGEST),
        101,
        None,
    );
    assert_eq!(revoke_wire.len(), 121);
    let revoke = decode_control_envelope(&revoke_wire, CoreV02Limits::default())
        .expect("closed ROUTE_REVOKE body");
    assert_eq!(revoke.message_type(), CoreV02MessageType::RouteRevoke);
    assert_eq!(
        revoke.route_revoke_body().expect("typed revoke body"),
        RouteRevokeBody {
            channel_id: CHANNEL_ID,
            route_id: ROUTE_ID,
            route_grant_digest: GRANT_DIGEST,
            revoked_at: 101,
        }
    );

    let close_wire = lifecycle_envelope(
        REQUEST_ID,
        14,
        11,
        (CHANNEL_ID, ROUTE_ID, GRANT_DIGEST),
        102,
        None,
    );
    assert_eq!(close_wire.len(), 121);
    let close = decode_control_envelope(&close_wire, CoreV02Limits::default())
        .expect("closed ROUTE_CLOSE body");
    assert_eq!(close.message_type(), CoreV02MessageType::RouteClose);
    assert_eq!(
        close.route_close_body().expect("typed close body"),
        RouteCloseBody {
            channel_id: CHANNEL_ID,
            route_id: ROUTE_ID,
            route_grant_digest: GRANT_DIGEST,
            closed_at: 102,
        }
    );
}

#[test]
fn lifecycle_decoder_rejects_wire_over_thirty_seconds_and_zero_ids() {
    let too_long = lifecycle_envelope(
        REQUEST_ID,
        12,
        9,
        (CHANNEL_ID, ROUTE_ID, GRANT_DIGEST),
        100,
        Some(31),
    );
    assert_eq!(
        decode_control_envelope(&too_long, CoreV02Limits::default()),
        Err(CoreV02Reject::ProfileUnsupported)
    );

    for (channel_id, route_id) in [([0; 16], ROUTE_ID), (CHANNEL_ID, [0; 16])] {
        let wire = lifecycle_envelope(
            REQUEST_ID,
            12,
            9,
            (channel_id, route_id, GRANT_DIGEST),
            100,
            Some(1),
        );
        assert_eq!(
            decode_control_envelope(&wire, CoreV02Limits::default()),
            Err(CoreV02Reject::ProfileUnsupported)
        );
    }
}

#[test]
fn fake_clock_deadlines_cover_every_required_bound_and_saturate() {
    for (requested, expected) in [(0, 100), (1, 101), (29, 129), (30, 130)] {
        let deadline = DrainDeadline::new(100, requested).expect("bounded drain");
        assert_eq!(deadline.monotonic_seconds(), expected);
        assert_eq!(
            deadline.is_due(expected - u64::from(requested != 0)),
            requested == 0
        );
        assert!(deadline.is_due(expected));
    }
    assert_eq!(DrainDeadline::new(100, 31), Err(DrainReject::TooLong));
    assert_eq!(
        DrainDeadline::new(u64::MAX - 5, 30)
            .expect("saturating deadline")
            .monotonic_seconds(),
        u64::MAX
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn channel_drain_denies_new_work_but_allows_release_until_the_exact_deadline() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = established_session(&destination);
    let channel = vector_channel();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .expect("bind active channel");

    let stream_open = decode_vector("artifacts/valid/envelopes/stream-open.cbor");
    let stream_accept = decode_vector("artifacts/valid/envelopes/stream-accept.cbor");
    session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .expect("accepted stream before drain");
    session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .expect("confirmed stream before drain");
    let (rejected_id, rejected_result) =
        tokio::join!(destination.reject_next_application_stream(), async {
            let mut stream = source.open_application_stream().await?;
            stream.send_payload(b"reserve-control-stream-id").await?;
            stream.receive_payload().await
        },);
    assert_eq!(rejected_id.expect("reject stream zero"), 0);
    assert_eq!(
        rejected_result,
        Err(nbsr_transport::TransportError::ApplicationStreamRejected)
    );
    let (accepted, opened) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_application_stream().await?;
            stream.send_payload(b"accepted-before-drain").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let mut accepted = accepted.expect("accepted application stream before drain");
    let mut opened = opened.expect("opened application stream before drain");
    let second_open = stream_open_envelope(&channel, 8, [0x76; 16]);
    let second_accept = stream_accept_envelope(&channel, 8, [0x76; 16], 22);
    session
        .authorize_stream_open(channel.channel_id, &second_open)
        .expect("second accepted stream before drain");
    session
        .confirm_stream_accept(channel.channel_id, &second_accept)
        .expect("second confirmed stream before drain");
    let (second_accepted, second_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_application_stream().await?;
            stream.send_payload(b"deadline-reset").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let _second_accepted = second_accepted.expect("second live target stream");
    let mut second_opened = second_opened.expect("second live source stream");
    session
        .reserve_stream_bytes(channel.channel_id, 4, 17)
        .expect("pre-drain reservation");

    let drain = decode_control_envelope(
        &lifecycle_envelope(
            REQUEST_ID,
            12,
            20,
            (
                channel.channel_id,
                channel.route_id,
                channel.route_grant_digest,
            ),
            1_893_456_000,
            Some(30),
        ),
        CoreV02Limits::default(),
    )
    .expect("valid ROUTE_DRAIN");
    session
        .accept_route_drain(channel.channel_id, &drain, 500, 1_893_456_000)
        .expect("start bounded drain");
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Draining)
    );
    assert_eq!(
        session.channel_drain_deadline(channel.channel_id),
        Some(530)
    );
    assert_eq!(
        session.reserve_stream_bytes(channel.channel_id, 4, 1),
        Err(SessionReject::InvalidChannelState)
    );
    session
        .release_stream_bytes(channel.channel_id, 4, 17)
        .expect("already accepted stream may finish accounting");
    let (pre_deadline_at_destination, pre_deadline_at_source) =
        tokio::join!(accepted.echo_once(), opened.receive_payload(),);
    assert_eq!(
        pre_deadline_at_destination.expect("accepted stream finishes during drain"),
        b"accepted-before-drain"
    );
    assert_eq!(
        pre_deadline_at_source.expect("source receives pre-deadline response"),
        b"accepted-before-drain"
    );

    let fresh_stream_open = stream_open_envelope(&channel, 12, [0x77; 16]);
    assert_eq!(
        session.authorize_stream_open(channel.channel_id, &fresh_stream_open),
        Err(SessionReject::InvalidChannelState)
    );
    let (rejected_after_drain, source_after_drain) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_application_stream().await?;
            stream.send_payload(b"new-after-drain").await?;
            stream.receive_payload().await
        },
    );
    assert!(matches!(
        rejected_after_drain,
        Err(nbsr_transport::TransportError::ApplicationStreamRejected)
    ));
    assert_eq!(
        source_after_drain,
        Err(nbsr_transport::TransportError::ApplicationStreamRejected)
    );

    assert_eq!(
        destination
            .enforce_channel_drain(&mut session, channel.channel_id, 529)
            .await,
        Ok(DrainEnforcement::Pending)
    );
    assert_eq!(
        destination
            .enforce_channel_drain(&mut session, channel.channel_id, 530)
            .await,
        Ok(DrainEnforcement::Enforced {
            audit_integrity: AuditIntegrity::Recorded,
        })
    );
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Closed)
    );
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), second_opened.receive_payload()).await,
        Ok(Err(
            nbsr_transport::TransportError::ApplicationStreamRejected
        ))
    );
    assert!(session.tombstone_expires_at(channel.channel_id).is_some());
    assert_eq!(
        session.accept_route_drain(channel.channel_id, &drain, 600, 1_893_456_100),
        Err(SessionReject::Replay)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wrong_binding_does_not_consume_control_and_revoke_wins_during_drain() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = established_session(&destination);
    let channel = vector_channel();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .expect("bind active channel");

    let wrong = decode_control_envelope(
        &lifecycle_envelope(
            [0x71; 16],
            12,
            20,
            (channel.channel_id, channel.route_id, [0x99; 32]),
            1_893_456_000,
            Some(30),
        ),
        CoreV02Limits::default(),
    )
    .expect("structurally valid wrong binding");
    assert_eq!(
        session.accept_route_drain(channel.channel_id, &wrong, 100, 1_893_456_000),
        Err(SessionReject::ControlRejected)
    );
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Active)
    );

    let drain = decode_control_envelope(
        &lifecycle_envelope(
            [0x71; 16],
            12,
            20,
            (
                channel.channel_id,
                channel.route_id,
                channel.route_grant_digest,
            ),
            1_893_456_000,
            Some(30),
        ),
        CoreV02Limits::default(),
    )
    .expect("valid ROUTE_DRAIN");
    session
        .accept_route_drain(channel.channel_id, &drain, 100, 1_893_456_000)
        .expect("wrong binding did not consume request or sequence");

    let revoke = decode_control_envelope(
        &lifecycle_envelope(
            [0x72; 16],
            13,
            21,
            (
                channel.channel_id,
                channel.route_id,
                channel.route_grant_digest,
            ),
            1_893_456_001,
            None,
        ),
        CoreV02Limits::default(),
    )
    .expect("valid ROUTE_REVOKE");
    session
        .accept_route_revoke(channel.channel_id, &revoke)
        .expect("revoke takes precedence over drain");
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Revoked)
    );
    assert_eq!(
        session.accept_route_revoke(channel.channel_id, &revoke),
        Err(SessionReject::Replay)
    );
    assert_eq!(
        destination
            .enforce_channel_drain(&mut session, channel.channel_id, 130)
            .await,
        Err(SessionReject::InvalidChannelState)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn route_close_is_bound_replay_terminal_and_retains_tombstone() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = established_session(&destination);
    let channel = vector_channel();
    let close = decode_control_envelope(
        &lifecycle_envelope(
            [0x73; 16],
            14,
            20,
            (
                channel.channel_id,
                channel.route_id,
                channel.route_grant_digest,
            ),
            1_893_456_010,
            None,
        ),
        CoreV02Limits::default(),
    )
    .expect("valid ROUTE_CLOSE");
    session
        .accept_route_close(channel.channel_id, &close)
        .expect("close exact live channel");
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Closed)
    );
    assert!(session.tombstone_expires_at(channel.channel_id).is_some());
    assert_eq!(
        session.accept_route_close(channel.channel_id, &close),
        Err(SessionReject::Replay)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn local_session_drain_closes_only_its_connection_at_the_bounded_deadline() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = established_session(&destination);
    session
        .begin_session_drain(1_000, 30)
        .expect("start local session drain without a wire sentinel");
    assert_eq!(session.session_drain_state(), SessionDrainState::Draining);
    assert_eq!(session.session_drain_deadline(), Some(1_030));
    assert_eq!(
        session.authorize_stream_open(
            vector_channel().channel_id,
            &stream_open_envelope(&vector_channel(), 4, [0x78; 16]),
        ),
        Err(SessionReject::InvalidChannelState)
    );
    assert_eq!(
        destination.enforce_session_drain(&mut session, 1_029).await,
        Ok(DrainEnforcement::Pending)
    );
    assert_eq!(
        destination.enforce_session_drain(&mut session, 1_030).await,
        Ok(DrainEnforcement::Enforced {
            audit_integrity: AuditIntegrity::Recorded,
        })
    );
    assert_eq!(session.session_drain_state(), SessionDrainState::Closed);
    let closed_result = tokio::time::timeout(Duration::from_secs(1), async {
        let mut stream = source.open_application_stream().await?;
        stream
            .send_payload(b"must-not-cross-closed-session")
            .await?;
        stream.receive_payload().await
    })
    .await
    .expect("closed session resolves");
    assert!(closed_result.is_err());

    let (other_listener, other_source, other_destination) = connection_pair().await;
    let (rejected, source_result) =
        tokio::join!(other_destination.reject_next_application_stream(), async {
            let mut stream = other_source.open_application_stream().await?;
            stream.send_payload(b"unrelated-session").await?;
            stream.receive_payload().await
        },);
    assert_eq!(rejected.expect("unrelated reset remains operational"), 0);
    assert_eq!(
        source_result,
        Err(nbsr_transport::TransportError::ApplicationStreamRejected)
    );

    other_source.close().await.expect("other source close");
    other_destination
        .close()
        .await
        .expect("other destination close");
    other_listener.close().await.expect("other listener close");
    source
        .close()
        .await
        .expect("source close after peer shutdown");
    destination
        .close()
        .await
        .expect("destination close after forced shutdown");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn grant_and_session_deadlines_can_only_shorten_drain() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = ControlSession::new_with_monotonic_deadline(
        &destination,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![route_grant_issuer()],
        DrainDeadline::new(100, 10).expect("session authority deadline"),
    );
    establish(&mut session);
    let channel = vector_channel();
    let drain = decode_control_envelope(
        &lifecycle_envelope(
            [0x79; 16],
            12,
            20,
            (
                channel.channel_id,
                channel.route_id,
                channel.route_grant_digest,
            ),
            1_893_456_000,
            Some(30),
        ),
        CoreV02Limits::default(),
    )
    .expect("valid ROUTE_DRAIN");
    session
        .accept_route_drain(channel.channel_id, &drain, 100, 1_893_456_299)
        .expect("drain bounded by earlier authority");
    assert_eq!(
        session.channel_drain_deadline(channel.channel_id),
        Some(101)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn audit_exhaustion_preserves_start_state_and_deadline_enforcement_stays_safe() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = established_session(&destination);
    let channel = vector_channel();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .expect("bind active channel");
    fill_audit_to(&mut session, &channel, 1_024);

    let drain = decode_control_envelope(
        &lifecycle_envelope(
            [0x7a; 16],
            12,
            20,
            (
                channel.channel_id,
                channel.route_id,
                channel.route_grant_digest,
            ),
            1_893_456_000,
            Some(1),
        ),
        CoreV02Limits::default(),
    )
    .expect("valid ROUTE_DRAIN");
    assert_eq!(
        session.accept_route_drain(channel.channel_id, &drain, 100, 1_893_456_000),
        Err(SessionReject::AuditUnavailable)
    );
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Active)
    );
    assert_eq!(session.channel_drain_deadline(channel.channel_id), None);
    assert_eq!(
        session.begin_session_drain(100, 1),
        Err(SessionReject::AuditUnavailable)
    );
    assert_eq!(session.session_drain_state(), SessionDrainState::Active);

    session.pop_audit_event().expect("make one audit slot");
    session
        .accept_route_drain(channel.channel_id, &drain, 100, 1_893_456_000)
        .expect("failed start consumed no request or sequence");
    assert_eq!(session.audit_events().len(), 1_024);
    assert_eq!(
        destination
            .enforce_channel_drain(&mut session, channel.channel_id, 101)
            .await,
        Ok(DrainEnforcement::Enforced {
            audit_integrity: AuditIntegrity::Failed,
        })
    );
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Draining)
    );
    assert_eq!(
        session.reserve_stream_bytes(channel.channel_id, 4, 1),
        Err(SessionReject::InvalidChannelState)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

fn established_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    let mut session = ControlSession::new(
        connection,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![route_grant_issuer()],
    );
    establish(&mut session);
    session
}

fn route_grant_issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    }
}

fn establish(session: &mut ControlSession) {
    let client_hello = decode_vector("artifacts/valid/envelopes/client-hello.cbor");
    let edge_hello = decode_vector("artifacts/valid/envelopes/edge-hello.cbor");
    let route_open = decode_vector("artifacts/valid/envelopes/route-open.cbor");
    let route_accept = decode_vector("artifacts/valid/envelopes/route-accept.cbor");
    session
        .accept_client_hello(&client_hello)
        .expect("CLIENT_HELLO");
    session.confirm_edge_hello(&edge_hello).expect("EDGE_HELLO");
    session.accept_route_open(&route_open).expect("ROUTE_OPEN");
    session
        .confirm_route_accept(&route_accept)
        .expect("ROUTE_ACCEPT");
}

fn fill_audit_to(session: &mut ControlSession, channel: &ActiveChannel, wanted: usize) {
    for index in 1_u64..=64 {
        let stream_id = index * 4;
        let request_id = id(10_000 + index);
        let open = stream_open_envelope(channel, stream_id, request_id);
        let accept = stream_accept_envelope(channel, stream_id, request_id, 100 + index);
        session
            .authorize_stream_open(channel.channel_id, &open)
            .expect("first 64 logical streams");
        session
            .confirm_stream_accept(channel.channel_id, &accept)
            .expect("confirm first 64 logical streams");
    }
    let over_capacity = stream_open_envelope(channel, 260, id(20_000));
    while session.audit_events().len() < wanted {
        assert!(matches!(
            session.authorize_stream_open(channel.channel_id, &over_capacity),
            Err(SessionReject::Stream(
                nbsr_transport::StreamReject::OverCapacity
            ))
        ));
    }
}

fn id(value: u64) -> [u8; 16] {
    let mut id = [0_u8; 16];
    id[8..].copy_from_slice(&value.to_be_bytes());
    id
}

fn vector_channel() -> ActiveChannel {
    let grant = vector("artifacts/valid/objects/route-grant-sign1.cose");
    ActiveChannel {
        channel_id: (0x40..0x50).collect::<Vec<_>>().try_into().unwrap(),
        route_id: (0x20..0x30).collect::<Vec<_>>().try_into().unwrap(),
        service_id: "service.example".into(),
        route_grant_digest: Sha256::digest(grant).into(),
        transport: "tcp".into(),
        port: 8443,
    }
}

fn runtime_policy() -> AdmissionPolicy {
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

fn decode_vector(relative: &str) -> nbsr_transport::CoreV02Envelope {
    decode_control_envelope(&vector(relative), CoreV02Limits::default()).expect("valid vector")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
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
    let remote = listener.local_addr().expect("listener address");
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

fn lifecycle_envelope(
    request_id: [u8; 16],
    message_type: u64,
    sequence: u64,
    binding: ([u8; 16], [u8; 16], [u8; 32]),
    timestamp: u64,
    drain_seconds: Option<u64>,
) -> Vec<u8> {
    let (channel_id, route_id, route_grant_digest) = binding;
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message_type);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &SESSION_ID);
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    map(&mut wire, if drain_seconds.is_some() { 6 } else { 5 });
    field_uint(&mut wire, 0, 1);
    field_bytes(&mut wire, 1, &channel_id);
    field_bytes(&mut wire, 2, &route_id);
    field_bytes(&mut wire, 3, &route_grant_digest);
    field_uint(&mut wire, 4, timestamp);
    if let Some(seconds) = drain_seconds {
        field_uint(&mut wire, 5, seconds);
    }
    wire
}

fn stream_open_envelope(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, stream_id);
    field_bytes(&mut body, 2, &channel.channel_id);
    field_bytes(&mut body, 3, &channel.route_id);
    field_bytes(&mut body, 4, &channel.route_grant_digest);
    uint(&mut body, 5);
    text(&mut body, "tcp");
    field_uint(&mut body, 6, u64::from(channel.port));

    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, 6);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &SESSION_ID);
    field_uint(&mut wire, 4, 21);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid STREAM_OPEN")
}

fn stream_accept_envelope(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, stream_id);
    field_bytes(&mut body, 2, &channel.channel_id);
    field_bytes(&mut body, 3, &channel.route_id);
    field_uint(&mut body, 4, 1_893_456_000);

    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, 7);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &SESSION_ID);
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid STREAM_ACCEPT")
}

fn field_uint(target: &mut Vec<u8>, key: u64, value: u64) {
    uint(target, key);
    uint(target, value);
}

fn field_bytes(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint(target, key);
    bytes(target, value);
}

fn uint(target: &mut Vec<u8>, value: u64) {
    argument(target, 0, value);
}

fn bytes(target: &mut Vec<u8>, value: &[u8]) {
    argument(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn text(target: &mut Vec<u8>, value: &str) {
    argument(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}

fn map(target: &mut Vec<u8>, length: u64) {
    argument(target, 5, length);
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
