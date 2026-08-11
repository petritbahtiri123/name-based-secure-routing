use std::env;
use std::fs;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[cfg(feature = "benchmark-harness")]
use nbsr_transport::p2a_benchmark::{decode_frame, encode_frame};
use quinn::crypto::rustls::{QuicClientConfig, QuicServerConfig};
use quinn::{ClientConfig, Connection, Endpoint, ServerConfig, TransportConfig, VarInt};
use rustls::client::Resumption;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use rustls::server::WebPkiClientVerifier;
use rustls::{RootCertStore, version};
#[cfg(feature = "benchmark-harness")]
use tokio::sync::Barrier;
#[cfg(feature = "benchmark-harness")]
use tokio::task::JoinSet;
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

fn optional_argument(name: &str) -> Option<String> {
    let values = env::args().collect::<Vec<_>>();
    values
        .iter()
        .position(|value| value == name)
        .map(|index| values[index + 1].clone())
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

#[cfg(feature = "benchmark-harness")]
async fn write_frame(send: &mut quinn::SendStream, wire: &[u8]) -> Result<(), ()> {
    send.write_all(&(wire.len() as u32).to_be_bytes())
        .await
        .map_err(|_| ())?;
    send.write_all(wire).await.map_err(|_| ())
}

#[cfg(feature = "benchmark-harness")]
async fn read_frame(receive: &mut quinn::RecvStream) -> Result<Vec<u8>, ()> {
    let mut length = [0_u8; 4];
    receive.read_exact(&mut length).await.map_err(|_| ())?;
    let mut wire = vec![0_u8; u32::from_be_bytes(length) as usize];
    receive.read_exact(&mut wire).await.map_err(|_| ())?;
    Ok(wire)
}

async fn wait_until(deadline: Instant) {
    loop {
        let now = Instant::now();
        if now >= deadline {
            return;
        }
        let remaining = deadline - now;
        if remaining > Duration::from_millis(20) {
            tokio::time::sleep(remaining - Duration::from_millis(20)).await;
        } else {
            std::hint::spin_loop();
        }
    }
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
    #[cfg(feature = "benchmark-harness")]
    if let Some(stream_count) = optional_argument("--p2a-streams") {
        let stream_count = stream_count.parse::<usize>().unwrap();
        let connection = accept_connection(&endpoint).await;
        let mut tasks = JoinSet::new();
        for _ in 0..stream_count {
            let (mut send, mut receive) = connection.accept_bi().await.unwrap();
            tasks.spawn(async move {
                while let Ok(wire) = read_frame(&mut receive).await {
                    if write_frame(&mut send, &wire).await.is_err() {
                        break;
                    }
                }
            });
        }
        while tasks.join_next().await.is_some() {}
        endpoint.close(VarInt::from_u32(0), b"");
        endpoint.wait_idle().await;
        return;
    }
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
    let offered_rate =
        optional_argument("--offered-rate").map(|value| value.parse::<f64>().unwrap());
    let connected_marker = optional_argument("--connected-marker").map(PathBuf::from);
    #[cfg(feature = "benchmark-harness")]
    if let Some(stream_count) = optional_argument("--p2a-streams") {
        let stream_count = stream_count.parse::<usize>().unwrap();
        let warmup = Duration::from_secs_f64(argument("--p2a-warmup-seconds").parse().unwrap());
        let duration = Duration::from_secs_f64(argument("--p2a-duration-seconds").parse().unwrap());
        let payload = vec![0x5a; payload_bytes];
        let (endpoint, connection) = connect(&authority, remote).await;
        let mut streams = Vec::with_capacity(stream_count);
        for _ in 0..stream_count {
            streams.push(connection.open_bi().await.unwrap());
        }
        let ready = Arc::new(Barrier::new(stream_count + 1));
        let measure = Arc::new(Barrier::new(stream_count + 1));
        let warmup_deadline = Instant::now() + warmup;
        let mut tasks = JoinSet::new();
        for (ordinal, (mut send, mut receive)) in streams.into_iter().enumerate() {
            let ready = Arc::clone(&ready);
            let measure = Arc::clone(&measure);
            let payload = payload.clone();
            tasks.spawn(async move {
                let mut sequence = (ordinal as u64) << 56;
                while Instant::now() < warmup_deadline {
                    let wire = encode_frame(sequence, &payload);
                    write_frame(&mut send, &wire).await.unwrap();
                    let response = read_frame(&mut receive).await.unwrap();
                    decode_frame(&response, sequence, payload.len()).unwrap();
                    sequence += 1;
                }
                ready.wait().await;
                measure.wait().await;
                let deadline = Instant::now() + duration;
                let mut completed = 0_u64;
                let mut latencies = Vec::new();
                while Instant::now() < deadline {
                    let started = Instant::now();
                    let wire = encode_frame(sequence, &payload);
                    write_frame(&mut send, &wire).await.unwrap();
                    let response = read_frame(&mut receive).await.unwrap();
                    decode_frame(&response, sequence, payload.len()).unwrap();
                    latencies.push(started.elapsed().as_nanos() as u64);
                    completed += 1;
                    sequence += 1;
                }
                send.finish().unwrap();
                (completed, latencies)
            });
        }
        ready.wait().await;
        let measured_started = Instant::now();
        measure.wait().await;
        let mut completed = 0_u64;
        let mut latencies = Vec::new();
        while let Some(joined) = tasks.join_next().await {
            let (count, mut values) = joined.unwrap();
            completed += count;
            latencies.append(&mut values);
        }
        let measured_ns = measured_started.elapsed().as_nanos();
        latencies.sort_unstable();
        let percentile = |p: f64| latencies[((latencies.len() - 1) as f64 * p).round() as usize];
        println!(
            "{{\"schema\":\"nbsr-p2a-repeat-v1\",\"path\":\"direct\",\"streams\":{stream_count},\"payload_bytes\":{payload_bytes},\"model\":\"one-outstanding-per-stream\",\"completed_operations\":{completed},\"measured_ns\":{measured_ns},\"p50_latency_ns\":{},\"p95_latency_ns\":{},\"p99_latency_ns\":{},\"errors\":0,\"missing\":0,\"duplicates\":0,\"corrupt\":0,\"wrong_request\":0,\"transport_sessions_created_delta\":0,\"service_channels_created_delta\":0,\"application_streams_created_delta\":0,\"replay_entries_delta\":0}}",
            percentile(0.50),
            percentile(0.95),
            percentile(0.99)
        );
        connection.close(VarInt::from_u32(0), b"");
        endpoint.wait_idle().await;
        return;
    }
    assert!(matches!(lifecycle.as_str(), "cold" | "warm"));
    assert!(offered_rate.is_none_or(|rate| rate.is_finite() && rate > 0.0 && lifecycle == "warm"));
    assert!((1..=MAX_PAYLOAD).contains(&payload_bytes));
    let payload = vec![0x5a; payload_bytes];
    let mut warm: Option<(Endpoint, Connection)> = None;
    let mut schedule_origin: Option<Instant> = None;
    let mut records = if offered_rate.is_some() {
        Vec::new()
    } else {
        Vec::with_capacity(samples)
    };
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
        if sample_id == 0
            && let Some(marker) = &connected_marker
        {
            fs::write(marker, b"connected\n").unwrap();
        }
        let (scheduled_ns, started_ns, start_lateness_ns) = if let Some(rate) = offered_rate {
            let origin = *schedule_origin.get_or_insert_with(Instant::now);
            let offset = Duration::from_secs_f64(sample_id as f64 / rate);
            let deadline = origin + offset;
            wait_until(deadline).await;
            let started = Instant::now();
            (
                offset.as_nanos(),
                started.duration_since(origin).as_nanos(),
                started.saturating_duration_since(deadline).as_nanos(),
            )
        } else {
            (0, 0, 0)
        };
        let started = Instant::now();
        let response = request(&pair.1, &payload).await;
        let service_ns = started.elapsed().as_nanos();
        let request_ns = schedule_origin.map_or(service_ns, |origin| {
            origin.elapsed().as_nanos() - scheduled_ns
        });
        assert_eq!(response, payload);
        let record = format!(
            "{{\"sample_id\":{sample_id},\"success\":true,\"transport_handshake_ns\":{},\"request_latency_ns\":{request_ns},\"service_latency_ns\":{service_ns},\"scheduled_ns\":{scheduled_ns},\"started_ns\":{started_ns},\"completed_ns\":{},\"start_lateness_ns\":{start_lateness_ns},\"ttfab_ns\":{request_ns},\"total_scenario_ns\":{},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}",
            handshake_ns.map_or_else(|| "null".into(), |value| value.to_string()),
            schedule_origin.map_or(0, |origin| origin.elapsed().as_nanos()),
            total.elapsed().as_nanos()
        );
        if offered_rate.is_some() {
            println!("{record}");
        } else {
            records.push(record);
        }
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
