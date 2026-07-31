use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, ControlSession, CoreV02Limits, DestinationAdmission,
    EdgeIdentity, EdgeRole, PeerPolicy, RouteGrantIssuer, StreamGate, TransportError,
    TransportListener, build_client_config, build_server_config, connect, decode_control_envelope,
};
use sha2::{Digest, Sha256};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

fn channel() -> ActiveChannel {
    let grant = vector("artifacts/valid/objects/route-grant-sign1.cose");
    let digest: [u8; 32] = Sha256::digest(grant).into();
    let channel_id: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    let route_id: [u8; 16] = (0x20..0x30).collect::<Vec<_>>().try_into().unwrap();
    ActiveChannel {
        channel_id,
        route_id,
        service_id: "service.example".into(),
        route_grant_digest: digest,
        transport: "tcp".into(),
        port: 8443,
    }
}

fn control_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    let policy = AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        service_id: "service.example".into(),
        accepted_record_sequence: 42,
        policy_hash: [
            0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2, 0xa4,
            0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2, 0xf1, 0x79,
            0x7b, 0xf1, 0x14, 0x3f,
        ],
        now: 1_893_456_000,
        max_channels: 1,
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
    ControlSession::new(connection, DestinationAdmission::new(policy), vec![issuer])
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

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn accepted_stream_id_four_echoes_only_the_bounded_in_memory_payload() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.expect("source control");
    let mut session = control_session(&destination);

    let client_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .expect("CLIENT_HELLO fixture");
    source_control
        .send_envelope(&client_hello)
        .await
        .expect("send CLIENT_HELLO");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    let received_hello = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive CLIENT_HELLO");
    session
        .accept_client_hello(&received_hello)
        .expect("accept CLIENT_HELLO");

    let edge_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/edge-hello.cbor"),
        CoreV02Limits::default(),
    )
    .expect("EDGE_HELLO fixture");
    destination_control
        .send_envelope(&edge_hello)
        .await
        .expect("send EDGE_HELLO");
    let received_edge_hello = source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive EDGE_HELLO");
    session
        .confirm_edge_hello(&received_edge_hello)
        .expect("confirm EDGE_HELLO");

    let route_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("ROUTE_OPEN fixture");
    source_control
        .send_envelope(&route_open)
        .await
        .expect("send ROUTE_OPEN");
    let received_route_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive ROUTE_OPEN");
    session
        .accept_route_open(&received_route_open)
        .expect("admit received ROUTE_OPEN");
    assert_eq!(
        session.stream_gate().err(),
        Some(nbsr_transport::SessionReject::UnexpectedMessage)
    );

    let route_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("ROUTE_ACCEPT fixture");
    destination_control
        .send_envelope(&route_accept)
        .await
        .expect("send ROUTE_ACCEPT");
    let received_route_accept = source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive ROUTE_ACCEPT");
    session
        .confirm_route_accept(&received_route_accept)
        .expect("confirm admitted ROUTE_ACCEPT");

    let stream_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_OPEN fixture");
    let stream_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_ACCEPT fixture");
    source_control
        .send_envelope(&stream_open)
        .await
        .expect("send STREAM_OPEN");
    let received_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_OPEN");
    let mut gate = session
        .stream_gate()
        .expect("accepted route creates stream gate");
    gate.authorize_open(&received_open)
        .expect("authorize received STREAM_OPEN");
    gate.accept(&stream_accept)
        .expect("bind matching STREAM_ACCEPT");
    destination_control
        .send_envelope(&stream_accept)
        .await
        .expect("send STREAM_ACCEPT");
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_ACCEPT");

    let (echoed_at_destination, echoed_at_source) = tokio::join!(
        async {
            let mut stream = destination
                .accept_application_stream(&mut gate)
                .await
                .expect("accept application stream");
            assert_eq!(stream.id(), 4);
            stream.echo_once().await.expect("bounded echo")
        },
        async {
            let mut stream = source
                .open_application_stream()
                .await
                .expect("open application stream");
            assert_eq!(stream.id(), 4);
            stream
                .send_and_receive(b"nbsr-lab")
                .await
                .expect("receive bounded echo")
        }
    );
    assert_eq!(echoed_at_destination, b"nbsr-lab");
    assert_eq!(echoed_at_source, b"nbsr-lab");

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_before_stream_accept_is_reset_without_delivery() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.expect("source control");
    let client_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .expect("CLIENT_HELLO fixture");
    source_control
        .send_envelope(&client_hello)
        .await
        .expect("send CLIENT_HELLO");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive CLIENT_HELLO");

    let (rejected, source_result) = tokio::join!(
        async {
            destination
                .reject_next_application_stream()
                .await
                .expect("reset unauthorized stream")
        },
        async {
            let mut stream = source
                .open_application_stream()
                .await
                .expect("open unauthorized stream");
            stream
                .send_payload(b"early")
                .await
                .expect("send early payload");
            stream.receive_payload().await
        }
    );
    assert_eq!(rejected, 4);
    assert_eq!(
        source_result,
        Err(TransportError::ApplicationStreamRejected)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_over_four_kib_is_reset_without_echo() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.expect("source control");
    let stream_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_OPEN fixture");
    source_control
        .send_envelope(&stream_open)
        .await
        .expect("send STREAM_OPEN");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    let received_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_OPEN");
    let stream_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_ACCEPT fixture");
    let mut gate = StreamGate::new(channel());
    gate.authorize_open(&received_open)
        .expect("authorize received STREAM_OPEN");
    gate.accept(&stream_accept)
        .expect("bind matching STREAM_ACCEPT");
    destination_control
        .send_envelope(&stream_accept)
        .await
        .expect("send STREAM_ACCEPT");
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_ACCEPT");

    let payload = vec![0x5a; 4_097];
    let (destination_result, source_result) = tokio::join!(
        async {
            let mut stream = destination
                .accept_application_stream(&mut gate)
                .await
                .expect("accept application stream");
            stream.echo_once().await
        },
        async {
            let mut stream = source
                .open_application_stream()
                .await
                .expect("open application stream");
            stream.send_and_receive(&payload).await
        }
    );
    assert_eq!(
        destination_result,
        Err(TransportError::ApplicationPayloadTooLarge)
    );
    assert_eq!(
        source_result,
        Err(TransportError::ApplicationStreamRejected)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}
