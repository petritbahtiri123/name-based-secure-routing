use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use ed25519_dalek::{Signer, SigningKey};
use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuditIntegrity, AuthorizedServicePolicy, ChannelState,
    ControlSession, CoreV02Envelope, CoreV02Limits, CoreV02MessageType, CoreV02Reject,
    DestinationAdmission, DrainDeadline, DrainEnforcement, DrainReject, EdgeIdentity, EdgeRole,
    PeerPolicy, RouteCloseBody, RouteDrainBody, RouteGrantIssuer, RouteRevokeBody,
    SessionDrainEnforcement, SessionDrainState, SessionReject, TransportListener, TrustProfileId,
    build_client_config, build_server_config, connect, decode_control_envelope,
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
const NOW: u64 = 1_893_456_000;
const POLICY_HASH: [u8; 32] = [
    0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2, 0xa4, 0x60, 0xf5,
    0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2, 0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
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
    let mut source_session = established_session(&source);
    let mut session = established_session(&destination);
    let channel = vector_channel();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .expect("bind active channel");
    source
        .bind_channel(&mut source_session, channel.channel_id)
        .expect("bind source channel");

    let stream_open = decode_vector("artifacts/valid/envelopes/stream-open.cbor");
    let stream_accept = decode_vector("artifacts/valid/envelopes/stream-accept.cbor");
    session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .expect("accepted stream before drain");
    session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .expect("confirmed stream before drain");
    source_session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .expect("source accepted stream before drain");
    source_session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .expect("source confirmed stream before drain");
    let permit4 = source_session
        .application_stream_permit(channel.channel_id, 4)
        .expect("source stream permit");
    let (rejected_id, rejected_result) =
        tokio::join!(destination.reject_next_application_stream(), async {
            let mut stream = source.open_control_stream().await?;
            stream.send_envelope(&stream_open).await?;
            stream.receive_envelope(CoreV02Limits::default()).await
        },);
    assert_eq!(rejected_id.expect("reject stream zero"), 0);
    assert_eq!(
        rejected_result,
        Err(nbsr_transport::TransportError::ControlStreamFailed)
    );
    let (accepted, opened) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit4).await?;
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
    source_session
        .authorize_stream_open(channel.channel_id, &second_open)
        .expect("source second stream open");
    source_session
        .confirm_stream_accept(channel.channel_id, &second_accept)
        .expect("source second stream accept");
    let permit8 = source_session
        .application_stream_permit(channel.channel_id, 8)
        .expect("source second stream permit");
    let (second_accepted, second_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit8).await?;
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
            23,
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

    let fresh_stream_open = stream_open_envelope_with_sequence(&channel, 12, [0xdd; 16], 100);
    let fresh_stream_accept = stream_accept_envelope(&channel, 12, [0xdd; 16], 101);
    source_session
        .authorize_stream_open(channel.channel_id, &fresh_stream_open)
        .expect("source third stream open");
    source_session
        .confirm_stream_accept(channel.channel_id, &fresh_stream_accept)
        .expect("source third stream accept");
    let permit12 = source_session
        .application_stream_permit(channel.channel_id, 12)
        .expect("source third stream permit");
    assert_eq!(
        session.authorize_stream_open(channel.channel_id, &fresh_stream_open),
        Err(SessionReject::InvalidChannelState)
    );
    let (rejected_after_drain, source_after_drain) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit12).await?;
            stream.send_and_receive(b"rejected-after-drain").await
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
    destination
        .accept_route_revoke(&mut session, channel.channel_id, &revoke)
        .expect("revoke takes precedence over drain");
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Revoked)
    );
    assert_eq!(
        destination.accept_route_revoke(&mut session, channel.channel_id, &revoke),
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
    destination
        .accept_route_close(&mut session, channel.channel_id, &close)
        .expect("close exact live channel");
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Closed)
    );
    assert!(session.tombstone_expires_at(channel.channel_id).is_some());
    assert_eq!(
        destination.accept_route_close(&mut session, channel.channel_id, &close),
        Err(SessionReject::Replay)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn adapter_revoke_and_close_reset_only_after_valid_audited_commit() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_session = established_session(&source);
    let mut session = established_session(&destination);
    let revoke_route = signed_route(0x61, 10);
    let close_route = signed_route(0x62, 11);
    let sibling_route = signed_route(0x63, 12);
    for route in [&revoke_route, &close_route, &sibling_route] {
        session
            .accept_route_open(&route.open)
            .expect("fresh signed route");
        session
            .confirm_route_accept(&route.accept)
            .expect("activate signed route");
        destination
            .bind_channel(&mut session, route.channel.channel_id)
            .expect("bind signed route");
        source_session
            .accept_route_open(&route.open)
            .expect("source fresh signed route");
        source_session
            .confirm_route_accept(&route.accept)
            .expect("source activate signed route");
        source
            .bind_channel(&mut source_session, route.channel.channel_id)
            .expect("bind source signed route");
    }

    for (route, stream_id, request_id, sequence) in [
        (&revoke_route, 4, [0xd1; 16], 20),
        (&revoke_route, 8, [0xd2; 16], 21),
        (&sibling_route, 12, [0xd3; 16], 22),
        (&close_route, 16, [0xd4; 16], 23),
        (&close_route, 20, [0xd5; 16], 24),
    ] {
        let open =
            stream_open_envelope_with_sequence(&route.channel, stream_id, request_id, sequence);
        let accept = stream_accept_envelope(&route.channel, stream_id, request_id, sequence + 20);
        session
            .authorize_stream_open(route.channel.channel_id, &open)
            .expect("authorize real stream");
        session
            .confirm_stream_accept(route.channel.channel_id, &accept)
            .expect("confirm real stream");
        source_session
            .authorize_stream_open(route.channel.channel_id, &open)
            .expect("source authorize real stream");
        source_session
            .confirm_stream_accept(route.channel.channel_id, &accept)
            .expect("source confirm real stream");
    }
    let permit4 = source_session
        .application_stream_permit(revoke_route.channel.channel_id, 4)
        .unwrap();
    let permit8 = source_session
        .application_stream_permit(revoke_route.channel.channel_id, 8)
        .unwrap();
    let permit12 = source_session
        .application_stream_permit(sibling_route.channel.channel_id, 12)
        .unwrap();
    let permit16 = source_session
        .application_stream_permit(close_route.channel.channel_id, 16)
        .unwrap();
    let permit20 = source_session
        .application_stream_permit(close_route.channel.channel_id, 20)
        .unwrap();
    let (reserved, reserved_source) =
        tokio::join!(destination.reject_next_application_stream(), async {
            let mut stream = source.open_control_stream().await?;
            stream.send_envelope(&revoke_route.open).await?;
            stream.receive_envelope(CoreV02Limits::default()).await
        });
    assert_eq!(reserved.expect("reject stream zero"), 0);
    assert_eq!(
        reserved_source,
        Err(nbsr_transport::TransportError::ControlStreamFailed)
    );
    let (revoke_accepted, revoke_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, revoke_route.channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit4).await?;
            stream.send_payload(b"revoke-no-reset").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let mut revoke_accepted = revoke_accepted.expect("tracked revoke target");
    let mut revoke_opened = revoke_opened.expect("opened revoke target");
    let (revoke_reset_accepted, revoke_reset_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, revoke_route.channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit8).await?;
            stream.send_payload(b"revoke-committed").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let _revoke_reset_accepted = revoke_reset_accepted.expect("second tracked revoke target");
    let mut revoke_reset_opened = revoke_reset_opened.expect("second opened revoke target");

    let invalid_revoke = lifecycle_control(&revoke_route, 13, [0x91; 16], 4_000, [0x99; 32]);
    let valid_revoke = lifecycle_control(
        &revoke_route,
        13,
        [0x91; 16],
        7_000,
        revoke_route.channel.route_grant_digest,
    );
    let invalid_close = lifecycle_control(&close_route, 14, [0x92; 16], 9_000, [0x99; 32]);
    let valid_close = lifecycle_control(
        &close_route,
        14,
        [0x92; 16],
        12_000,
        close_route.channel.route_grant_digest,
    );
    let (other_listener, other_source, other_destination) = connection_pair().await;
    assert_eq!(
        other_destination.accept_route_revoke(
            &mut session,
            revoke_route.channel.channel_id,
            &valid_revoke,
        ),
        Err(SessionReject::ConnectionMismatch)
    );
    other_source.close().await.expect("other source close");
    other_destination
        .close()
        .await
        .expect("other destination close");
    other_listener.close().await.expect("other listener close");
    assert_eq!(
        destination.accept_route_revoke(
            &mut session,
            revoke_route.channel.channel_id,
            &invalid_revoke,
        ),
        Err(SessionReject::ControlRejected)
    );
    fill_channel_audit_partition(&mut session, &revoke_route.channel, 5_000);
    assert_eq!(
        destination.accept_route_revoke(
            &mut session,
            revoke_route.channel.channel_id,
            &valid_revoke,
        ),
        Err(SessionReject::AuditUnavailable)
    );
    let (revoke_echo, revoke_reply) =
        tokio::join!(revoke_accepted.echo_once(), revoke_opened.receive_payload());
    assert_eq!(
        revoke_echo.expect("invalid and audit-failed revoke did not reset"),
        b"revoke-no-reset"
    );
    assert_eq!(
        revoke_reply.expect("non-reset revoke response"),
        b"revoke-no-reset"
    );

    pop_until_channel_slot(&mut session, revoke_route.channel.channel_id);
    let (sibling_accepted, sibling_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, sibling_route.channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit12).await?;
            stream.send_payload(b"sibling-survives").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let mut sibling_accepted = sibling_accepted.expect("tracked sibling");
    let mut sibling_opened = sibling_opened.expect("opened sibling");
    pop_until_channel_slot(&mut session, revoke_route.channel.channel_id);
    destination
        .accept_route_revoke(&mut session, revoke_route.channel.channel_id, &valid_revoke)
        .expect("valid audited revoke");
    assert_eq!(
        tokio::time::timeout(
            Duration::from_secs(1),
            revoke_reset_opened.receive_payload()
        )
        .await,
        Ok(Err(
            nbsr_transport::TransportError::ApplicationStreamRejected
        ))
    );
    assert_eq!(
        session.channel_state(revoke_route.channel.channel_id),
        Some(ChannelState::Revoked)
    );

    session
        .pop_audit_event()
        .expect("one close application audit slot");
    let (close_accepted, close_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, close_route.channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit16).await?;
            stream.send_payload(b"close-no-reset").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let mut close_accepted = close_accepted.expect("tracked close target");
    let mut close_opened = close_opened.expect("opened close target");
    assert_eq!(
        destination.accept_route_close(
            &mut session,
            close_route.channel.channel_id,
            &invalid_close,
        ),
        Err(SessionReject::ControlRejected)
    );
    fill_channel_audit_partition(&mut session, &close_route.channel, 10_000);
    assert_eq!(
        destination.accept_route_close(&mut session, close_route.channel.channel_id, &valid_close),
        Err(SessionReject::AuditUnavailable)
    );
    let (close_echo, close_reply) =
        tokio::join!(close_accepted.echo_once(), close_opened.receive_payload());
    assert_eq!(
        close_echo.expect("invalid and audit-failed close did not reset"),
        b"close-no-reset"
    );
    assert_eq!(
        close_reply.expect("non-reset close response"),
        b"close-no-reset"
    );

    pop_until_channel_slot(&mut session, close_route.channel.channel_id);
    let (close_reset_accepted, close_reset_opened) = tokio::join!(
        destination.accept_session_stream(&mut session, close_route.channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit20).await?;
            stream.send_payload(b"close-committed").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let _close_reset_accepted = close_reset_accepted.expect("second tracked close target");
    let mut close_reset_opened = close_reset_opened.expect("second opened close target");
    pop_until_channel_slot(&mut session, close_route.channel.channel_id);
    destination
        .accept_route_close(&mut session, close_route.channel.channel_id, &valid_close)
        .expect("valid audited close");
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), close_reset_opened.receive_payload()).await,
        Ok(Err(
            nbsr_transport::TransportError::ApplicationStreamRejected
        ))
    );
    assert_eq!(
        session.channel_state(close_route.channel.channel_id),
        Some(ChannelState::Closed)
    );
    let (sibling_echo, sibling_reply) = tokio::join!(
        sibling_accepted.echo_once(),
        sibling_opened.receive_payload()
    );
    assert_eq!(
        sibling_echo.expect("sibling target remains live"),
        b"sibling-survives"
    );
    assert_eq!(
        sibling_reply.expect("sibling source remains live"),
        b"sibling-survives"
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
        .begin_session_drain(1_000, NOW, 30)
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
        Ok(SessionDrainEnforcement::Pending {
            audit_integrity: AuditIntegrity::Recorded,
        })
    );
    assert_eq!(
        destination.enforce_session_drain(&mut session, 1_030).await,
        Ok(SessionDrainEnforcement::Enforced {
            audit_integrity: AuditIntegrity::Recorded,
        })
    );
    assert_eq!(session.session_drain_state(), SessionDrainState::Closed);
    let closed_result = tokio::time::timeout(Duration::from_secs(1), async {
        let mut stream = source.open_control_stream().await?;
        stream
            .send_envelope(&decode_vector("artifacts/valid/envelopes/stream-open.cbor"))
            .await?;
        stream.receive_envelope(CoreV02Limits::default()).await
    })
    .await
    .expect("closed session resolves");
    assert!(closed_result.is_err());

    let (other_listener, other_source, other_destination) = connection_pair().await;
    let (rejected, source_result) =
        tokio::join!(other_destination.reject_next_application_stream(), async {
            let mut stream = other_source.open_control_stream().await?;
            stream
                .send_envelope(&decode_vector("artifacts/valid/envelopes/stream-open.cbor"))
                .await?;
            stream.receive_envelope(CoreV02Limits::default()).await
        },);
    assert_eq!(rejected.expect("unrelated reset remains operational"), 0);
    assert_eq!(
        source_result,
        Err(nbsr_transport::TransportError::ControlStreamFailed)
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
async fn session_drain_resets_a_live_channel_at_its_one_second_grant_deadline() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_session = established_session(&source);
    let policy = runtime_policy();
    let mut session = ControlSession::new(
        &destination,
        DestinationAdmission::new(policy).expect("valid admission policy"),
        vec![route_grant_issuer()],
        TrustProfileId::new("test-profile").expect("trust profile"),
    );
    establish(&mut session);
    let channel = vector_channel();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .expect("bind active channel");
    source
        .bind_channel(&mut source_session, channel.channel_id)
        .expect("bind source channel");
    let stream_open = stream_open_envelope(&channel, 4, [0x7b; 16]);
    let stream_accept = stream_accept_envelope(&channel, 4, [0x7b; 16], 22);
    session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .expect("stream opened while grant is live");
    session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .expect("stream accepted while grant is live");
    source_session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .unwrap();
    source_session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .unwrap();
    let permit = source_session
        .application_stream_permit(channel.channel_id, 4)
        .unwrap();
    let (reserved, reserved_source) =
        tokio::join!(destination.reject_next_application_stream(), async {
            let mut stream = source.open_control_stream().await?;
            stream.send_envelope(&stream_open).await?;
            stream.receive_envelope(CoreV02Limits::default()).await
        });
    assert_eq!(reserved.expect("reject stream zero"), 0);
    assert_eq!(
        reserved_source,
        Err(nbsr_transport::TransportError::ControlStreamFailed)
    );
    let (accepted, opened) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit).await?;
            stream.send_payload(b"grant-expiry-reset").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let _accepted = accepted.expect("accepted live stream before session drain");
    let mut opened = opened.expect("opened live stream before session drain");

    session
        .begin_session_drain(1_000, NOW + 299, 30)
        .expect("start requested thirty-second session drain");
    assert_eq!(session.session_drain_deadline(), Some(1_030));
    assert_eq!(
        session.channel_drain_deadline(channel.channel_id),
        Some(1_001)
    );
    assert_eq!(
        destination.enforce_session_drain(&mut session, 1_000).await,
        Ok(SessionDrainEnforcement::Pending {
            audit_integrity: AuditIntegrity::Recorded,
        })
    );
    assert_eq!(
        destination.enforce_session_drain(&mut session, 1_001).await,
        Ok(SessionDrainEnforcement::Pending {
            audit_integrity: AuditIntegrity::Recorded,
        })
    );
    assert_eq!(session.session_drain_state(), SessionDrainState::Draining);
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Closed)
    );
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), opened.receive_payload()).await,
        Ok(Err(
            nbsr_transport::TransportError::ApplicationStreamRejected
        ))
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn session_drain_reports_due_channel_audit_failure_while_resetting_safely() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_session = established_session(&source);
    let policy = runtime_policy();
    let mut session = ControlSession::new(
        &destination,
        DestinationAdmission::new(policy).expect("valid admission policy"),
        vec![route_grant_issuer()],
        TrustProfileId::new("test-profile").expect("trust profile"),
    );
    establish(&mut session);
    let channel = vector_channel();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .expect("bind active channel");
    source
        .bind_channel(&mut source_session, channel.channel_id)
        .expect("bind source channel");
    let stream_open = stream_open_envelope(&channel, 4, [0x7c; 16]);
    let stream_accept = stream_accept_envelope(&channel, 4, [0x7c; 16], 22);
    session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .expect("stream opened while grant is live");
    session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .expect("stream accepted while grant is live");
    source_session
        .authorize_stream_open(channel.channel_id, &stream_open)
        .unwrap();
    source_session
        .confirm_stream_accept(channel.channel_id, &stream_accept)
        .unwrap();
    let permit = source_session
        .application_stream_permit(channel.channel_id, 4)
        .unwrap();
    let (reserved, reserved_source) =
        tokio::join!(destination.reject_next_application_stream(), async {
            let mut stream = source.open_control_stream().await?;
            stream.send_envelope(&stream_open).await?;
            stream.receive_envelope(CoreV02Limits::default()).await
        });
    assert_eq!(reserved.expect("reject stream zero"), 0);
    assert_eq!(
        reserved_source,
        Err(nbsr_transport::TransportError::ControlStreamFailed)
    );
    let (accepted, opened) = tokio::join!(
        destination.accept_session_stream(&mut session, channel.channel_id),
        async {
            let mut stream = source.open_session_stream(&permit).await?;
            stream.send_payload(b"audit-failed-grant-expiry").await?;
            Ok::<_, nbsr_transport::TransportError>(stream)
        },
    );
    let _accepted = accepted.expect("accepted live stream before session drain");
    let mut opened = opened.expect("opened live stream before session drain");
    fill_channel_audit_partition(&mut session, &channel, 100);
    pop_until_channel_slot(&mut session, channel.channel_id);
    session
        .begin_session_drain(1_000, NOW + 299, 30)
        .expect("channel exhaustion preserves the session lifecycle reserve");
    assert_eq!(
        session
            .audit_events()
            .filter(|event| event.channel_id == Some(channel.channel_id))
            .count(),
        1_023
    );
    assert_eq!(
        session.audit_events().last().map(|event| event.channel_id),
        Some(None)
    );

    assert_eq!(
        destination.enforce_session_drain(&mut session, 1_001).await,
        Ok(SessionDrainEnforcement::Pending {
            audit_integrity: AuditIntegrity::Failed,
        })
    );
    assert_eq!(session.session_drain_state(), SessionDrainState::Draining);
    assert_eq!(
        session.channel_state(channel.channel_id),
        Some(ChannelState::Draining)
    );
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), opened.receive_payload()).await,
        Ok(Err(
            nbsr_transport::TransportError::ApplicationStreamRejected
        ))
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn grant_deadlines_can_only_shorten_drain() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = ControlSession::new(
        &destination,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![route_grant_issuer()],
        TrustProfileId::new("test-profile").expect("trust profile"),
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
    session
        .begin_session_drain(100, NOW + 299, 30)
        .expect("session drain preserves every earlier channel authority");
    assert_eq!(session.session_drain_deadline(), Some(130));
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
    fill_channel_audit_partition(&mut session, &channel, 100);

    let drain = decode_control_envelope(
        &lifecycle_envelope(
            [0xde; 16],
            12,
            10_000,
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
    assert_eq!(session.session_drain_state(), SessionDrainState::Active);
    assert_eq!(session.channel_drain_deadline(channel.channel_id), None);

    pop_until_channel_slot(&mut session, channel.channel_id);
    session
        .accept_route_drain(channel.channel_id, &drain, 100, 1_893_456_000)
        .expect("failed start consumed no request or sequence");
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

struct SignedRoute {
    channel: ActiveChannel,
    open: CoreV02Envelope,
    accept: CoreV02Envelope,
}

fn signed_route(id: u8, sequence: u64) -> SignedRoute {
    let request_id = [id.wrapping_add(0x20); 16];
    let channel_id = [id; 16];
    let route_id = [id.wrapping_add(0x40); 16];
    let grant_wire = signed_grant(route_id, [id.wrapping_add(0x80); 16]);
    let grant_digest = Sha256::digest(&grant_wire).into();
    let proof = SigningKey::from_bytes(&SESSION_SEED).sign(&route_open_transcript(
        request_id,
        channel_id,
        route_id,
        grant_digest,
    ));
    let open = decode_generated_envelope(control_envelope(
        3,
        request_id,
        sequence,
        route_open_body(channel_id, &grant_wire, proof.to_bytes()),
    ));
    let accept = route_accept_envelope(request_id, sequence, channel_id, route_id, grant_digest);
    SignedRoute {
        channel: ActiveChannel {
            channel_id,
            route_id,
            service_id: "service.example".into(),
            route_grant_digest: grant_digest,
            transport: "tcp".into(),
            port: 8443,
        },
        open,
        accept,
    }
}

fn lifecycle_control(
    route: &SignedRoute,
    message_type: u64,
    request_id: [u8; 16],
    sequence: u64,
    grant_digest: [u8; 32],
) -> CoreV02Envelope {
    decode_control_envelope(
        &lifecycle_envelope(
            request_id,
            message_type,
            sequence,
            (
                route.channel.channel_id,
                route.channel.route_id,
                grant_digest,
            ),
            NOW,
            None,
        ),
        CoreV02Limits::default(),
    )
    .expect("valid generated lifecycle envelope")
}

fn fill_channel_audit_partition(
    session: &mut ControlSession,
    channel: &ActiveChannel,
    sequence_base: u64,
) {
    let first_stream_id = 24 + u64::from(channel.channel_id[0]) * 1_000_000;
    let mut offset = 0_u64;
    while session.audit_events().len() < 1_024 {
        let stream_id = first_stream_id + offset * 4;
        let request_id = id(30_000 + stream_id);
        let sequence = sequence_base + offset;
        let open = stream_open_envelope_with_sequence(channel, stream_id, request_id, sequence);
        if let Err(error) = session.authorize_stream_open(channel.channel_id, &open) {
            panic!("audit fill failed at offset {offset}, sequence {sequence}: {error:?}");
        }
        if session.audit_events().len() == 1_024 {
            break;
        }
        let accept = stream_accept_envelope(channel, stream_id, request_id, sequence + 100);
        session
            .confirm_stream_accept(channel.channel_id, &accept)
            .expect("confirm transient audit-fill stream");
        session
            .release_stream(channel.channel_id, stream_id)
            .expect("audit-fill stream leaves no capacity mutation");
        offset += 1;
    }
    assert_eq!(session.audit_events().len(), 1_024);
}

fn pop_until_channel_slot(session: &mut ControlSession, channel_id: [u8; 16]) {
    loop {
        let event = session
            .pop_audit_event()
            .expect("target channel has a queued audit event");
        if event.channel_id == Some(channel_id) {
            return;
        }
    }
}

fn signed_grant(route_id: [u8; 16], unique_nonce: [u8; 16]) -> Vec<u8> {
    let session_public_key = SigningKey::from_bytes(&SESSION_SEED)
        .verifying_key()
        .to_bytes();
    let thumbprint: [u8; 32] = Sha256::digest(session_public_key).into();
    let mut payload = Vec::new();
    map(&mut payload, 17);
    field_uint(&mut payload, 0, 1);
    field_bytes(&mut payload, 1, &route_id);
    field_bytes(&mut payload, 2, &[0x11; 32]);
    field_text(&mut payload, 3, "service.example");
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
    field_uint(&mut payload, 14, 42);
    field_bytes(&mut payload, 15, &POLICY_HASH);
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
    text(&mut wire, "service.example");
    text(&mut wire, "destination.edge");
    bytes(&mut wire, &EDGE_NONCE);
    text(&mut wire, "tcp");
    uint(&mut wire, 8443);
    bytes(&mut wire, &grant_digest);
    uint(&mut wire, NOW);
    wire
}

fn route_open_body(channel_id: [u8; 16], grant_wire: &[u8], proof: [u8; 64]) -> Vec<u8> {
    let mut body = Vec::new();
    map(&mut body, 8);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &channel_id);
    field_bytes(&mut body, 2, grant_wire);
    field_bytes(&mut body, 3, &EDGE_NONCE);
    field_text(&mut body, 4, "tcp");
    field_uint(&mut body, 5, 8443);
    field_uint(&mut body, 6, NOW);
    field_bytes(&mut body, 7, &proof);
    body
}

fn route_accept_envelope(
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
    decode_generated_envelope(control_envelope(4, request_id, sequence, body))
}

fn control_envelope(
    message_type: u64,
    request_id: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> Vec<u8> {
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

fn decode_generated_envelope(wire: Vec<u8>) -> CoreV02Envelope {
    decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid generated envelope")
}

fn established_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    let mut session = ControlSession::new(
        connection,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![route_grant_issuer()],
        TrustProfileId::new("test-profile").expect("trust profile"),
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
    stream_open_envelope_with_sequence(channel, stream_id, request_id, 21)
}

fn stream_open_envelope_with_sequence(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
    sequence: u64,
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
    field_uint(&mut wire, 4, sequence);
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

fn array(target: &mut Vec<u8>, length: u64) {
    argument(target, 4, length);
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
