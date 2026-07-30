use std::time::Duration;

use nbsr_transport::{EdgeIdentity, EdgeRole, PeerPolicy, TransportError};

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
