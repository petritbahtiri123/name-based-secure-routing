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
        let healthy = connect(
            build_client_config(source_policy(), pki.source_material()).unwrap(),
            remote,
        );
        tokio::pin!(healthy);
        // With only the stalled admission slot, the healthy handshake cannot
        // progress. Keep the same future alive when opening the second slot.
        assert!(
            tokio::time::timeout(Duration::from_millis(150), &mut healthy)
                .await
                .is_err(),
            "a serial accept leaves the healthy peer waiting"
        );
        assert!(!first.is_finished(), "the first admission is still stalled");
        let (destination, source) = tokio::time::timeout(Duration::from_secs(1), async {
            tokio::join!(listener.accept_one(), &mut healthy)
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

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn shared_listener_shutdown_disconnects_two_active_authenticated_peers() {
    let pki = support::TestPki::generate();
    let listener = TransportListener::bind(
        build_server_config(destination_policy(), pki.destination_material()).unwrap(),
        "127.0.0.1:0".parse().unwrap(),
    )
    .unwrap();
    let remote = listener.local_addr().unwrap();
    let fixture = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/core-v0.2/artifacts/valid/envelopes/client-hello.cbor"),
    )
    .unwrap();
    let envelope =
        nbsr_transport::decode_control_envelope(&fixture, nbsr_transport::CoreV02Limits::default())
            .unwrap();
    let mut peers = Vec::new();
    for _ in 0..2 {
        let (destination, source) = tokio::join!(
            listener.accept_one(),
            connect(
                build_client_config(source_policy(), pki.source_material()).unwrap(),
                remote
            )
        );
        let (destination, source) = (destination.unwrap(), source.unwrap());
        assert_eq!(
            destination.authenticated_peer().as_str(),
            "source-edge.test"
        );
        assert_eq!(
            source.authenticated_peer().as_str(),
            "destination-edge.test"
        );
        let (source_stream, destination_stream) =
            tokio::time::timeout(Duration::from_secs(2), async {
                tokio::join!(
                    async {
                        let mut stream = source.open_control_stream().await.unwrap();
                        stream.send_envelope(&envelope).await.unwrap();
                        stream
                    },
                    async {
                        let mut stream = destination.accept_control_stream().await.unwrap();
                        let received = stream
                            .receive_envelope(nbsr_transport::CoreV02Limits::default())
                            .await
                            .unwrap();
                        assert_eq!(
                            received.message_type(),
                            nbsr_transport::CoreV02MessageType::ClientHello
                        );
                        stream
                    }
                )
            })
            .await
            .expect("peer exchanges authenticated data before shutdown");
        peers.push((source, destination, source_stream, destination_stream));
    }
    // Keep both connection pairs and stream halves alive during endpoint-wide drain.
    let shutdown = listener.close().await;
    let mut disconnected = Vec::new();
    let mut cleanup = Vec::new();
    for (source, destination, mut source_stream, destination_stream) in peers {
        disconnected.push(
            tokio::time::timeout(
                Duration::from_secs(2),
                source_stream.receive_envelope(nbsr_transport::CoreV02Limits::default()),
            )
            .await,
        );
        drop(source_stream);
        drop(destination_stream);
        cleanup.push(source.close().await);
        cleanup.push(destination.close().await);
    }
    assert_eq!(
        shutdown,
        Ok(()),
        "shared listener drains with both peers retained"
    );
    for result in disconnected {
        assert!(
            matches!(result, Ok(Err(TransportError::ControlStreamFailed))),
            "peer must observe listener shutdown: {result:?}"
        );
    }
    for result in cleanup {
        assert_eq!(result, Ok(()), "connection cleanup drains");
    }
}

#[cfg(feature = "benchmark-harness")]
#[path = "../src/bin/benchmark_support/lifecycle_teardown.rs"]
mod lifecycle_teardown;

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn lifecycle_teardown_keeps_source_alive_for_delayed_response_ack() {
    use std::sync::{
        Arc,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    };
    let pki = support::TestPki::generate();
    let endpoint = Endpoint::server(
        pki.server_config_with_alpn(ALPN),
        "127.0.0.1:0".parse().unwrap(),
    )
    .unwrap();
    let remote = endpoint.local_addr().unwrap();
    let relay = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
    relay
        .set_read_timeout(Some(Duration::from_millis(10)))
        .unwrap();
    let address = relay.local_addr().unwrap();
    let blocked = Arc::new(AtomicBool::new(false));
    let stopped = Arc::new(AtomicBool::new(false));
    let discarded = Arc::new(AtomicUsize::new(0));
    let (gate, stop, drops) = (blocked.clone(), stopped.clone(), discarded.clone());
    let worker = std::thread::spawn(move || {
        let mut client = None;
        let mut bytes = [0; 65536];
        while !stop.load(Ordering::SeqCst) {
            match relay.recv_from(&mut bytes) {
                Ok((size, sender)) if sender == remote => {
                    if let Some(client) = client {
                        relay.send_to(&bytes[..size], client).unwrap();
                    }
                }
                Ok((size, sender)) => {
                    client = Some(sender);
                    if gate.load(Ordering::SeqCst) {
                        drops.fetch_add(1, Ordering::SeqCst);
                    } else {
                        relay.send_to(&bytes[..size], remote).unwrap();
                    }
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::WouldBlock
                            | std::io::ErrorKind::TimedOut
                            | std::io::ErrorKind::ConnectionReset
                            | std::io::ErrorKind::ConnectionRefused
                    ) => {}
                Err(e) => panic!("relay: {e}"),
            }
        }
    });
    struct RelayGuard(Arc<AtomicBool>, Option<std::thread::JoinHandle<()>>);
    impl Drop for RelayGuard {
        fn drop(&mut self) {
            self.0.store(true, Ordering::SeqCst);
            self.1.take().unwrap().join().unwrap();
        }
    }
    let guard = RelayGuard(stopped, Some(worker));
    let fixture = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/core-v0.2/artifacts/valid/envelopes/client-hello.cbor"),
    )
    .unwrap();
    let client_fixture = fixture.clone();
    let (ready_tx, ready_rx) = tokio::sync::oneshot::channel();
    let (finished_tx, mut finished_rx) = tokio::sync::oneshot::channel();
    let client_config = build_client_config(source_policy(), pki.source_material()).unwrap();
    let client_thread = std::thread::spawn(move || {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let result = runtime.block_on(async {
            tokio::time::timeout(Duration::from_secs(4), async {
                let source = connect(client_config, address).await.unwrap();
                let envelope = nbsr_transport::decode_control_envelope(
                    &client_fixture,
                    nbsr_transport::CoreV02Limits::default(),
                )
                .unwrap();
                let mut control = source.open_control_stream().await.unwrap();
                control.send_envelope(&envelope).await.unwrap();
                control
                    .receive_envelope(nbsr_transport::CoreV02Limits::default())
                    .await
                    .unwrap();
                // Read FIN, as the benchmark's receive_payload does.
                assert!(matches!(
                    control
                        .receive_envelope(nbsr_transport::CoreV02Limits::default())
                        .await,
                    Err(TransportError::ControlStreamFailed)
                ));
                drop(control);
                ready_tx.send(()).unwrap();
                lifecycle_teardown::finish(source, true).await
            })
            .await
            .expect("bounded source worker")
        });
        // Match lifecycle_shards: the runtime ends when its clients finish.
        drop(runtime);
        finished_tx.send(result).unwrap();
    });
    let server = endpoint.accept().await.unwrap().await.unwrap();
    let gate = blocked.clone();
    let destination = tokio::spawn(async move {
        let (mut send, mut receive) = server.accept_bi().await.unwrap();
        receive.read_chunk(65536, true).await.unwrap().unwrap();
        // Lose initial client ACKs, then reopen the link. A live source can
        // acknowledge retransmission; an already-dropped endpoint cannot.
        gate.store(true, Ordering::SeqCst);
        assert!((64..16384).contains(&fixture.len()));
        send.write_all(&(0x4000 | fixture.len() as u16).to_be_bytes())
            .await
            .unwrap();
        send.write_all(&fixture).await.unwrap();
        send.finish().unwrap();
        let ack = tokio::time::timeout(Duration::from_secs(1), send.stopped()).await;
        server.close(VarInt::from_u32(0), b"");
        ack
    });
    tokio::time::timeout(Duration::from_secs(2), ready_rx)
        .await
        .unwrap()
        .unwrap();
    let early = tokio::time::timeout(Duration::from_millis(100), &mut finished_rx).await;
    let returned_before_ack = early.is_ok();
    blocked.store(false, Ordering::SeqCst);
    let finished = match early {
        Ok(value) => value,
        Err(_) => tokio::time::timeout(Duration::from_secs(3), finished_rx)
            .await
            .expect("bounded source finish"),
    };
    client_thread.join().unwrap();
    let acknowledged = destination.await.unwrap();
    endpoint.close(VarInt::from_u32(0), b"");
    tokio::time::timeout(Duration::from_secs(2), endpoint.wait_idle())
        .await
        .unwrap();
    drop(guard);
    assert!(
        discarded.load(Ordering::SeqCst) > 0,
        "response ACK loss was exercised"
    );
    assert!(
        matches!(acknowledged, Ok(Ok(None))),
        "destination response must be acknowledged: {acknowledged:?}"
    );
    assert!(
        !returned_before_ack,
        "source completion must retain its endpoint until peer completion"
    );
    assert_eq!(finished.unwrap(), Ok(()));
}

#[cfg(feature = "benchmark-harness")]
async fn benchmark_teardown_pair() -> (
    Endpoint,
    quinn::Connection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate();
    let endpoint = Endpoint::server(
        pki.server_config_with_alpn(ALPN),
        "127.0.0.1:0".parse().unwrap(),
    )
    .unwrap();
    let (server, source) = tokio::join!(
        async { endpoint.accept().await.unwrap().await.unwrap() },
        connect(
            build_client_config(source_policy(), pki.source_material()).unwrap(),
            endpoint.local_addr().unwrap()
        )
    );
    (endpoint, server, source.unwrap())
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_teardown_rejects_abnormal_peer_close() {
    let (endpoint, server, source) = benchmark_teardown_pair().await;
    server.close(VarInt::from_u32(42), b"test failure");
    assert_eq!(
        source.benchmark_wait_for_peer_close().await,
        Err(TransportError::ApplicationStreamFailed)
    );
    assert_eq!(
        source.benchmark_close_reason_category(),
        "application_closed"
    );
    let result = lifecycle_teardown::finish(source, true).await;
    endpoint.close(VarInt::from_u32(0), b"");
    tokio::time::timeout(Duration::from_secs(2), endpoint.wait_idle())
        .await
        .unwrap();
    assert_eq!(result, Err(TransportError::ApplicationStreamFailed));
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_teardown_requires_peer_completion_within_existing_close_bound() {
    let (endpoint, server, source) = benchmark_teardown_pair().await;
    let result = tokio::time::timeout(
        Duration::from_secs(5),
        lifecycle_teardown::finish(source, true),
    )
    .await;
    server.close(VarInt::from_u32(0), b"");
    endpoint.close(VarInt::from_u32(0), b"");
    tokio::time::timeout(Duration::from_secs(2), endpoint.wait_idle())
        .await
        .unwrap();
    assert_eq!(result.unwrap(), Err(TransportError::CloseTimeout));
}

#[cfg(feature = "benchmark-harness")]
#[path = "../src/bin/benchmark_support/lifecycle_accept_window.rs"]
mod bounded_admission_policy;
