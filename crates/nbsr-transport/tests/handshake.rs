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
