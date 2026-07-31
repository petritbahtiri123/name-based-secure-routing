use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use nbsr_transport::{
    CoreV02Limits, CoreV02MessageType, EdgeIdentity, EdgeRole, PeerPolicy, TransportListener,
    build_client_config, build_server_config, connect, decode_control_envelope,
};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn first_bidirectional_stream_carries_a_version_locked_control_frame() {
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
    let destination = destination.expect("destination connection");
    let source = source.expect("source connection");
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let fixture =
        std::fs::read(root.join("vectors/core-v0.2/artifacts/valid/envelopes/client-hello.cbor"))
            .expect("fixture");
    let envelope = decode_control_envelope(&fixture, CoreV02Limits::default()).expect("v2 fixture");

    let (received, sent) = tokio::join!(
        async {
            let mut stream = destination
                .accept_control_stream()
                .await
                .expect("control stream");
            stream
                .receive_envelope(CoreV02Limits::default())
                .await
                .expect("control frame")
        },
        async {
            let mut stream = source.open_control_stream().await.expect("control stream");
            stream.send_envelope(&envelope).await.expect("send control")
        }
    );
    assert_eq!(sent, ());
    assert_eq!(received.message_type(), CoreV02MessageType::ClientHello);
    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}
