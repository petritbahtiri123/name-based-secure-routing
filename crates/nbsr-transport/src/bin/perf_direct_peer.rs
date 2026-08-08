use std::env;
use std::fs;
use std::net::{Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use nbsr_transport::{
    EdgeIdentity, EdgeRole, PeerPolicy, TlsMaterial, TransportListener, build_client_config,
    build_server_config, connect,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};

fn argument(name: &str) -> String {
    let values = env::args().collect::<Vec<_>>();
    let index = values
        .iter()
        .position(|value| value == name)
        .unwrap_or_else(|| panic!("missing {name}"));
    values
        .get(index + 1)
        .unwrap_or_else(|| panic!("missing value for {name}"))
        .clone()
}

fn count(name: &str) -> usize {
    argument(name)
        .parse()
        .unwrap_or_else(|_| panic!("invalid {name}"))
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).unwrap()
}

fn tls_material(authority: &Path, stem: &str) -> TlsMaterial {
    let ca = CertificateDer::from(fs::read(authority.join("ca.der")).unwrap());
    let certificate =
        CertificateDer::from(fs::read(authority.join(format!("{stem}.der"))).unwrap());
    let key = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(
        fs::read(authority.join(format!("{stem}-key.der"))).unwrap(),
    ));
    let mut roots = RootCertStore::empty();
    roots.add(ca).unwrap();
    TlsMaterial::new(vec![certificate], key, roots).unwrap()
}

fn policy(local: EdgeRole) -> PeerPolicy {
    let (peer_role, peer) = match local {
        EdgeRole::Source => (EdgeRole::Destination, "destination.edge"),
        EdgeRole::Destination => (EdgeRole::Source, "source.edge"),
    };
    PeerPolicy::new(
        local,
        peer_role,
        identity(peer),
        Duration::from_secs(5),
        Duration::from_secs(30),
    )
    .unwrap()
}

async fn server() {
    let ready = PathBuf::from(argument("--ready"));
    let authority = PathBuf::from(argument("--authority-dir"));
    let connections = count("--connections");
    let requests = count("--requests-per-connection");
    let listener = TransportListener::bind(
        build_server_config(
            policy(EdgeRole::Destination),
            tls_material(&authority, "destination"),
        )
        .unwrap(),
        SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
    )
    .unwrap();
    let endpoint = listener.local_addr().unwrap();
    fs::write(
        ready,
        format!(
            "{{\"alpn\":\"nbsr-quic-1\",\"endpoint\":\"{endpoint}\",\"mode\":\"direct-quic\",\"zero_rtt\":false}}"
        ),
    )
    .unwrap();
    for _ in 0..connections {
        let connection = listener.accept_one().await.unwrap();
        for _ in 0..requests {
            connection.accept_direct_benchmark_echo().await.unwrap();
        }
        connection.close().await.unwrap();
    }
    listener.close().await.unwrap();
}

async fn client() {
    let authority = PathBuf::from(argument("--authority-dir"));
    let endpoint: SocketAddr = argument("--endpoint").parse().unwrap();
    let samples = count("--samples");
    let payload_bytes = count("--payload-bytes");
    let lifecycle = argument("--lifecycle");
    assert!(matches!(lifecycle.as_str(), "cold" | "warm"));
    assert!((1..=1_048_576).contains(&payload_bytes));
    let payload = vec![0x5a; payload_bytes];
    let mut warm = None;
    let mut records = Vec::with_capacity(samples);
    for sample_id in 0..samples {
        let scenario_started = Instant::now();
        let handshake_started = Instant::now();
        let connection = if lifecycle == "cold" || warm.is_none() {
            connect(
                build_client_config(policy(EdgeRole::Source), tls_material(&authority, "source"))
                    .unwrap(),
                endpoint,
            )
            .await
            .unwrap()
        } else {
            warm.take().unwrap()
        };
        let handshake_ns = if lifecycle == "cold" || sample_id == 0 {
            Some(handshake_started.elapsed().as_nanos())
        } else {
            None
        };
        let request_started = Instant::now();
        let response = connection.direct_benchmark_request(&payload).await.unwrap();
        let request_ns = request_started.elapsed().as_nanos();
        assert_eq!(response, payload);
        records.push(format!(
            "{{\"sample_id\":{sample_id},\"success\":true,\"transport_handshake_ns\":{},\"request_latency_ns\":{request_ns},\"ttfab_ns\":{request_ns},\"total_scenario_ns\":{},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}",
            handshake_ns.map_or_else(|| "null".to_string(), |value| value.to_string()),
            scenario_started.elapsed().as_nanos(),
        ));
        if lifecycle == "cold" {
            connection.close().await.unwrap();
        } else {
            warm = Some(connection);
        }
    }
    if let Some(connection) = warm {
        connection.close().await.unwrap();
    }
    for record in records {
        println!("{record}");
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    match argument("--role").as_str() {
        "server" => server().await,
        "client" => client().await,
        other => panic!("unsupported role {other}"),
    }
}
