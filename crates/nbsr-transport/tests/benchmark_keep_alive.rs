//! A distinct keepalive workload preserves ordinary idle expiry and TLS identity.
#![cfg(feature = "benchmark-harness")]

use nbsr_transport::{
    ALPN, EdgeIdentity, EdgeRole, PeerPolicy, TransportError, TransportListener,
    build_client_config, build_server_config, connect,
};
use std::net::{Ipv4Addr, SocketAddr};
use std::time::Duration;
mod support;

fn policy(local: EdgeRole, remote: EdgeRole, name: &str) -> PeerPolicy {
    PeerPolicy::new(
        local,
        remote,
        EdgeIdentity::from_dns_name(name).unwrap(),
        Duration::from_secs(2),
        Duration::from_millis(400),
    )
    .unwrap()
}

async fn held_pair(keep_alive: bool) {
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
    let mut client = build_client_config(
        policy(
            EdgeRole::Source,
            EdgeRole::Destination,
            "destination-edge.test",
        ),
        pki.source_material(),
    )
    .unwrap();
    let original_policy = format!("{client:?}");
    if keep_alive {
        client = client
            .with_benchmark_keep_alive(Duration::from_millis(50))
            .unwrap();
    }
    assert_eq!(format!("{client:?}"), original_policy);
    let (source, destination) = tokio::join!(
        connect(client, listener.local_addr().unwrap()),
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
    tokio::time::sleep(Duration::from_millis(1200)).await;
    let expected = if keep_alive {
        "not_closed"
    } else {
        "timed_out"
    };
    assert_eq!(source.benchmark_close_reason_category(), expected);
    assert_eq!(destination.benchmark_close_reason_category(), expected);
    if keep_alive {
        source.close().await.unwrap();
        destination.close().await.unwrap();
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn default_idle_connection_still_expires() {
    held_pair(false).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn explicit_keep_alive_retains_authenticated_connection() {
    held_pair(true).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn keep_alive_does_not_accept_wrong_destination_identity() {
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
    let address = listener.local_addr().unwrap();
    let accepting = tokio::spawn(async move { listener.accept_one().await });
    let client = build_client_config(
        policy(EdgeRole::Source, EdgeRole::Destination, "wrong-edge.test"),
        pki.source_material(),
    )
    .unwrap()
    .with_benchmark_keep_alive(Duration::from_millis(50))
    .unwrap();
    let result = connect(client, address).await;
    accepting.abort();
    let _ = accepting.await;
    assert!(
        result.is_err(),
        "keepalive must not bypass expected peer identity"
    );
}

#[test]
fn rejects_zero_or_idle_length_keep_alive() {
    let pki = support::TestPki::generate();
    for interval in [
        Duration::ZERO,
        Duration::from_millis(400),
        Duration::from_secs(1),
    ] {
        let client = build_client_config(
            policy(
                EdgeRole::Source,
                EdgeRole::Destination,
                "destination-edge.test",
            ),
            pki.source_material(),
        )
        .unwrap();
        assert!(matches!(
            client.with_benchmark_keep_alive(interval),
            Err(TransportError::InvalidTimeout)
        ));
    }
}
