use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Duration;

use nbsr_transport::{
    ALPN, EdgeIdentity, EdgeRole, PeerPolicy, TlsMaterial, TransportError, TransportListener,
    build_client_config, build_server_config, connect,
};
use quinn::{Endpoint, VarInt};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("valid test identity")
}

fn source_policy() -> PeerPolicy {
    PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy")
}

fn destination_policy() -> PeerPolicy {
    PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn valid_mutual_auth_handshake_exposes_only_expected_peer_identity() {
    let pki = support::TestPki::generate();
    let listener = TransportListener::bind(
        build_server_config(destination_policy(), pki.destination_material())
            .expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("loopback listener");
    let remote = listener.local_addr().expect("listener address");

    let (destination, source) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy(), pki.source_material()).expect("client config"),
            remote,
        )
    );
    let destination = destination.expect("destination handshake");
    let source = source.expect("source handshake");

    assert_eq!(
        source.authenticated_peer().as_str(),
        "destination-edge.test"
    );
    assert_eq!(
        destination.authenticated_peer().as_str(),
        "source-edge.test"
    );
    assert_eq!(source.negotiated_alpn(), ALPN);
    assert_eq!(destination.negotiated_alpn(), ALPN);

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

async fn handshake_result(
    source_material: TlsMaterial,
    destination_material: TlsMaterial,
    source: PeerPolicy,
    destination: PeerPolicy,
) -> (
    Result<nbsr_transport::AuthenticatedConnection, TransportError>,
    Result<nbsr_transport::AuthenticatedConnection, TransportError>,
) {
    let listener = TransportListener::bind(
        build_server_config(destination, destination_material).expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("loopback listener");
    let remote = listener.local_addr().expect("listener address");
    let result = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source, source_material).expect("client config"),
            remote,
        )
    );
    listener.close().await.expect("listener close");
    result
}

async fn assert_destination_rejected(
    destination: Result<nbsr_transport::AuthenticatedConnection, TransportError>,
    source: Result<nbsr_transport::AuthenticatedConnection, TransportError>,
) {
    assert!(
        destination.is_err(),
        "destination unexpectedly authenticated"
    );
    if let Ok(source) = source {
        source.close().await.expect("close source after rejection");
    }
}

async fn assert_source_rejected(
    destination: Result<nbsr_transport::AuthenticatedConnection, TransportError>,
    source: Result<nbsr_transport::AuthenticatedConnection, TransportError>,
) {
    assert!(source.is_err(), "source unexpectedly authenticated");
    if let Ok(destination) = destination {
        destination
            .close()
            .await
            .expect("close destination after rejection");
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn client_certificate_from_unknown_ca_is_rejected() {
    let trusted = support::TestPki::generate();
    let rogue = support::TestPki::generate();

    let (destination, source) = handshake_result(
        rogue.source_material_trusting(&trusted),
        trusted.destination_material(),
        source_policy(),
        destination_policy(),
    )
    .await;

    assert_destination_rejected(destination, source).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn server_certificate_from_unknown_ca_is_rejected() {
    let trusted = support::TestPki::generate();
    let rogue = support::TestPki::generate();

    let (destination, source) = handshake_result(
        trusted.source_material(),
        rogue.destination_material_trusting(&trusted),
        source_policy(),
        destination_policy(),
    )
    .await;

    assert_source_rejected(destination, source).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn expired_client_certificate_is_rejected() {
    let pki = support::TestPki::generate_with_expired_source();

    let (destination, source) = handshake_result(
        pki.source_material(),
        pki.destination_material(),
        source_policy(),
        destination_policy(),
    )
    .await;

    assert_destination_rejected(destination, source).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn expired_server_certificate_is_rejected() {
    let pki = support::TestPki::generate_with_expired_destination();

    let (destination, source) = handshake_result(
        pki.source_material(),
        pki.destination_material(),
        source_policy(),
        destination_policy(),
    )
    .await;

    assert_source_rejected(destination, source).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn source_identity_mismatch_is_rejected() {
    let pki = support::TestPki::generate();
    let mismatched_destination = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("different-source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");

    let (destination, source) = handshake_result(
        pki.source_material(),
        pki.destination_material(),
        source_policy(),
        mismatched_destination,
    )
    .await;

    assert_destination_rejected(destination, source).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn destination_identity_mismatch_is_rejected() {
    let pki = support::TestPki::generate();
    let mismatched_source = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("different-destination-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy");

    let (destination, source) = handshake_result(
        pki.source_material(),
        pki.destination_material(),
        mismatched_source,
        destination_policy(),
    )
    .await;

    assert_source_rejected(destination, source).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn missing_client_certificate_is_rejected() {
    let pki = support::TestPki::generate();
    let listener = TransportListener::bind(
        build_server_config(destination_policy(), pki.destination_material())
            .expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("loopback listener");
    let remote = listener.local_addr().expect("listener address");
    let mut endpoint = Endpoint::client(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0))
        .expect("raw client endpoint");
    endpoint.set_default_client_config(pki.client_config_without_certificate(ALPN));

    let (destination, source) = tokio::join!(
        listener.accept_one(),
        endpoint
            .connect(remote, "destination-edge.test")
            .expect("start raw connection")
    );

    assert!(
        destination.is_err(),
        "missing client certificate was accepted"
    );
    if let Ok(source) = source {
        source.close(VarInt::from_u32(0), b"");
    }
    endpoint.close(VarInt::from_u32(0), b"");
    endpoint.wait_idle().await;
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn alpn_mismatch_is_rejected() {
    let pki = support::TestPki::generate();
    let endpoint = Endpoint::server(
        pki.server_config_with_alpn(b"not-nbsr"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("raw server endpoint");
    let remote = endpoint.local_addr().expect("server address");

    let (destination, source) = tokio::join!(
        async {
            let incoming = endpoint.accept().await.expect("incoming connection");
            incoming.await
        },
        connect(
            build_client_config(source_policy(), pki.source_material()).expect("client config"),
            remote,
        )
    );

    assert!(source.is_err(), "mismatched ALPN was accepted");
    if let Ok(destination) = destination {
        destination.close(VarInt::from_u32(0), b"");
    }
    endpoint.close(VarInt::from_u32(0), b"");
    endpoint.wait_idle().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn accept_times_out_without_allocating_an_authenticated_connection() {
    let pki = support::TestPki::generate();
    let policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_millis(20),
        Duration::from_secs(5),
    )
    .expect("short destination policy");
    let listener = TransportListener::bind(
        build_server_config(policy, pki.destination_material()).expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("loopback listener");

    match listener.accept_one().await {
        Err(error) => assert_eq!(error, TransportError::HandshakeTimeout),
        Ok(_) => panic!("listener unexpectedly authenticated a peer"),
    }
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn peer_refusal_during_setup_is_rejected() {
    let pki = support::TestPki::generate();
    let endpoint = Endpoint::server(
        pki.server_config_with_alpn(ALPN),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("raw server endpoint");
    let remote = endpoint.local_addr().expect("server address");

    let (_, source) = tokio::join!(
        async {
            endpoint
                .accept()
                .await
                .expect("incoming connection")
                .refuse();
        },
        connect(
            build_client_config(source_policy(), pki.source_material()).expect("client config"),
            remote,
        )
    );

    match source {
        Err(error) => assert_eq!(error, TransportError::HandshakeFailed),
        Ok(_) => panic!("refused peer unexpectedly authenticated"),
    }
    endpoint.close(VarInt::from_u32(0), b"");
    endpoint.wait_idle().await;
}

// A loopback UDP gate forwards the first client's Initial but withholds server
// replies. Observing a server reply establishes the stall before client two starts.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn two_accept_slots_allow_healthy_peer_while_first_handshake_stalls() {
    use std::sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    };
    let pki = support::TestPki::generate();
    let listener = Arc::new(
        TransportListener::bind(
            build_server_config(destination_policy(), pki.destination_material()).unwrap(),
            "127.0.0.1:0".parse().unwrap(),
        )
        .unwrap(),
    );
    let remote = listener.local_addr().unwrap();
    let relay = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
    relay
        .set_read_timeout(Some(Duration::from_millis(50)))
        .unwrap();
    let relay_addr = relay.local_addr().unwrap();
    let stop = Arc::new(AtomicBool::new(false));
    let relay_stop = stop.clone();
    let (ready_tx, ready_rx) = tokio::sync::oneshot::channel();
    let relay_thread = std::thread::spawn(move || {
        let mut ready = Some(ready_tx);
        let mut buffer = [0; 65536];
        while !relay_stop.load(Ordering::Acquire) {
            match relay.recv_from(&mut buffer) {
                Ok((_, from)) if from == remote => {
                    if let Some(ready) = ready.take() {
                        let _ = ready.send(());
                    }
                }
                Ok((length, _)) => {
                    relay.send_to(&buffer[..length], remote).unwrap();
                }
                Err(error)
                    if matches!(
                        error.kind(),
                        std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                    ) => {}
                Err(error) => panic!("relay receive: {error}"),
            }
        }
    });
    struct RelayGuard(Arc<AtomicBool>, Option<std::thread::JoinHandle<()>>);
    impl Drop for RelayGuard {
        fn drop(&mut self) {
            self.0.store(true, Ordering::Release);
            if let Some(thread) = self.1.take() {
                let _ = thread.join();
            }
        }
    }
    let relay_guard = RelayGuard(stop, Some(relay_thread));
    let mut blocked_endpoint = Endpoint::client("127.0.0.1:0".parse().unwrap()).unwrap();
    blocked_endpoint.set_default_client_config(pki.client_config_without_certificate(ALPN));
    let blocked_connect = blocked_endpoint
        .connect(relay_addr, "destination-edge.test")
        .unwrap();
    let first_listener = listener.clone();
    let first = tokio::spawn(async move { first_listener.accept_one().await });
    let result = tokio::time::timeout(Duration::from_secs(8), async {
        ready_rx.await.expect("server emitted handshake response");
        assert!(
            !first.is_finished(),
            "first handshake must still be pending"
        );
        let (destination, source) = tokio::time::timeout(Duration::from_secs(1), async {
            tokio::join!(
                listener.accept_one(),
                connect(
                    build_client_config(source_policy(), pki.source_material()).unwrap(),
                    remote
                )
            )
        })
        .await
        .expect("healthy connection must progress before the stalled two-second deadline");
        let destination = destination.expect("healthy destination authentication");
        let source = source.expect("healthy source authentication");
        assert_eq!(
            destination.authenticated_peer().as_str(),
            "source-edge.test"
        );
        assert_eq!(
            source.authenticated_peer().as_str(),
            "destination-edge.test"
        );
        assert_eq!(destination.negotiated_alpn(), ALPN);
        assert!(
            !first.is_finished(),
            "healthy peer completed while first still pending"
        );
        (source, destination)
    })
    .await;
    // Connection close waits for the shared endpoint, so cancel and join the
    // deliberately stalled acceptance before asking the healthy peer to drain.
    first.abort();
    match first.await {
        Err(error) => assert!(error.is_cancelled()),
        Ok(Err(TransportError::HandshakeTimeout)) => {}
        _ => panic!("stalled unauthenticated peer must never be accepted"),
    }
    drop(blocked_connect);
    blocked_endpoint.close(VarInt::from_u32(0), b"");
    blocked_endpoint.wait_idle().await;
    drop(relay_guard);
    let (source, destination) = result.expect("bounded two-connection test");
    source.close().await.expect("healthy source drained");
    destination
        .close()
        .await
        .expect("healthy destination drained");
    let listener =
        Arc::try_unwrap(listener).unwrap_or_else(|_| panic!("accept task retained listener"));
    listener.close().await.expect("listener drained");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn closing_accepted_connection_does_not_wait_for_active_sibling() {
    let pki = support::TestPki::generate();
    let listener = TransportListener::bind(
        build_server_config(destination_policy(), pki.destination_material()).unwrap(),
        "127.0.0.1:0".parse().unwrap(),
    )
    .unwrap();
    let remote = listener.local_addr().unwrap();
    let (destination_a, source_a) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy(), pki.source_material()).unwrap(),
            remote
        )
    );
    let (destination_b, source_b) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy(), pki.source_material()).unwrap(),
            remote
        )
    );
    let (destination_a, source_a) = (destination_a.unwrap(), source_a.unwrap());
    let (destination_b, source_b) = (destination_b.unwrap(), source_b.unwrap());
    assert_eq!(
        destination_b.authenticated_peer().as_str(),
        "source-edge.test"
    );
    assert_eq!(
        source_b.authenticated_peer().as_str(),
        "destination-edge.test"
    );
    let close_a = destination_a.close().await;
    // Peer B must remain usable after A closes; do not merely check cached identity.
    let fixture = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/core-v0.2/artifacts/valid/envelopes/client-hello.cbor"),
    )
    .unwrap();
    let envelope =
        nbsr_transport::decode_control_envelope(&fixture, nbsr_transport::CoreV02Limits::default())
            .unwrap();
    let (received, sent) = tokio::time::timeout(Duration::from_secs(2), async {
        tokio::join!(
            async {
                let mut stream = destination_b.accept_control_stream().await.unwrap();
                stream
                    .receive_envelope(nbsr_transport::CoreV02Limits::default())
                    .await
                    .unwrap()
            },
            async {
                let mut stream = source_b.open_control_stream().await.unwrap();
                stream.send_envelope(&envelope).await.unwrap()
            }
        )
    })
    .await
    .expect("sibling B still exchanges authenticated control data");
    assert_eq!(sent, ());
    assert_eq!(
        received.message_type(),
        nbsr_transport::CoreV02MessageType::ClientHello
    );
    source_a.close().await.expect("owned endpoint A drained");
    source_b.close().await.expect("owned endpoint B drained");
    destination_b
        .close()
        .await
        .expect("accepted connection B closed");
    listener.close().await.expect("shared listener drained");
    assert_eq!(
        close_a,
        Ok(()),
        "closing A must not wait for unrelated active B"
    );
}
