use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use ed25519_dalek::{Signer, SigningKey};
use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuditAction, AuthorizedServicePolicy, ChannelState,
    ControlSession, CoreV02Envelope, CoreV02Limits, DestinationAdmission, EdgeIdentity, EdgeRole,
    PeerPolicy, RouteGrantIssuer, SessionReject, StreamReject, TransportListener, TrustProfileId,
    build_client_config, build_server_config, connect, decode_control_envelope,
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

fn channel(id: u8) -> ActiveChannel {
    ActiveChannel {
        channel_id: [id; 16],
        route_id: [id.wrapping_add(0x40); 16],
        service_id: format!("service-{id}"),
        route_grant_digest: [id.wrapping_add(0x80); 32],
        transport: "tcp".into(),
        port: 8443,
    }
}

fn stream_open(channel: &ActiveChannel, stream_id: u64, request_id: [u8; 16]) -> CoreV02Envelope {
    stream_open_with_sequence(channel, stream_id, request_id, 5 + stream_id / 4)
}

fn stream_open_with_sequence(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
    sequence: u64,
) -> CoreV02Envelope {
    decode_stream_open_with_sequence(channel, stream_id, request_id, sequence)
        .expect("valid stream control")
}

fn decode_stream_open(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
) -> Result<CoreV02Envelope, nbsr_transport::CoreV02Reject> {
    decode_stream_open_with_sequence(channel, stream_id, request_id, 5)
}

fn decode_stream_open_with_sequence(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
    sequence: u64,
) -> Result<CoreV02Envelope, nbsr_transport::CoreV02Reject> {
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, stream_id);
    field_bytes(&mut body, 2, &channel.channel_id);
    field_bytes(&mut body, 3, &channel.route_id);
    field_bytes(&mut body, 4, &channel.route_grant_digest);
    field_text(&mut body, 5, &channel.transport);
    field_uint(&mut body, 6, u64::from(channel.port));
    decode_envelope(6, request_id, SESSION_ID, sequence, body)
}

fn stream_accept(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
    session_id: [u8; 16],
) -> CoreV02Envelope {
    stream_accept_with_sequence(
        channel,
        stream_id,
        request_id,
        session_id,
        6 + stream_id / 4,
    )
}

fn stream_accept_with_sequence(
    channel: &ActiveChannel,
    stream_id: u64,
    request_id: [u8; 16],
    session_id: [u8; 16],
    sequence: u64,
) -> CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, stream_id);
    field_bytes(&mut body, 2, &channel.channel_id);
    field_bytes(&mut body, 3, &channel.route_id);
    field_uint(&mut body, 4, 1_893_456_000);
    decode_envelope(7, request_id, session_id, sequence, body).expect("valid stream control")
}

fn route_revoke(
    channel: &ActiveChannel,
    request_id: [u8; 16],
    sequence: u64,
    revoked_at: u64,
) -> CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &channel.channel_id);
    field_bytes(&mut body, 2, &channel.route_id);
    field_bytes(&mut body, 3, &channel.route_grant_digest);
    field_uint(&mut body, 4, revoked_at);
    decode_envelope(13, request_id, SESSION_ID, sequence, body).expect("valid ROUTE_REVOKE control")
}

fn decode_envelope(
    message_type: u64,
    request_id: [u8; 16],
    session_id: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> Result<CoreV02Envelope, nbsr_transport::CoreV02Reject> {
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message_type);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &session_id);
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default())
}

#[test]
fn invalid_role_parity_reserved_and_overflow_ids_fail_closed() {
    let active = channel(1);
    for stream_id in [0, 1, 2, 3, 5, 6, 7, 4_611_686_018_427_387_904] {
        assert!(decode_stream_open(&active, stream_id, [0x41; 16]).is_err());
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn quinn_streams_four_eight_and_twelve_echo_on_two_bound_channels() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (listener, source, destination) = connection_pair_with_pki(&pki).await;
    let issuer_key = SigningKey::from_bytes(&ROUTE_GRANT_SEED)
        .verifying_key()
        .to_bytes();
    let mut session = ControlSession::new(
        &destination,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![RouteGrantIssuer {
            kid: KID.to_vec(),
            public_key: issuer_key,
        }],
        TrustProfileId::new("test-profile").expect("trust profile"),
    );
    let mut source_session = ControlSession::new(
        &source,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![RouteGrantIssuer {
            kid: KID.to_vec(),
            public_key: issuer_key,
        }],
        TrustProfileId::new("test-profile").expect("trust profile"),
    );
    let client_hello = decode_vector("artifacts/valid/envelopes/client-hello.cbor");
    let edge_hello = decode_vector("artifacts/valid/envelopes/edge-hello.cbor");
    for peer_session in [&mut session, &mut source_session] {
        peer_session
            .accept_client_hello(&client_hello)
            .expect("CLIENT_HELLO");
        peer_session
            .confirm_edge_hello(&edge_hello)
            .expect("EDGE_HELLO");
    }
    let (route_a, accept_a) = signed_route(1, "service-a", 42, POLICY_A, 2);
    let channel_a = session
        .accept_route_open(&route_a)
        .expect("service A route open");
    let source_channel_a = source_session
        .accept_route_open(&route_a)
        .expect("source-side service A route open");
    assert_eq!(source_channel_a, channel_a);
    session
        .confirm_route_accept(&accept_a)
        .expect("service A route accept");
    source_session
        .confirm_route_accept(&accept_a)
        .expect("source-side service A route accept");
    let (route_b, accept_b) = signed_route(2, "service-b", 43, POLICY_B, 3);
    let channel_b = session
        .accept_route_open(&route_b)
        .expect("service B route open");
    let source_channel_b = source_session
        .accept_route_open(&route_b)
        .expect("source-side service B route open");
    assert_eq!(source_channel_b, channel_b);
    assert_eq!(
        destination.bind_channel(&mut session, channel_b.channel_id),
        Err(SessionReject::UnexpectedMessage)
    );
    session
        .confirm_route_accept(&accept_b)
        .expect("service B route accept");
    source_session
        .confirm_route_accept(&accept_b)
        .expect("source-side service B route accept");
    assert_eq!(session.active_channels(), 2);

    let max_stream_id = 4_611_686_018_427_387_900;
    let max_stream_open = stream_open(&channel_a, max_stream_id, [0xfc; 16]);
    assert_eq!(
        session.authorize_stream_open(channel_a.channel_id, &max_stream_open),
        Err(SessionReject::ChannelBindingRequired)
    );
    let (replacement_listener, replacement_source, replacement_destination) =
        connection_pair_with_pki(&pki).await;
    assert_eq!(
        replacement_destination.bind_channel(&mut session, channel_a.channel_id),
        Err(SessionReject::ConnectionMismatch)
    );
    assert_eq!(
        session.authorize_stream_open(channel_a.channel_id, &max_stream_open),
        Err(SessionReject::ChannelBindingRequired)
    );
    replacement_source
        .close()
        .await
        .expect("replacement source close");
    replacement_destination
        .close()
        .await
        .expect("replacement destination close");
    replacement_listener
        .close()
        .await
        .expect("replacement listener close");
    let (wrong_listener, wrong_source, wrong_destination) =
        connection_pair_for("wrong-source.edge", "wrong-destination.edge").await;
    assert_eq!(
        wrong_destination.bind_channel(&mut session, channel_a.channel_id),
        Err(SessionReject::ConnectionMismatch)
    );
    wrong_source.close().await.expect("wrong source close");
    wrong_destination
        .close()
        .await
        .expect("wrong destination close");
    wrong_listener.close().await.expect("wrong listener close");
    source
        .bind_channel(&mut source_session, channel_a.channel_id)
        .expect("source peer derives channel A binding");
    destination
        .bind_channel(&mut session, channel_a.channel_id)
        .expect("destination peer derives the same channel A binding");
    destination
        .bind_channel(&mut session, channel_b.channel_id)
        .expect("destination peer derives independent channel B binding");
    source
        .bind_channel(&mut source_session, channel_b.channel_id)
        .expect("source peer derives independent channel B binding");
    assert_eq!(
        destination.bind_channel(&mut session, [0xee; 16]),
        Err(SessionReject::UnexpectedMessage)
    );
    let max_stream_open = stream_open_with_sequence(&channel_a, max_stream_id, [0xfc; 16], 5);
    session
        .authorize_stream_open(channel_a.channel_id, &max_stream_open)
        .expect("maximum source bidirectional stream ID");
    session
        .confirm_stream_accept(
            channel_a.channel_id,
            &stream_accept_with_sequence(&channel_a, max_stream_id, [0xfc; 16], SESSION_ID, 6),
        )
        .expect("maximum stream accept binding");
    session
        .release_stream(channel_a.channel_id, max_stream_id)
        .expect("release maximum stream fixture");

    for (stream_id, mutated, expected) in [
        {
            let mut value = channel_a.clone();
            value.route_id = [0xee; 16];
            (16, value, StreamReject::RouteMismatch)
        },
        {
            let mut value = channel_a.clone();
            value.route_grant_digest = [0xdd; 32];
            (20, value, StreamReject::ChannelMismatch)
        },
        {
            let mut value = channel_a.clone();
            value.port = 443;
            (24, value, StreamReject::UnsupportedTransport)
        },
    ] {
        assert_eq!(
            session.authorize_stream_open(
                channel_a.channel_id,
                &stream_open(&mutated, stream_id, [stream_id as u8; 16]),
            ),
            Err(SessionReject::Stream(expected))
        );
    }
    let mut wrong_transport = channel_a.clone();
    wrong_transport.transport = "udp".into();
    assert!(decode_stream_open(&wrong_transport, 28, [28; 16]).is_err());

    let mut source_control = source.open_control_stream().await.expect("source control");
    let mut destination_control = None;

    for (stream_id, active, payload) in [
        (4, &channel_a, b"channel-a-first".to_vec()),
        (8, &channel_b, b"channel-b-only".to_vec()),
        (12, &channel_a, vec![0x5a; 4_096]),
    ] {
        let request_id = [stream_id as u8; 16];
        let open = stream_open(active, stream_id, request_id);
        source_control
            .send_envelope(&open)
            .await
            .expect("send STREAM_OPEN");
        if destination_control.is_none() {
            destination_control = Some(
                destination
                    .accept_control_stream()
                    .await
                    .expect("destination control"),
            );
        }
        let received_open = destination_control
            .as_mut()
            .expect("control stream established")
            .receive_envelope(CoreV02Limits::default())
            .await
            .expect("receive STREAM_OPEN");
        session
            .authorize_stream_open(active.channel_id, &received_open)
            .expect("bind stream open");

        if stream_id == 4 {
            assert_eq!(
                session.confirm_stream_accept(
                    active.channel_id,
                    &stream_accept(active, stream_id, [0x32; 16], SESSION_ID),
                ),
                Err(SessionReject::Stream(StreamReject::ControlRejected))
            );
            assert_eq!(
                session.confirm_stream_accept(
                    active.channel_id,
                    &stream_accept(active, stream_id, request_id, [0x11; 16]),
                ),
                Err(SessionReject::Replay)
            );
        }

        let accept = stream_accept(active, stream_id, request_id, SESSION_ID);
        destination_control
            .as_mut()
            .expect("control stream established")
            .send_envelope(&accept)
            .await
            .expect("send STREAM_ACCEPT");
        let received_accept = source_control
            .receive_envelope(CoreV02Limits::default())
            .await
            .expect("receive STREAM_ACCEPT");
        session
            .confirm_stream_accept(active.channel_id, &received_accept)
            .expect("bind stream accept");

        let (at_destination, at_source) = tokio::join!(
            async {
                let mut stream = destination
                    .accept_session_stream(&mut session, active.channel_id)
                    .await
                    .expect("accept authorized stream");
                assert_eq!(stream.id(), stream_id);
                stream.echo_once().await.expect("bounded in-memory echo")
            },
            async {
                let mut stream = source
                    .open_application_stream()
                    .await
                    .expect("open application stream");
                assert_eq!(stream.id(), stream_id);
                stream
                    .send_and_receive(&payload)
                    .await
                    .expect("receive matching echo")
            }
        );
        assert_eq!(at_destination, payload);
        assert_eq!(at_source, payload);
    }

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn revoked_channel_is_terminal_while_bound_sibling_remains_usable() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (listener, source, destination) = connection_pair_with_pki(&pki).await;
    let issuer_key = SigningKey::from_bytes(&ROUTE_GRANT_SEED)
        .verifying_key()
        .to_bytes();
    let mut session = ControlSession::new(
        &destination,
        DestinationAdmission::new(runtime_policy()).expect("valid admission policy"),
        vec![RouteGrantIssuer {
            kid: KID.to_vec(),
            public_key: issuer_key,
        }],
        TrustProfileId::new("test-profile").expect("trust profile"),
    );
    session
        .accept_client_hello(&decode_vector(
            "artifacts/valid/envelopes/client-hello.cbor",
        ))
        .expect("CLIENT_HELLO");
    session
        .confirm_edge_hello(&decode_vector("artifacts/valid/envelopes/edge-hello.cbor"))
        .expect("EDGE_HELLO");

    let (route_a, accept_a) = signed_route(1, "service-a", 42, POLICY_A, 2);
    let channel_a = session.accept_route_open(&route_a).expect("route A open");
    session
        .confirm_route_accept(&accept_a)
        .expect("route A accept");
    let (route_b, accept_b) = signed_route(2, "service-b", 43, POLICY_B, 3);
    let channel_b = session.accept_route_open(&route_b).expect("route B open");
    session
        .confirm_route_accept(&accept_b)
        .expect("route B accept");
    destination
        .bind_channel(&mut session, channel_a.channel_id)
        .expect("bind A");
    destination
        .bind_channel(&mut session, channel_b.channel_id)
        .expect("bind B");

    let revoke_a = route_revoke(&channel_a, [0xa1; 16], 4, NOW + 100);
    destination
        .accept_route_revoke(&mut session, channel_a.channel_id, &revoke_a)
        .expect("revoke A");
    assert_eq!(
        session.channel_state(channel_a.channel_id),
        Some(ChannelState::Revoked)
    );
    assert_eq!(
        session.tombstone_expires_at(channel_a.channel_id),
        Some(NOW + 330)
    );
    assert_eq!(
        session.authorize_stream_open(
            channel_a.channel_id,
            &stream_open(&channel_a, 4, [0x41; 16])
        ),
        Err(SessionReject::InvalidChannelState)
    );
    assert_eq!(
        session.reserve_stream_bytes(channel_a.channel_id, 4, 1),
        Err(SessionReject::InvalidChannelState)
    );
    assert_eq!(
        destination.bind_channel(&mut session, channel_a.channel_id),
        Err(SessionReject::InvalidChannelState)
    );
    assert_eq!(
        destination.accept_route_revoke(&mut session, channel_a.channel_id, &revoke_a),
        Err(SessionReject::Replay)
    );
    let unknown = channel(0xee);
    let revoke_unknown = route_revoke(&unknown, [0xa2; 16], 5, NOW + 101);
    assert_eq!(
        destination.accept_route_revoke(&mut session, unknown.channel_id, &revoke_unknown),
        Err(SessionReject::UnexpectedMessage)
    );

    session
        .authorize_stream_open(
            channel_b.channel_id,
            &stream_open(&channel_b, 8, [0x42; 16]),
        )
        .expect("bound sibling remains usable");
    assert_eq!(
        session.channel_state(channel_b.channel_id),
        Some(ChannelState::Active)
    );
    let actions = session
        .audit_events()
        .map(|event| event.action)
        .collect::<Vec<_>>();
    assert!(actions.contains(&AuditAction::ChannelRevoked));
    assert!(actions.contains(&AuditAction::StreamAuthorized));

    while session.pop_audit_event().is_some() {}
    for (index, stream_id) in (4..=256)
        .step_by(4)
        .filter(|stream_id| *stream_id != 8)
        .enumerate()
    {
        session
            .authorize_stream_open(
                channel_b.channel_id,
                &stream_open_with_sequence(
                    &channel_b,
                    stream_id,
                    [0x50 + index as u8; 16],
                    100 + index as u64,
                ),
            )
            .expect("fill sibling stream slots");
        while session.pop_audit_event().is_some() {}
    }
    for index in 0..1_024_u64 {
        let mut request_id = [0xf0; 16];
        request_id[8..].copy_from_slice(&index.to_be_bytes());
        assert_eq!(
            session.authorize_stream_open(
                channel_b.channel_id,
                // Failed authorization is mutation-free, so the same next
                // control sequence remains reusable with each fresh request.
                &stream_open_with_sequence(&channel_b, 260, request_id, 1_000),
            ),
            Err(SessionReject::Stream(StreamReject::OverCapacity))
        );
    }
    assert_eq!(
        session
            .audit_events()
            .filter(|event| event.channel_id == Some(channel_b.channel_id))
            .count(),
        1_024
    );
    let revoke_b = route_revoke(&channel_b, [0xa3; 16], 3_000, NOW + 200);
    assert_eq!(
        destination.accept_route_revoke(&mut session, channel_b.channel_id, &revoke_b),
        Err(SessionReject::AuditUnavailable)
    );
    assert_eq!(
        session.channel_state(channel_b.channel_id),
        Some(ChannelState::Active)
    );
    destination
        .bind_channel(&mut session, channel_b.channel_id)
        .expect("audit exhaustion did not unbind sibling");

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

async fn connection_pair_with_pki(
    pki: &support::TestPki,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    connection_pair_with_pki_for(pki, "source.edge", "destination.edge").await
}

async fn connection_pair_for(
    source_edge_id: &str,
    destination_edge_id: &str,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate_for(source_edge_id, destination_edge_id);
    connection_pair_with_pki_for(&pki, source_edge_id, destination_edge_id).await
}

async fn connection_pair_with_pki_for(
    pki: &support::TestPki,
    source_edge_id: &str,
    destination_edge_id: &str,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity(source_edge_id),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity(destination_edge_id),
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

fn runtime_policy() -> AdmissionPolicy {
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
        client_session_public_key: SigningKey::from_bytes(&SESSION_SEED)
            .verifying_key()
            .to_bytes(),
        edge_nonce: EDGE_NONCE,
    }
}

fn decode_vector(relative: &str) -> CoreV02Envelope {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let wire =
        std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture");
    decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid vector")
}

fn signed_route(
    id: u8,
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
    sequence: u64,
) -> (CoreV02Envelope, CoreV02Envelope) {
    let request_id = [id.wrapping_add(0x20); 16];
    let channel_id = [id; 16];
    let route_id = [id.wrapping_add(0x40); 16];
    let grant_wire = signed_grant(
        route_id,
        [id.wrapping_add(0x80); 16],
        service_id,
        record_sequence,
        policy_hash,
    );
    let grant_digest: [u8; 32] = Sha256::digest(&grant_wire).into();
    let proof = SigningKey::from_bytes(&SESSION_SEED).sign(&route_open_transcript(
        request_id,
        channel_id,
        route_id,
        service_id,
        grant_digest,
    ));

    let mut open_body = Vec::new();
    map(&mut open_body, 8);
    field_uint(&mut open_body, 0, 1);
    field_bytes(&mut open_body, 1, &channel_id);
    field_bytes(&mut open_body, 2, &grant_wire);
    field_bytes(&mut open_body, 3, &EDGE_NONCE);
    field_text(&mut open_body, 4, "tcp");
    field_uint(&mut open_body, 5, 8443);
    field_uint(&mut open_body, 6, NOW);
    field_bytes(&mut open_body, 7, &proof.to_bytes());

    let mut accept_body = Vec::new();
    map(&mut accept_body, 5);
    field_uint(&mut accept_body, 0, 1);
    field_bytes(&mut accept_body, 1, &channel_id);
    field_bytes(&mut accept_body, 2, &route_id);
    field_bytes(&mut accept_body, 3, &grant_digest);
    field_uint(&mut accept_body, 4, NOW);

    (
        decode_envelope(3, request_id, SESSION_ID, sequence, open_body).expect("valid ROUTE_OPEN"),
        decode_envelope(4, request_id, SESSION_ID, sequence, accept_body)
            .expect("valid ROUTE_ACCEPT"),
    )
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
