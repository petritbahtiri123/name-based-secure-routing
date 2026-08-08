use std::env;
use std::fs;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use quinn::crypto::rustls::{QuicClientConfig, QuicServerConfig};
use quinn::{ClientConfig, Connection, Endpoint, ServerConfig, TransportConfig, VarInt};
use rustls::client::Resumption;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use rustls::server::WebPkiClientVerifier;
use rustls::{RootCertStore, version};
use x509_parser::extensions::GeneralName;
use x509_parser::prelude::{FromDer, X509Certificate};

const ALPN: &[u8] = b"nbsr-quic-1";
const MAX_PAYLOAD: usize = 1_048_576;

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

fn material(
    authority: &Path,
    stem: &str,
) -> (
    Vec<CertificateDer<'static>>,
    PrivateKeyDer<'static>,
    RootCertStore,
) {
    let ca = CertificateDer::from(fs::read(authority.join("ca.der")).unwrap());
    let certificate =
        CertificateDer::from(fs::read(authority.join(format!("{stem}.der"))).unwrap());
    let key = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(
        fs::read(authority.join(format!("{stem}-key.der"))).unwrap(),
    ));
    let mut roots = RootCertStore::empty();
    roots.add(ca).unwrap();
    (vec![certificate], key, roots)
}

fn transport() -> Arc<TransportConfig> {
    let mut value = TransportConfig::default();
    value.max_idle_timeout(Some(Duration::from_secs(30).try_into().unwrap()));
    value.max_concurrent_bidi_streams(VarInt::from_u32(2_049));
    value.max_concurrent_uni_streams(VarInt::from_u32(0));
    Arc::new(value)
}

fn server_config(authority: &Path) -> ServerConfig {
    let (certificates, key, roots) = material(authority, "destination");
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let verifier =
        WebPkiClientVerifier::builder_with_provider(Arc::new(roots), Arc::clone(&provider))
            .build()
            .unwrap();
    let mut tls = rustls::ServerConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .unwrap()
        .with_client_cert_verifier(verifier)
        .with_single_cert(certificates, key)
        .unwrap();
    tls.alpn_protocols = vec![ALPN.to_vec()];
    tls.max_early_data_size = 0;
    let mut config = ServerConfig::with_crypto(Arc::new(QuicServerConfig::try_from(tls).unwrap()));
    config.transport = transport();
    config
}

fn client_config(authority: &Path) -> ClientConfig {
    let (certificates, key, roots) = material(authority, "source");
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let mut tls = rustls::ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .unwrap()
        .with_root_certificates(roots)
        .with_client_auth_cert(certificates, key)
        .unwrap();
    tls.alpn_protocols = vec![ALPN.to_vec()];
    tls.enable_early_data = false;
    tls.resumption = Resumption::disabled();
    let mut config = ClientConfig::new(Arc::new(QuicClientConfig::try_from(tls).unwrap()));
    config.transport_config(transport());
    config
}

fn authenticate(connection: &Connection, expected: &str) {
    let handshake = connection
        .handshake_data()
        .unwrap()
        .downcast::<quinn::crypto::rustls::HandshakeData>()
        .unwrap();
    assert_eq!(handshake.protocol.as_deref(), Some(ALPN));
    let identity = connection
        .peer_identity()
        .unwrap()
        .downcast::<Vec<CertificateDer<'static>>>()
        .unwrap();
    let (_, certificate) = X509Certificate::from_der(identity[0].as_ref()).unwrap();
    let names = certificate
        .subject_alternative_name()
        .unwrap()
        .unwrap()
        .value
        .general_names
        .iter()
        .filter_map(|name| match name {
            GeneralName::DNSName(value) => Some(*value),
            _ => None,
        })
        .collect::<Vec<_>>();
    assert_eq!(names, [expected]);
}

async fn accept_connection(endpoint: &Endpoint) -> Connection {
    let connection = endpoint.accept().await.unwrap().await.unwrap();
    authenticate(&connection, "source.edge");
    connection
}

async fn connect(authority: &Path, remote: SocketAddr) -> (Endpoint, Connection) {
    let mut endpoint =
        Endpoint::client(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0)).unwrap();
    endpoint.set_default_client_config(client_config(authority));
    let connection = endpoint
        .connect(remote, "destination.edge")
        .unwrap()
        .await
        .unwrap();
    authenticate(&connection, "destination.edge");
    (endpoint, connection)
}

async fn echo(connection: &Connection) {
    let (mut send, mut receive) = connection.accept_bi().await.unwrap();
    let payload = receive.read_to_end(MAX_PAYLOAD).await.unwrap();
    send.write_all(&payload).await.unwrap();
    send.finish().unwrap();
}

async fn request(connection: &Connection, payload: &[u8]) -> Vec<u8> {
    let (mut send, mut receive) = connection.open_bi().await.unwrap();
    send.write_all(payload).await.unwrap();
    send.finish().unwrap();
    receive.read_to_end(MAX_PAYLOAD).await.unwrap()
}

async fn server() {
    let ready = PathBuf::from(argument("--ready"));
    let authority = PathBuf::from(argument("--authority-dir"));
    let connections = count("--connections");
    let requests = count("--requests-per-connection");
    let endpoint = Endpoint::server(
        server_config(&authority),
        SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
    )
    .unwrap();
    let address = endpoint.local_addr().unwrap();
    fs::write(ready, format!("{{\"alpn\":\"nbsr-quic-1\",\"endpoint\":\"{address}\",\"mode\":\"direct-quic\",\"zero_rtt\":false}}")).unwrap();
    for _ in 0..connections {
        let connection = accept_connection(&endpoint).await;
        for _ in 0..requests {
            echo(&connection).await;
        }
        connection.closed().await;
    }
    endpoint.close(VarInt::from_u32(0), b"");
    endpoint.wait_idle().await;
}

async fn client() {
    let authority = PathBuf::from(argument("--authority-dir"));
    let remote: SocketAddr = argument("--endpoint").parse().unwrap();
    let samples = count("--samples");
    let payload_bytes = count("--payload-bytes");
    let lifecycle = argument("--lifecycle");
    assert!(matches!(lifecycle.as_str(), "cold" | "warm"));
    assert!((1..=MAX_PAYLOAD).contains(&payload_bytes));
    let payload = vec![0x5a; payload_bytes];
    let mut warm: Option<(Endpoint, Connection)> = None;
    let mut records = Vec::with_capacity(samples);
    for sample_id in 0..samples {
        let total = Instant::now();
        let handshake = Instant::now();
        let pair = if lifecycle == "cold" || warm.is_none() {
            connect(&authority, remote).await
        } else {
            warm.take().unwrap()
        };
        let handshake_ns = if lifecycle == "cold" || sample_id == 0 {
            Some(handshake.elapsed().as_nanos())
        } else {
            None
        };
        let started = Instant::now();
        let response = request(&pair.1, &payload).await;
        let request_ns = started.elapsed().as_nanos();
        assert_eq!(response, payload);
        records.push(format!("{{\"sample_id\":{sample_id},\"success\":true,\"transport_handshake_ns\":{},\"request_latency_ns\":{request_ns},\"ttfab_ns\":{request_ns},\"total_scenario_ns\":{},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}", handshake_ns.map_or_else(|| "null".into(), |value| value.to_string()), total.elapsed().as_nanos()));
        if lifecycle == "cold" {
            pair.1.close(VarInt::from_u32(0), b"");
            pair.0.wait_idle().await;
        } else {
            warm = Some(pair);
        }
    }
    if let Some((endpoint, connection)) = warm {
        connection.close(VarInt::from_u32(0), b"");
        endpoint.wait_idle().await;
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
