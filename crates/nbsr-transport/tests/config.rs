use std::time::Duration;

use nbsr_transport::{
    EdgeIdentity, EdgeRole, PeerPolicy, TlsMaterial, TransportError, build_client_config,
    build_server_config,
};
use rustls::RootCertStore;
use rustls::pki_types::{PrivateKeyDer, PrivatePkcs8KeyDer};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("valid test identity")
}

#[test]
fn rejects_same_role_peer_before_socket_creation() {
    let error = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect_err("same-role policy must fail");

    assert_eq!(error, TransportError::InvalidPeerRole);
}

#[test]
fn rejects_invalid_or_ip_peer_identity() {
    assert_eq!(
        EdgeIdentity::from_dns_name("not a dns name").unwrap_err(),
        TransportError::InvalidPeerIdentity
    );
    assert_eq!(
        EdgeIdentity::from_dns_name("127.0.0.1").unwrap_err(),
        TransportError::InvalidPeerIdentity
    );
}

#[test]
fn rejects_zero_handshake_timeout() {
    let error = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination-edge.test"),
        Duration::ZERO,
        Duration::from_secs(5),
    )
    .expect_err("zero handshake timeout must fail");

    assert_eq!(error, TransportError::InvalidTimeout);
}

#[test]
fn rejects_zero_idle_timeout() {
    let error = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::ZERO,
    )
    .expect_err("zero idle timeout must fail");

    assert_eq!(error, TransportError::InvalidTimeout);
}

#[test]
fn accepts_complementary_edge_roles() {
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");

    assert_eq!(source_policy.local_role(), EdgeRole::Source);
    assert_eq!(source_policy.expected_peer_role(), EdgeRole::Destination);
    assert_eq!(
        source_policy.expected_peer().as_str(),
        "destination-edge.test"
    );
    assert_eq!(destination_policy.local_role(), EdgeRole::Destination);
    assert_eq!(destination_policy.expected_peer_role(), EdgeRole::Source);
    assert_eq!(
        destination_policy.expected_peer().as_str(),
        "source-edge.test"
    );
}

#[test]
fn builds_mutual_tls_client_and_server_configuration() {
    let pki = support::TestPki::generate();

    build_client_config(
        PeerPolicy::new(
            EdgeRole::Source,
            EdgeRole::Destination,
            identity("destination-edge.test"),
            Duration::from_secs(2),
            Duration::from_secs(5),
        )
        .unwrap(),
        pki.source_material(),
    )
    .expect("source client configuration");

    build_server_config(
        PeerPolicy::new(
            EdgeRole::Destination,
            EdgeRole::Source,
            identity("source-edge.test"),
            Duration::from_secs(2),
            Duration::from_secs(5),
        )
        .unwrap(),
        pki.destination_material(),
    )
    .expect("destination server configuration");
}

#[test]
fn rejects_endpoint_role_reversal() {
    let pki = support::TestPki::generate();
    let destination_as_client = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let source_as_server = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();

    assert_eq!(
        build_client_config(destination_as_client, pki.destination_material()).unwrap_err(),
        TransportError::InvalidEndpointRole
    );
    assert_eq!(
        build_server_config(source_as_server, pki.source_material()).unwrap_err(),
        TransportError::InvalidEndpointRole
    );
}

#[test]
fn rejects_empty_tls_material() {
    let error = TlsMaterial::new(
        Vec::new(),
        PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(vec![1, 2, 3])),
        RootCertStore::empty(),
    )
    .unwrap_err();

    assert_eq!(error, TransportError::InvalidTlsMaterial);
}
