use std::collections::{BTreeMap, VecDeque};
use std::env;
use std::fs;
use std::net::{Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::time::Duration;

use nbsr_transport::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Limits, DestinationAdmission,
    EdgeIdentity, EdgeRole, LocalFederationAdmissionAttestations,
    LocalFederationAdmissionAuthorities, PeerPolicy, RouteGrantIssuer, TlsMaterial,
    TransportListener, TrustProfileId, build_server_config, decode_control_envelope,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use sha2::{Digest, Sha256};

fn cli_path(name: &str) -> PathBuf {
    let args: Vec<String> = env::args().collect();
    let index = args
        .iter()
        .position(|item| item == name)
        .unwrap_or_else(|| panic!("missing {name}"));
    PathBuf::from(
        args.get(index + 1)
            .unwrap_or_else(|| panic!("missing value for {name}")),
    )
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).unwrap()
}

fn tls_material(authority: &Path) -> TlsMaterial {
    let ca = CertificateDer::from(fs::read(authority.join("ca.der")).unwrap());
    let certificate = CertificateDer::from(fs::read(authority.join("destination.der")).unwrap());
    let key = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(
        fs::read(authority.join("destination-key.der")).unwrap(),
    ));
    let mut roots = RootCertStore::empty();
    roots.add(ca).unwrap();
    TlsMaterial::new(vec![certificate], key, roots).unwrap()
}

fn policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r"
            .into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg"
            .into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "service.example".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: [
                    0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2,
                    0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2,
                    0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                ],
            },
        )]),
        now: 1_893_456_000,
        client_session_public_key: [
            0x3d, 0x40, 0x17, 0xc3, 0xe8, 0x43, 0x89, 0x5a, 0x92, 0xb7, 0x0a, 0xa7, 0x4d, 0x1b,
            0x7e, 0xbc, 0x9c, 0x98, 0x2c, 0xcf, 0x2e, 0xc4, 0x96, 0x8c, 0xc0, 0xcd, 0x55, 0xf1,
            0x2a, 0xf4, 0x66, 0x0c,
        ],
        edge_nonce: (0x80..0xa0).collect::<Vec<_>>().try_into().unwrap(),
    }
}

fn lifecycle_policy(root: &Path, services: u64) -> AdmissionPolicy {
    let authorized_services = (0..services)
        .map(|index| {
            let name = fs::read_to_string(root.join(format!("{index:02}/name.txt")))
                .unwrap()
                .trim()
                .to_owned();
            (
                name,
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: [
                        0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4,
                        0xe2, 0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22,
                        0x58, 0xd2, 0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                    ],
                },
            )
        })
        .collect();
    AdmissionPolicy {
        authorized_services,
        ..policy()
    }
}

fn authorities() -> LocalFederationAdmissionAuthorities {
    let mut destination_key = [
        0xd7, 0x59, 0x79, 0x3b, 0xbc, 0x13, 0xa2, 0x81, 0x9a, 0x82, 0x7c, 0x76, 0xad, 0xb6, 0xfb,
        0xa8, 0xa4, 0x9a, 0xee, 0x00, 0x7f, 0x49, 0xf2, 0xd0, 0x99, 0x2d, 0x99, 0xb8, 0x25, 0xad,
        0x2c, 0x48,
    ];
    if env::var_os("NBSR_TASK10B_REVOKE_DESTINATION_AUTHORITY").is_some() {
        destination_key[0] ^= 1;
    }
    LocalFederationAdmissionAuthorities::new(
        b"local-source".to_vec(),
        [
            0xf8, 0x0c, 0xcc, 0xdc, 0xe4, 0xae, 0x1c, 0x07, 0xae, 0x20, 0x8a, 0x2a, 0xdf, 0x99,
            0xa3, 0x10, 0xae, 0x42, 0x07, 0xe0, 0x30, 0x6f, 0xa0, 0x23, 0x61, 0x10, 0xb0, 0x68,
            0x27, 0xbb, 0xb8, 0xd0,
        ],
        b"local-destination".to_vec(),
        destination_key,
    )
    .unwrap()
}

fn issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    }
}

fn envelope(
    message: u64,
    request: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> nbsr_transport::CoreV02Envelope {
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message);
    field_bytes(&mut wire, 2, &request);
    field_bytes(&mut wire, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend(body);
    decode_control_envelope(&wire, CoreV02Limits::default()).unwrap()
}

fn edge_hello() -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_text(&mut body, 1, "source.edge");
    field_text(&mut body, 2, "destination.edge");
    field_bytes(&mut body, 3, &(0x60..0x80).collect::<Vec<_>>());
    field_bytes(&mut body, 4, &(0x80..0xa0).collect::<Vec<_>>());
    field_bytes(
        &mut body,
        5,
        &[
            0x39, 0xf7, 0x13, 0xd0, 0xa6, 0x44, 0x25, 0x3f, 0x04, 0x52, 0x94, 0x21, 0xb9, 0xf5,
            0x1b, 0x9b, 0x08, 0x97, 0x9d, 0x08, 0x29, 0x59, 0x59, 0xc4, 0xf3, 0x99, 0x0e, 0xe6,
            0x17, 0xf5, 0x13, 0x9f,
        ],
    );
    field_uint(&mut body, 6, 1_893_456_000);
    envelope(
        2,
        (0x00..0x10).collect::<Vec<_>>().try_into().unwrap(),
        1,
        body,
    )
}

fn route_accept() -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &(0x40..0x50).collect::<Vec<_>>());
    field_bytes(&mut body, 2, &(0x20..0x30).collect::<Vec<_>>());
    field_bytes(
        &mut body,
        3,
        &[
            0xf6, 0x09, 0x00, 0x54, 0xa8, 0x32, 0xc5, 0x59, 0xb2, 0x8b, 0xba, 0x38, 0x6f, 0x78,
            0x61, 0x65, 0x57, 0xce, 0x13, 0xaf, 0x39, 0xe1, 0xa9, 0x5d, 0x3d, 0xff, 0x9e, 0x1f,
            0x7b, 0xa9, 0x68, 0x60,
        ],
    );
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(
        4,
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16],
        2,
        body,
    )
}

fn fixed<const N: usize>(path: &Path) -> [u8; N] {
    fs::read(path).unwrap().try_into().unwrap()
}

fn lifecycle_route_accept(
    root: &Path,
    index: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let directory = root.join(format!("{index:02}"));
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(
        &mut body,
        1,
        &fixed::<16>(&directory.join("channel-id.bin")),
    );
    field_bytes(&mut body, 2, &fixed::<16>(&directory.join("route-id.bin")));
    field_bytes(
        &mut body,
        3,
        &fixed::<32>(&directory.join("grant-digest.bin")),
    );
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(
        4,
        fixed::<16>(&directory.join("request-id.bin")),
        sequence,
        body,
    )
}

fn lifecycle_stream_accept(
    root: &Path,
    service: u64,
    stream_ordinal: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let directory = root.join(format!("{service:02}"));
    let stream_id = 4 + stream_ordinal * 4;
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, stream_id);
    field_bytes(
        &mut body,
        2,
        &fixed::<16>(&directory.join("channel-id.bin")),
    );
    field_bytes(&mut body, 3, &fixed::<16>(&directory.join("route-id.bin")));
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(7, stream_request(stream_ordinal), sequence, body)
}

async fn run_lifecycle(
    listener: &TransportListener,
    root: &Path,
    connections: u64,
    services: u64,
    streams_per_service: u64,
    concurrent: bool,
) -> Vec<(u128, u128)> {
    let mut measurements =
        Vec::with_capacity((connections * services * streams_per_service) as usize);
    let concurrent_sessions = env::var_os("NBSR_PERF_CONCURRENT_SESSIONS").is_some();
    let mut accepted_connections = VecDeque::new();
    if concurrent_sessions {
        for _ in 0..connections {
            accepted_connections.push_back(listener.accept_one().await.unwrap());
        }
    }
    for connection_ordinal in 0..connections {
        let connection = if concurrent_sessions {
            accepted_connections.pop_front().unwrap()
        } else {
            listener.accept_one().await.unwrap()
        };
        let mut control = connection.accept_control_stream().await.unwrap();
        let mut session = ControlSession::new(
            &connection,
            DestinationAdmission::new_federated(lifecycle_policy(root, services), authorities())
                .unwrap(),
            vec![issuer()],
            TrustProfileId::new("federation-dev-v1").unwrap(),
        );
        let client = control
            .receive_envelope(CoreV02Limits::default())
            .await
            .unwrap();
        session.accept_client_hello(&client).unwrap();
        let edge = edge_hello();
        session.confirm_edge_hello(&edge).unwrap();
        control.send_envelope(&edge).await.unwrap();
        let mut concurrent_tasks = tokio::task::JoinSet::new();
        let mut concurrent_admissions = vec![0_u128; services as usize];
        let mut concurrent_channels = Vec::with_capacity(services as usize);
        for index in 0..services {
            let directory = root.join(format!("{index:02}"));
            let route = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            let attestations = LocalFederationAdmissionAttestations {
                source: fs::read(directory.join("source.cose")).unwrap(),
                destination: fs::read(directory.join("destination.cose")).unwrap(),
            };
            let destination_admission = std::time::Instant::now();
            session
                .accept_federated_route_open(&route, &attestations)
                .unwrap();
            let destination_admission_ns = destination_admission.elapsed().as_nanos();
            concurrent_admissions[index as usize] = destination_admission_ns;
            let route_sequence = 2 + index * (1 + streams_per_service);
            let accepted = lifecycle_route_accept(root, index, route_sequence);
            session.confirm_route_accept(&accepted).unwrap();
            control.send_envelope(&accepted).await.unwrap();
            let channel = fixed::<16>(&directory.join("channel-id.bin"));
            connection.bind_channel(&mut session, channel).unwrap();
            if concurrent {
                for local_stream in 0..streams_per_service {
                    let stream_ordinal = index * streams_per_service + local_stream;
                    let stream = control
                        .receive_envelope(CoreV02Limits::default())
                        .await
                        .unwrap();
                    session.authorize_stream_open(channel, &stream).unwrap();
                    let stream_accepted = lifecycle_stream_accept(
                        root,
                        index,
                        stream_ordinal,
                        route_sequence + 1 + local_stream,
                    );
                    session
                        .confirm_stream_accept(channel, &stream_accepted)
                        .unwrap();
                    control.send_envelope(&stream_accepted).await.unwrap();
                }
                concurrent_channels.push(channel);
                continue;
            }
            for local_stream in 0..streams_per_service {
                let stream_ordinal = index * streams_per_service + local_stream;
                let stream = control
                    .receive_envelope(CoreV02Limits::default())
                    .await
                    .unwrap();
                session.authorize_stream_open(channel, &stream).unwrap();
                let stream_accepted = lifecycle_stream_accept(
                    root,
                    index,
                    stream_ordinal,
                    route_sequence + 1 + local_stream,
                );
                session
                    .confirm_stream_accept(channel, &stream_accepted)
                    .unwrap();
                control.send_envelope(&stream_accepted).await.unwrap();
                let application_processing = std::time::Instant::now();
                let application = connection
                    .accept_session_stream(&mut session, channel)
                    .await;
                if let Err(error) = &application {
                    eprintln!("nbsr-perf lifecycle application admission failed: {error:?}");
                }
                application.unwrap().echo_once().await.unwrap();
                measurements.push((
                    if local_stream == 0 {
                        destination_admission_ns
                    } else {
                        0
                    },
                    application_processing.elapsed().as_nanos(),
                ));
                session
                    .release_stream(channel, 4 + stream_ordinal * 4)
                    .unwrap();
                while session.pop_audit_event().is_some() {}
            }
        }
        if concurrent {
            for stream_ordinal in 0..(services * streams_per_service) {
                let service = stream_ordinal / streams_per_service;
                let local_stream = stream_ordinal % streams_per_service;
                let channel = concurrent_channels[service as usize];
                let mut application = connection
                    .accept_session_stream(&mut session, channel)
                    .await
                    .unwrap();
                concurrent_tasks.spawn(async move {
                    let started = std::time::Instant::now();
                    application.echo_once().await.unwrap();
                    (service, local_stream, channel, started.elapsed().as_nanos())
                });
            }
            let mut completed = vec![0_u128; (services * streams_per_service) as usize];
            while let Some(joined) = concurrent_tasks.join_next().await {
                let (service, local_stream, channel, application_ns) = joined.unwrap();
                let stream_ordinal = service * streams_per_service + local_stream;
                completed[stream_ordinal as usize] = application_ns;
                session
                    .release_stream(channel, 4 + stream_ordinal * 4)
                    .unwrap();
            }
            for (stream_ordinal, application_ns) in completed.into_iter().enumerate() {
                let service = stream_ordinal / streams_per_service as usize;
                let local_stream = stream_ordinal % streams_per_service as usize;
                measurements.push((
                    if local_stream == 0 {
                        concurrent_admissions[service]
                    } else {
                        0
                    },
                    application_ns,
                ));
            }
            while session.pop_audit_event().is_some() {}
        }
        tokio::time::timeout(Duration::from_secs(10), async {
            while fs::read_dir(root)
                .unwrap()
                .filter_map(Result::ok)
                .filter(|entry| {
                    let name = entry.file_name();
                    let name = name.to_string_lossy();
                    name.starts_with("connection-") && name.ends_with(".ack")
                })
                .count()
                < connection_ordinal as usize + 1
            {
                tokio::time::sleep(Duration::from_millis(1)).await;
            }
        })
        .await
        .expect("lifecycle client completion acknowledgement");
        if !concurrent_sessions {
            connection.close().await.unwrap();
        }
    }
    measurements
}

fn stream_accept(index: u64) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, 4 + 4 * index);
    field_bytes(&mut body, 2, &(0x40..0x50).collect::<Vec<_>>());
    field_bytes(&mut body, 3, &(0x20..0x30).collect::<Vec<_>>());
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(7, stream_request(index), 3 + index, body)
}

fn stream_request(index: u64) -> [u8; 16] {
    let mut request: [u8; 16] = (0_u8..16).collect::<Vec<_>>().try_into().unwrap();
    request[15] = 0x11;
    let suffix = u64::from_be_bytes(request[8..16].try_into().unwrap()) + index;
    request[8..16].copy_from_slice(&suffix.to_be_bytes());
    request
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let ready = cli_path("--ready");
    let result = cli_path("--result");
    let authority = cli_path("--authority-dir");
    let completion_ack = cli_path("--completion-ack");
    let peer_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(5),
        Duration::from_secs(10),
    )
    .unwrap();
    let port = env::var("NBSR_TASK10B_CAPTURE_PORT")
        .ok()
        .map(|value| value.parse::<u16>().expect("valid capture port"))
        .unwrap_or(0);
    let listener = TransportListener::bind(
        build_server_config(peer_policy, tls_material(&authority)).unwrap(),
        SocketAddr::from((Ipv4Addr::LOCALHOST, port)),
    )
    .unwrap();
    let endpoint = listener.local_addr().unwrap();
    let path = |name: &str| {
        authority
            .join(name)
            .display()
            .to_string()
            .replace('\\', "/")
    };
    fs::write(&ready,format!("{{\"alpn\":\"nbsr-quic-1\",\"ca_der\":\"{}\",\"client_cert_der\":\"{}\",\"client_key_der\":\"{}\",\"endpoint\":\"{}\",\"quic_version\":\"v1\",\"server_name\":\"destination.edge\",\"tls_version\":\"1.3\"}}",path("ca.der"),path("source.der"),path("source-key.der"),endpoint)).unwrap();
    if let Some(lifecycle_root) = env::var_os("NBSR_PERF_LIFECYCLE_ROOT") {
        let connections = env::var("NBSR_PERF_LIFECYCLE_CONNECTIONS")
            .unwrap()
            .parse::<u64>()
            .unwrap();
        let services = env::var("NBSR_PERF_LIFECYCLE_SERVICES")
            .unwrap()
            .parse::<u64>()
            .unwrap();
        let streams_per_service = env::var("NBSR_PERF_STREAMS_PER_SERVICE")
            .unwrap_or_else(|_| "1".into())
            .parse::<u64>()
            .unwrap();
        let concurrent = env::var_os("NBSR_PERF_CONCURRENT_STREAMS").is_some();
        assert!((1..=32).contains(&services));
        assert!((1..=64).contains(&streams_per_service));
        let measurements = run_lifecycle(
            &listener,
            &PathBuf::from(lifecycle_root),
            connections,
            services,
            streams_per_service,
            concurrent,
        )
        .await;
        let samples = measurements
            .iter()
            .map(|(destination, application)| format!("{{\"destination_admission_ns\":{destination},\"application_processing_ns\":{application}}}"))
            .collect::<Vec<_>>()
            .join(",");
        fs::write(result, format!("{{\"connections\":{connections},\"services_per_connection\":{services},\"streams_per_service\":{streams_per_service},\"samples\":[{samples}],\"status\":\"PASS\"}}")).unwrap();
        listener.close().await.unwrap();
        return;
    }
    let connection = listener.accept_one().await.unwrap();
    let mut control = connection.accept_control_stream().await.unwrap();
    let mut session = ControlSession::new(
        &connection,
        DestinationAdmission::new_federated(policy(), authorities()).unwrap(),
        vec![issuer()],
        TrustProfileId::new("federation-dev-v1").unwrap(),
    );
    let client = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    session.accept_client_hello(&client).unwrap();
    let edge = edge_hello();
    session.confirm_edge_hello(&edge).unwrap();
    control.send_envelope(&edge).await.unwrap();
    let route = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let attestations = LocalFederationAdmissionAttestations {
        source: fs::read(root.join("vectors/wp8-local-admission/source.cose")).unwrap(),
        destination: fs::read(root.join("vectors/wp8-local-admission/destination.cose")).unwrap(),
    };
    session
        .accept_federated_route_open(&route, &attestations)
        .unwrap();
    let accepted = route_accept();
    session.confirm_route_accept(&accepted).unwrap();
    control.send_envelope(&accepted).await.unwrap();
    let channel: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    connection.bind_channel(&mut session, channel).unwrap();
    let benchmark_samples = env::var("NBSR_PERF_STREAM_SAMPLES").ok();
    let samples = benchmark_samples
        .as_deref()
        .map(|value| value.parse::<u64>().expect("valid sample count"))
        .unwrap_or(1);
    assert!((1..=10_000_000).contains(&samples));
    let mut payload = Vec::new();
    for index in 0..samples {
        let stream = control
            .receive_envelope(CoreV02Limits::default())
            .await
            .unwrap();
        session.authorize_stream_open(channel, &stream).unwrap();
        let stream_accepted = stream_accept(index);
        session
            .confirm_stream_accept(channel, &stream_accepted)
            .unwrap();
        control.send_envelope(&stream_accepted).await.unwrap();
        payload = connection
            .accept_session_stream(&mut session, channel)
            .await
            .unwrap()
            .echo_once()
            .await
            .unwrap();
        session.release_stream(channel, 4 + 4 * index).unwrap();
        while session.pop_audit_event().is_some() {}
    }
    let digest = Sha256::digest(&payload);
    let digest_hex = digest
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let result_json = if benchmark_samples.is_some() {
        format!(
            "{{\"payload_bytes\":{},\"payload_sha256\":\"{}\",\"samples\":{},\"status\":\"PASS\"}}",
            payload.len(),
            digest_hex,
            samples
        )
    } else {
        format!(
            "{{\"payload_bytes\":{},\"payload_sha256\":\"{}\",\"status\":\"PASS\"}}",
            payload.len(),
            digest_hex
        )
    };
    fs::write(result, result_json).unwrap();
    tokio::time::timeout(Duration::from_secs(10), async {
        while !completion_ack.exists() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("test harness completion acknowledgement");
    connection.close().await.unwrap();
    listener.close().await.unwrap();
}

fn field_uint(t: &mut Vec<u8>, k: u64, v: u64) {
    uint(t, k);
    uint(t, v)
}
fn field_bytes(t: &mut Vec<u8>, k: u64, v: &[u8]) {
    uint(t, k);
    argument(t, 2, v.len() as u64);
    t.extend(v)
}
fn field_text(t: &mut Vec<u8>, k: u64, v: &str) {
    uint(t, k);
    argument(t, 3, v.len() as u64);
    t.extend(v.as_bytes())
}
fn uint(t: &mut Vec<u8>, v: u64) {
    argument(t, 0, v)
}
fn map(t: &mut Vec<u8>, v: u64) {
    argument(t, 5, v)
}
fn argument(t: &mut Vec<u8>, m: u8, v: u64) {
    let i = m << 5;
    match v {
        0..=23 => t.push(i | v as u8),
        24..=0xff => t.extend([i | 24, v as u8]),
        0x100..=0xffff => {
            t.push(i | 25);
            t.extend((v as u16).to_be_bytes())
        }
        0x1_0000..=0xffff_ffff => {
            t.push(i | 26);
            t.extend((v as u32).to_be_bytes())
        }
        _ => {
            t.push(i | 27);
            t.extend(v.to_be_bytes())
        }
    }
}
