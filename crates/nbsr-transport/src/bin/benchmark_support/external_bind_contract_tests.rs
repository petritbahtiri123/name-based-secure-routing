//! Benchmark socket argument contracts; no interface sockets are opened here.
use super::external_bind::{client_bind, listener_bind};
use std::net::{Ipv4Addr, SocketAddrV4};

fn arguments(values: &[&str]) -> Vec<String> {
    values.iter().map(|v| (*v).to_owned()).collect()
}

#[test]
fn absent_options_preserve_loopback_and_legacy_capture_port() {
    assert_eq!(
        client_bind(arguments(&["source"])).unwrap(),
        SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
    );
    assert_eq!(
        listener_bind(arguments(&["server"]), None).unwrap(),
        SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
    );
    assert_eq!(
        listener_bind(arguments(&["server"]), Some("31337")).unwrap(),
        SocketAddrV4::new(Ipv4Addr::LOCALHOST, 31337)
    );
    assert_eq!(
        listener_bind(arguments(&["server"]), Some("0")).unwrap(),
        SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
    );
}

#[test]
fn explicit_concrete_ipv4_source_uses_only_ephemeral_port() {
    assert_eq!(
        client_bind(arguments(&[
            "source",
            "--benchmark-client-bind",
            "192.0.2.10:0"
        ]))
        .unwrap(),
        SocketAddrV4::new(Ipv4Addr::new(192, 0, 2, 10), 0)
    );
    assert_eq!(
        client_bind(arguments(&["--benchmark-client-bind", "127.0.0.1:0"])).unwrap(),
        SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)
    );
    assert!(client_bind(arguments(&["--benchmark-client-bind", "192.0.2.10:4444"])).is_err());
}

#[test]
fn explicit_listener_accepts_concrete_ipv4_and_fixed_or_ephemeral_port() {
    assert_eq!(
        listener_bind(
            arguments(&["server", "--benchmark-listen", "192.0.2.20:4444"]),
            None
        )
        .unwrap(),
        SocketAddrV4::new(Ipv4Addr::new(192, 0, 2, 20), 4444)
    );
    assert_eq!(
        listener_bind(arguments(&["--benchmark-listen", "192.0.2.20:0"]), None).unwrap(),
        SocketAddrV4::new(Ipv4Addr::new(192, 0, 2, 20), 0)
    );
}

#[test]
fn ipv6_multicast_unspecified_and_limited_broadcast_are_rejected() {
    for ip in [
        "[::1]",
        "[::]",
        "[::ffff:192.0.2.10]",
        "224.0.0.1",
        "239.255.255.255",
        "0.0.0.0",
        "255.255.255.255",
    ] {
        assert!(
            client_bind(arguments(&["--benchmark-client-bind", &format!("{ip}:0")])).is_err(),
            "{ip}"
        );
        assert!(
            listener_bind(
                arguments(&["--benchmark-listen", &format!("{ip}:4444")]),
                None
            )
            .is_err(),
            "{ip}"
        );
    }
}

#[test]
fn duplicate_missing_or_malformed_options_are_not_silently_ignored() {
    for value in [
        "",
        "192.0.2.1",
        "destination.edge:0",
        "192.0.2.1:-1",
        "192.0.2.1:65536",
        " 192.0.2.1:0",
    ] {
        assert!(client_bind(arguments(&["--benchmark-client-bind", value])).is_err());
        assert!(listener_bind(arguments(&["--benchmark-listen", value]), None).is_err());
    }
    assert!(client_bind(arguments(&["--benchmark-client-bind"])).is_err());
    assert!(listener_bind(arguments(&["--benchmark-listen"]), None).is_err());
    assert!(
        client_bind(arguments(&[
            "--benchmark-client-bind",
            "192.0.2.1:0",
            "--benchmark-client-bind",
            "192.0.2.1:0"
        ]))
        .is_err()
    );
    assert!(
        listener_bind(
            arguments(&[
                "--benchmark-listen",
                "192.0.2.1:4444",
                "--benchmark-listen",
                "192.0.2.1:4444"
            ]),
            None
        )
        .is_err()
    );
}

#[test]
fn explicit_listener_and_any_capture_override_conflict_even_if_equal() {
    for legacy in ["0", "4444", "invalid"] {
        assert!(
            listener_bind(
                arguments(&["--benchmark-listen", "127.0.0.1:4444"]),
                Some(legacy)
            )
            .is_err()
        );
    }
    assert!(listener_bind(arguments(&[]), Some("65536")).is_err());
    assert!(listener_bind(arguments(&[]), Some("invalid")).is_err());
}

#[test]
fn role_specific_bind_options_cannot_be_silently_ignored() {
    assert!(client_bind(arguments(&["--benchmark-listen", "192.0.2.1:4444"])).is_err());
    assert!(listener_bind(arguments(&["--benchmark-client-bind", "192.0.2.1:0"]), None).is_err());
    // Unrelated established arguments remain the owning CLI's responsibility.
    assert_eq!(
        client_bind(arguments(&["--endpoint", "192.0.2.20:4444"]))
            .unwrap()
            .ip(),
        &Ipv4Addr::LOCALHOST
    );
}
