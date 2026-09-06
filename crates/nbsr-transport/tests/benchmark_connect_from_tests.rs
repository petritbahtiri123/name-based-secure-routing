//! Explicit benchmark bind keeps the authenticated transport boundary intact.
#![cfg(feature = "benchmark-harness")]
use nbsr_transport::{
    ALPN, EdgeIdentity, EdgeRole, PeerPolicy, ServiceChannelContext, TransportError,
    TransportListener, benchmark_connect_from, build_client_config, build_server_config,
};
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4};
use std::time::Duration;
mod support;

fn policy(local: EdgeRole, remote: EdgeRole, expected: &str) -> PeerPolicy {
    PeerPolicy::new(
        local,
        remote,
        EdgeIdentity::from_dns_name(expected).unwrap(),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn explicit_local_bind_preserves_expected_tls_identity_and_alpn() {
    let pki = support::TestPki::generate();
    let listener = TransportListener::bind(
        build_server_config(
            policy(EdgeRole::Destination, EdgeRole::Source, "source-edge.test"),
            pki.destination_material(),
        )
        .unwrap(),
        SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
    )
    .unwrap();
    let (source, destination) = tokio::join!(
        benchmark_connect_from(
            build_client_config(
                policy(
                    EdgeRole::Source,
                    EdgeRole::Destination,
                    "destination-edge.test"
                ),
                pki.source_material()
            )
            .unwrap(),
            listener.local_addr().unwrap(),
            SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
        ),
        listener.accept_one()
    );
    let source = source.unwrap();
    let destination = destination.unwrap();
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
    let context = ServiceChannelContext {
        session_id: [0x10; 16],
        source_edge_id: "source-edge.test",
        destination_edge_id: "destination-edge.test",
        channel_id: [0x40; 16],
        route_id: [0x20; 16],
        route_grant_digest: [0x50; 32],
        service_id: "service.example",
        transport: "tcp",
        port: 8443,
        policy_hash: [0x60; 32],
        client_nonce: [0x70; 32],
        edge_nonce: [0x80; 32],
    };
    assert_eq!(
        source.export_channel_binding(&context).unwrap(),
        destination.export_channel_binding(&context).unwrap()
    );
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test]
async fn transport_entry_validates_local_bind_without_trusting_the_cli() {
    let pki = support::TestPki::generate();
    for local in [
        "0.0.0.0:0",
        "224.0.0.1:0",
        "255.255.255.255:0",
        "127.0.0.1:4444",
    ] {
        let result = benchmark_connect_from(
            build_client_config(
                policy(
                    EdgeRole::Source,
                    EdgeRole::Destination,
                    "destination-edge.test",
                ),
                pki.source_material(),
            )
            .unwrap(),
            "127.0.0.1:9".parse().unwrap(),
            local.parse().unwrap(),
        )
        .await;
        assert!(matches!(result, Err(TransportError::BindFailed)), "{local}");
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn explicit_local_bind_rejects_alpn_mismatch() {
    let pki = support::TestPki::generate();
    let endpoint = quinn::Endpoint::server(
        pki.server_config_with_alpn(b"not-nbsr"),
        SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
    )
    .unwrap();
    let (destination, source) = tokio::join!(
        async { endpoint.accept().await.unwrap().await },
        benchmark_connect_from(
            build_client_config(
                policy(
                    EdgeRole::Source,
                    EdgeRole::Destination,
                    "destination-edge.test"
                ),
                pki.source_material()
            )
            .unwrap(),
            endpoint.local_addr().unwrap(),
            SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
        )
    );
    assert!(source.is_err());
    if let Ok(destination) = destination {
        destination.close(quinn::VarInt::from_u32(0), b"");
    }
    endpoint.close(quinn::VarInt::from_u32(0), b"");
    endpoint.wait_idle().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn explicit_local_bind_does_not_replace_the_authenticated_peer_name_with_ip() {
    let pki = support::TestPki::generate();
    let listener = TransportListener::bind(
        build_server_config(
            policy(EdgeRole::Destination, EdgeRole::Source, "source-edge.test"),
            pki.destination_material(),
        )
        .unwrap(),
        SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
    )
    .unwrap();
    let (source, destination) = tokio::join!(
        benchmark_connect_from(
            build_client_config(
                policy(
                    EdgeRole::Source,
                    EdgeRole::Destination,
                    "wrong-destination.test"
                ),
                pki.source_material()
            )
            .unwrap(),
            listener.local_addr().unwrap(),
            SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
        ),
        listener.accept_one()
    );
    assert!(source.is_err());
    if let Ok(destination) = destination {
        destination.close().await.unwrap();
    }
    listener.close().await.unwrap();
}
