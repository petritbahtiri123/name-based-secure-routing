use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use nbsr_transport::{
    ActiveChannel, CoreV02Limits, EdgeIdentity, EdgeRole, PeerPolicy, StreamGate, TransportError,
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

async fn connection_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate();
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination-edge.test"),
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
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    let received_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_OPEN");
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
