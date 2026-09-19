use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::Arc;
#[cfg(feature = "benchmark-harness")]
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

#[cfg(feature = "benchmark-harness")]
use nbsr_transport::StreamCreditRefill;
#[cfg(not(feature = "benchmark-harness"))]
use nbsr_transport::connect;
#[cfg(feature = "benchmark-harness")]
use nbsr_transport::p2a_benchmark::{
    OutstandingTracker, build_benchmark_runtime, decode_frame, decode_measured_frame, encode_frame,
    encode_measured_frame, parse_group_count, parse_group_endpoints, parse_runtime_workers,
    run_current_thread_groups,
};
use nbsr_transport::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Limits, DestinationAdmission,
    EdgeIdentity, EdgeRole, LocalFederationAdmissionAttestations,
    LocalFederationAdmissionAuthorities, PeerPolicy, RouteGrantIssuer, TlsMaterial, TrustProfileId,
    build_client_config, decode_control_envelope,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
#[cfg(feature = "benchmark-harness")]
use tokio::sync::{Barrier, Notify};
#[cfg(feature = "benchmark-harness")]
use tokio::task::JoinSet;

#[cfg(feature = "benchmark-harness")]
mod b1_support;
#[cfg(all(test, feature = "benchmark-harness"))]
#[path = "benchmark_support/external_bind_contract_tests.rs"]
mod external_bind_contract_tests;
#[cfg(feature = "benchmark-harness")]
use nbsr_transport::benchmark_bind as external_bind;
#[cfg(feature = "benchmark-harness")]
#[path = "benchmark_support/allocator_snapshot.rs"]
mod allocator_snapshot;
mod b3_support;
#[cfg(feature = "benchmark-harness")]
mod b4_support;
#[cfg(feature = "benchmark-harness")]
#[path = "b5_support/driver.rs"]
mod b5_driver;
#[cfg(feature = "benchmark-harness")]
mod b5_support;
#[path = "benchmark_support/batch_release.rs"]
mod batch_release;
#[path = "benchmark_support/handshake_timeline.rs"]
mod handshake_timeline;
#[path = "benchmark_support/lifecycle_completion.rs"]
mod lifecycle_completion;
#[cfg(feature = "benchmark-harness")]
#[path = "benchmark_support/lifecycle_shards.rs"]
mod lifecycle_shards;
#[cfg(feature = "benchmark-harness")]
#[path = "benchmark_support/post_close.rs"]
mod post_close;
use lifecycle_completion::{CompletionCoordinator, CompletionSender, TerminalKind};

#[cfg(feature = "benchmark-harness")]
async fn run_lifecycle_clients(
    clients: Vec<usize>,
    timeline: Option<Arc<handshake_timeline::Region>>,
    release_gate: Option<batch_release::BatchRelease>,
    completion: CompletionSender,
) {
    let mut lifecycle_clients = tokio::task::JoinSet::new();
    let marker_monitor = optional_argument("--hold-for-release")
        .map(|_| b3_support::marker_monitor::MarkerMonitor::new());
    for ordinal in clients {
        let marker_waiter = marker_monitor.as_ref().map(|monitor| monitor.waiter());
        let completion = completion.clone();
        let slot = timeline.as_ref().and_then(|region| region.claim(ordinal));
        lifecycle_clients.spawn(async move {
            let task_completion = completion.clone();
            let run_slot = slot.clone();
            let client = batch_release::after_release(
                release_gate,
                ordinal,
                move || {
                    handshake_timeline::scope(run_slot, async move {
                        handshake_timeline::mark(handshake_timeline::Event::TaskStarted);
                        run(None, ordinal, Some(task_completion), None).await
                    })
                },
            );
            let outcome = tokio::spawn(b3_support::marker_monitor::scope(marker_waiter, client))
            .await;
            if let Err(error) = outcome {
                if let Some(slot) = &slot {
                    slot.mark(if error.is_cancelled() {
                        handshake_timeline::Event::Cancelled
                    } else {
                        handshake_timeline::Event::Failed
                    });
                }
                let terminal = if error.is_cancelled() {
                    TerminalKind::Cancelled
                } else {
                    TerminalKind::Failed
                };
                completion.record(ordinal, terminal).await.unwrap();
                println!(
                    "{{\"logical_client_id\":{ordinal},\"success\":false,\"error\":\"client_task_failed\",\"timed_out\":false}}"
                );
                if let Some(slot) = &slot {
                    slot.mark(handshake_timeline::Event::Cleaned);
                }
            }
            if let Some(slot) = &slot {
                slot.complete();
            }
        });
    }
    while let Some(client) = lifecycle_clients.join_next().await {
        client.expect("bounded lifecycle client task");
    }
    if let Some(monitor) = marker_monitor {
        monitor.shutdown().await;
    }
}

fn argument(name: &str) -> String {
    let values = env::args().collect::<Vec<_>>();
    let index = values
        .iter()
        .position(|value| value == name)
        .unwrap_or_else(|| panic!("missing {name}"));
    values[index + 1].clone()
}

fn optional_argument(name: &str) -> Option<String> {
    let values = env::args().collect::<Vec<_>>();
    values
        .iter()
        .position(|value| value == name)
        .map(|index| values[index + 1].clone())
}

fn emit_diagnostic(timestamp_ns: u128, phase: &str) {
    let snapshot = nbsr_transport::diagnostics::global().snapshot();
    let lifecycle = |name: &str, value: nbsr_transport::diagnostics::LifecycleSnapshot| {
        format!(
            "\"{name}_created\":{},\"{name}_completed\":{},\"{name}_failed_or_cancelled\":{},\"{name}_current_live\":{},\"{name}_high_water_live\":{}",
            value.created,
            value.completed,
            value.failed_or_cancelled,
            value.current_live,
            value.high_water_live
        )
    };
    let collection = |name: &str, value: nbsr_transport::diagnostics::CollectionSnapshot| {
        format!(
            "\"{name}_inserts\":{},\"{name}_removals\":{},\"{name}_current_entries\":{},\"{name}_high_water_entries\":{},\"{name}_retained_capacity\":{},\"{name}_high_water_retained_capacity\":{}",
            value.inserts,
            value.removals,
            value.current_entries,
            value.high_water_entries,
            value.retained_capacity,
            value.high_water_retained_capacity
        )
    };
    println!(
        "{{\"event\":\"diagnostic\",\"schema\":\"nbsr-rust-ownership-v1\",\"timestamp_ns\":{timestamp_ns},\"phase\":\"{phase}\",{},{},{},{},{},{},{},{},{},{},{}}}",
        lifecycle("transport_sessions", snapshot.transport_sessions),
        lifecycle("service_channels", snapshot.service_channels),
        lifecycle("application_streams", snapshot.application_streams),
        lifecycle("nbsr_tasks", snapshot.nbsr_tasks),
        lifecycle("quic_connections", snapshot.quic_connections),
        lifecycle("quic_streams", snapshot.quic_streams),
        collection("pending_routes", snapshot.pending_routes),
        collection("channel_registry", snapshot.channel_registry),
        collection("stream_registry", snapshot.stream_registry),
        collection("audit_queue", snapshot.audit_queue),
        collection("replay_state", snapshot.replay_state),
    );
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

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).unwrap()
}

fn tls_material(authority: &Path) -> TlsMaterial {
    let ca = CertificateDer::from(fs::read(authority.join("ca.der")).unwrap());
    let certificate = CertificateDer::from(fs::read(authority.join("source.der")).unwrap());
    let key = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(
        fs::read(authority.join("source-key.der")).unwrap(),
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
    LocalFederationAdmissionAuthorities::new(
        b"local-source".to_vec(),
        [
            0xf8, 0x0c, 0xcc, 0xdc, 0xe4, 0xae, 0x1c, 0x07, 0xae, 0x20, 0x8a, 0x2a, 0xdf, 0x99,
            0xa3, 0x10, 0xae, 0x42, 0x07, 0xe0, 0x30, 0x6f, 0xa0, 0x23, 0x61, 0x10, 0xb0, 0x68,
            0x27, 0xbb, 0xb8, 0xd0,
        ],
        b"local-destination".to_vec(),
        [
            0xd7, 0x59, 0x79, 0x3b, 0xbc, 0x13, 0xa2, 0x81, 0x9a, 0x82, 0x7c, 0x76, 0xad, 0xb6,
            0xfb, 0xa8, 0xa4, 0x9a, 0xee, 0x00, 0x7f, 0x49, 0xf2, 0xd0, 0x99, 0x2d, 0x99, 0xb8,
            0x25, 0xad, 0x2c, 0x48,
        ],
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

fn argument_cbor(target: &mut Vec<u8>, major: u8, value: u64) {
    let initial = major << 5;
    match value {
        0..=23 => target.push(initial | value as u8),
        24..=0xff => target.extend([initial | 24, value as u8]),
        0x100..=0xffff => {
            target.push(initial | 25);
            target.extend((value as u16).to_be_bytes());
        }
        0x1_0000..=0xffff_ffff => {
            target.push(initial | 26);
            target.extend((value as u32).to_be_bytes());
        }
        _ => {
            target.push(initial | 27);
            target.extend(value.to_be_bytes());
        }
    }
}
fn uint(target: &mut Vec<u8>, value: u64) {
    argument_cbor(target, 0, value);
}
fn map(target: &mut Vec<u8>, value: u64) {
    argument_cbor(target, 5, value);
}
fn bytes(target: &mut Vec<u8>, value: &[u8]) {
    argument_cbor(target, 2, value.len() as u64);
    target.extend(value);
}
fn field_uint(target: &mut Vec<u8>, key: u64, value: u64) {
    uint(target, key);
    uint(target, value);
}
fn field_bytes(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint(target, key);
    bytes(target, value);
}
fn field_text(target: &mut Vec<u8>, key: u64, value: &str) {
    uint(target, key);
    argument_cbor(target, 3, value.len() as u64);
    target.extend(value.as_bytes());
}

fn request(index: u64) -> [u8; 16] {
    let mut value: [u8; 16] = (0_u8..16).collect::<Vec<_>>().try_into().unwrap();
    value[15] = 0x11;
    let suffix = u64::from_be_bytes(value[8..16].try_into().unwrap()) + index;
    value[8..16].copy_from_slice(&suffix.to_be_bytes());
    value
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

fn stream_open(index: u64) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, 4 + 4 * index);
    field_bytes(&mut body, 2, &(0x40..0x50).collect::<Vec<_>>());
    field_bytes(&mut body, 3, &(0x20..0x30).collect::<Vec<_>>());
    field_bytes(
        &mut body,
        4,
        &[
            0xf6, 0x09, 0x00, 0x54, 0xa8, 0x32, 0xc5, 0x59, 0xb2, 0x8b, 0xba, 0x38, 0x6f, 0x78,
            0x61, 0x65, 0x57, 0xce, 0x13, 0xaf, 0x39, 0xe1, 0xa9, 0x5d, 0x3d, 0xff, 0x9e, 0x1f,
            0x7b, 0xa9, 0x68, 0x60,
        ],
    );
    field_text(&mut body, 5, "tcp");
    field_uint(&mut body, 6, 8443);
    envelope(6, request(index), 3 + index, body)
}

fn fixed<const N: usize>(path: &Path) -> [u8; N] {
    fs::read(path).unwrap().try_into().unwrap()
}

fn lifecycle_route_open(
    root: &Path,
    service: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let directory = root.join(format!("{service:02}"));
    envelope(
        3,
        fixed::<16>(&directory.join("request-id.bin")),
        sequence,
        fs::read(directory.join("route-open-body.cbor")).unwrap(),
    )
}

fn lifecycle_stream_open(
    root: &Path,
    service: u64,
    stream_ordinal: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let directory = root.join(format!("{service:02}"));
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, 4 + 4 * stream_ordinal);
    field_bytes(
        &mut body,
        2,
        &fixed::<16>(&directory.join("channel-id.bin")),
    );
    field_bytes(&mut body, 3, &fixed::<16>(&directory.join("route-id.bin")));
    field_bytes(
        &mut body,
        4,
        &fixed::<32>(&directory.join("grant-digest.bin")),
    );
    field_text(&mut body, 5, "tcp");
    field_uint(&mut body, 6, 8443);
    envelope(6, request(stream_ordinal), sequence, body)
}

#[allow(clippy::too_many_arguments)]
async fn run_lifecycle(
    authority: &Path,
    endpoint: SocketAddr,
    root: &Path,
    connections: u64,
    services: u64,
    streams_per_service: u64,
    concurrent: bool,
    connection_offset: u64,
    report_connections: bool,
    hold_for_release: bool,
    payload_bytes: usize,
    completion: Option<CompletionSender>,
) {
    let materialized_streams = optional_argument("--b3-materialized-streams").is_some();
    assert!(!materialized_streams || (hold_for_release && concurrent));
    let keep_alive = optional_argument("--b3-keep-alive-seconds");
    assert!(keep_alive.as_deref().is_none_or(|value| value == "1"));
    assert!(keep_alive.is_none() || hold_for_release);
    #[cfg(not(feature = "benchmark-harness"))]
    assert!(
        keep_alive.is_none(),
        "B3 keepalive requires benchmark-harness"
    );
    let payload = vec![0x5a; payload_bytes];
    let mut sample_id = 0_u64;
    #[cfg(feature = "benchmark-harness")]
    let lifecycle_bind =
        external_bind::client_bind(env::args()).expect("valid benchmark client bind");
    #[cfg(feature = "benchmark-harness")]
    let allocator_directory = optional_argument("--b3-allocator-directory").map(PathBuf::from);
    #[cfg(feature = "benchmark-harness")]
    if let Some(directory) = allocator_directory.as_deref() {
        assert!(
            hold_for_release
                && completion.is_none()
                && connection_offset == 0
                && connections <= 100
        );
        allocator_snapshot::snapshot(directory, 0).expect("initial allocator snapshot");
    }
    for connection_ordinal in 0..connections {
        if hold_for_release {
            let ordinal = connection_offset + connection_ordinal;
            b3_support::wait_for_lifecycle_start(
                &root.join(format!("connection-{ordinal}.start")),
                Duration::from_secs(120),
            )
            .await
            .unwrap();
        }
        let total_cold = Instant::now();
        let handshake = Instant::now();
        let client_config = build_client_config(
            PeerPolicy::new(
                EdgeRole::Source,
                EdgeRole::Destination,
                identity("destination.edge"),
                Duration::from_secs(5),
                Duration::from_secs(30),
            )
            .unwrap(),
            tls_material(authority),
        )
        .unwrap();
        #[cfg(feature = "benchmark-harness")]
        let client_config = if keep_alive.is_some() {
            client_config
                .with_benchmark_keep_alive(Duration::from_secs(1))
                .unwrap()
        } else {
            client_config
        };
        #[cfg(feature = "benchmark-harness")]
        let connecting =
            nbsr_transport::benchmark_connect_from(client_config, endpoint, lifecycle_bind);
        #[cfg(not(feature = "benchmark-harness"))]
        let connecting = connect(client_config, endpoint);
        let connection = match handshake_timeline::observe(connecting).await {
            Ok(connection) => connection,
            Err(error) => {
                let logical_client_id = connection_offset + connection_ordinal;
                handshake_timeline::mark(
                    if matches!(error, nbsr_transport::TransportError::HandshakeTimeout) {
                        handshake_timeline::Event::TimedOut
                    } else {
                        handshake_timeline::Event::Failed
                    },
                );
                if let Some(sender) = &completion {
                    let terminal =
                        if matches!(error, nbsr_transport::TransportError::HandshakeTimeout) {
                            TerminalKind::TimedOut
                        } else {
                            TerminalKind::Failed
                        };
                    sender
                        .record(logical_client_id as usize, terminal)
                        .await
                        .unwrap();
                } else {
                    fs::write(
                        root.join(format!("connection-{logical_client_id}.failed")),
                        format!("{error:?}\n"),
                    )
                    .unwrap();
                }
                println!(
                    "{{\"logical_client_id\":{logical_client_id},\"success\":false,\"error\":\"{error:?}\",\"timed_out\":{}}}",
                    matches!(error, nbsr_transport::TransportError::HandshakeTimeout)
                );
                handshake_timeline::mark(handshake_timeline::Event::Cleaned);
                return;
            }
        };
        let handshake_ns = handshake.elapsed().as_nanos();
        handshake_timeline::mark(handshake_timeline::Event::Connected);
        if report_connections {
            fs::write(
                root.join(format!(
                    "connection-{}.connected",
                    connection_offset + connection_ordinal
                )),
                b"connected\n",
            )
            .unwrap();
        }
        let mut control = connection.open_control_stream().await.unwrap();
        let client = client_hello();
        let hello = Instant::now();
        control.send_envelope(&client).await.unwrap();
        let edge = control
            .receive_envelope(CoreV02Limits::default())
            .await
            .unwrap();
        let hello_rtt_ns = hello.elapsed().as_nanos();
        let mut session = ControlSession::new(
            &connection,
            DestinationAdmission::new_federated(lifecycle_policy(root, services), authorities())
                .unwrap(),
            vec![issuer()],
            TrustProfileId::new("federation-dev-v1").unwrap(),
        );
        session.accept_client_hello(&client).unwrap();
        session.confirm_edge_hello(&edge).unwrap();
        handshake_timeline::mark(handshake_timeline::Event::ControlHelloComplete);
        let concurrent_barrier = Arc::new(tokio::sync::Barrier::new(
            (services * streams_per_service) as usize + 1,
        ));
        let mut concurrent_tasks = tokio::task::JoinSet::new();
        let prepared_barrier = materialized_streams.then(|| {
            Arc::new(tokio::sync::Barrier::new(
                (services * streams_per_service) as usize + 1,
            ))
        });
        let mut concurrent_metrics: Vec<(u64, u64, Instant, u128, u128, u128, u128)> = Vec::new();
        for service in 0..services {
            let scenario_started = Instant::now();
            let directory = root.join(format!("{service:02}"));
            let route_sequence = 2 + service * (1 + streams_per_service);
            let route = lifecycle_route_open(root, service, route_sequence);
            let attestations = LocalFederationAdmissionAttestations {
                source: fs::read(directory.join("source.cose")).unwrap(),
                destination: fs::read(directory.join("destination.cose")).unwrap(),
            };
            let source_admission = Instant::now();
            handshake_timeline::mark(handshake_timeline::Event::AdmissionStarted);
            session
                .accept_federated_route_open(&route, &attestations)
                .unwrap();
            let source_admission_ns = source_admission.elapsed().as_nanos();
            let route_started = Instant::now();
            control.send_envelope(&route).await.unwrap();
            let accepted = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            let route_open_rtt_ns = route_started.elapsed().as_nanos();
            session.confirm_route_accept(&accepted).unwrap();
            handshake_timeline::mark(handshake_timeline::Event::RouteAccepted);
            let channel = fixed::<16>(&directory.join("channel-id.bin"));
            let binding = Instant::now();
            connection.bind_channel(&mut session, channel).unwrap();
            handshake_timeline::mark(handshake_timeline::Event::Admitted);
            let channel_binding_ns = binding.elapsed().as_nanos();
            if concurrent {
                for local_stream in 0..streams_per_service {
                    let stream_ordinal = service * streams_per_service + local_stream;
                    let stream = lifecycle_stream_open(
                        root,
                        service,
                        stream_ordinal,
                        route_sequence + 1 + local_stream,
                    );
                    session.authorize_stream_open(channel, &stream).unwrap();
                    let stream_started = Instant::now();
                    control.send_envelope(&stream).await.unwrap();
                    let stream_accepted = control
                        .receive_envelope(CoreV02Limits::default())
                        .await
                        .unwrap();
                    session
                        .confirm_stream_accept(channel, &stream_accepted)
                        .unwrap();
                    let stream_rtt_ns = stream_started.elapsed().as_nanos();
                    let permit = session
                        .application_stream_permit(channel, 4 + 4 * stream_ordinal)
                        .unwrap();
                    let mut application = connection.open_session_stream(&permit).await.unwrap();
                    let task_barrier = concurrent_barrier.clone();
                    let task_prepared = prepared_barrier.clone();
                    let task_payload = payload.clone();
                    concurrent_tasks.spawn(async move {
                        let materialized_started = if let Some(prepared) = task_prepared {
                            let started = Instant::now();
                            application.send_payload(&task_payload).await.unwrap();
                            prepared.wait().await;
                            Some(started)
                        } else {
                            None
                        };
                        task_barrier.wait().await;
                        let request_started = materialized_started.unwrap_or_else(Instant::now);
                        let response = if materialized_started.is_some() {
                            application.receive_payload().await.unwrap()
                        } else {
                            application.send_and_receive(&task_payload).await.unwrap()
                        };
                        assert_eq!(response, task_payload);
                        (stream_ordinal, request_started.elapsed().as_nanos())
                    });
                    concurrent_metrics.push((
                        service,
                        local_stream,
                        scenario_started,
                        source_admission_ns,
                        route_open_rtt_ns,
                        channel_binding_ns,
                        stream_rtt_ns,
                    ));
                    // Consume mandatory audit records during setup, as the serial path does.
                    // Waiting until every held stream closes can fill the bounded audit queue.
                    while session.pop_audit_event().is_some() {}
                }
                continue;
            }
            for local_stream in 0..streams_per_service {
                let stream_ordinal = service * streams_per_service + local_stream;
                let stream = lifecycle_stream_open(
                    root,
                    service,
                    stream_ordinal,
                    route_sequence + 1 + local_stream,
                );
                session.authorize_stream_open(channel, &stream).unwrap();
                let stream_started = Instant::now();
                control.send_envelope(&stream).await.unwrap();
                let stream_accepted = control
                    .receive_envelope(CoreV02Limits::default())
                    .await
                    .unwrap();
                session
                    .confirm_stream_accept(channel, &stream_accepted)
                    .unwrap();
                let stream_open_rtt_ns = stream_started.elapsed().as_nanos();
                let permit = session
                    .application_stream_permit(channel, 4 + 4 * stream_ordinal)
                    .unwrap();
                let request_started = Instant::now();
                let response = connection
                    .open_session_stream(&permit)
                    .await
                    .unwrap()
                    .send_and_receive(&payload)
                    .await
                    .unwrap();
                let request_latency_ns = request_started.elapsed().as_nanos();
                assert_eq!(response, payload);
                session
                    .release_stream(channel, 4 + 4 * stream_ordinal)
                    .unwrap();
                let total_ns = if service == 0 && local_stream == 0 {
                    total_cold.elapsed().as_nanos()
                } else {
                    scenario_started.elapsed().as_nanos()
                };
                println!(
                    "{{\"sample_id\":{sample_id},\"logical_client_id\":{},\"success\":true,\"transport_handshake_ns\":{},\"hello_rtt_ns\":{},\"source_admission_ns\":{},\"destination_admission_ns\":null,\"route_open_rtt_ns\":{},\"channel_binding_ns\":{},\"stream_open_rtt_ns\":{stream_open_rtt_ns},\"ttfab_ns\":{total_ns},\"request_latency_ns\":{request_latency_ns},\"application_processing_ns\":null,\"total_scenario_ns\":{total_ns},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}",
                    connection_offset + connection_ordinal,
                    if service == 0 && local_stream == 0 {
                        handshake_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if service == 0 && local_stream == 0 {
                        hello_rtt_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if local_stream == 0 {
                        source_admission_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if local_stream == 0 {
                        route_open_rtt_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if local_stream == 0 {
                        channel_binding_ns.to_string()
                    } else {
                        "null".into()
                    },
                );
                sample_id += 1;
                while session.pop_audit_event().is_some() {}
            }
        }
        if concurrent {
            if let Some(prepared) = prepared_barrier {
                prepared.wait().await;
                if optional_argument("--diagnostics").is_some() {
                    emit_diagnostic(0, "b3_materialized_streams_ready");
                }
            }
            #[cfg(feature = "benchmark-harness")]
            let b3_prepared_ns = hold_for_release.then(|| total_cold.elapsed().as_nanos());
            if hold_for_release {
                let ordinal = connection_offset + connection_ordinal;
                b3_support::wait_for_lifecycle_release(
                    &root.join(format!("connection-{ordinal}.active")),
                    &root.join(format!("connection-{ordinal}.release")),
                    Duration::from_secs(120),
                )
                .await
                .unwrap();
            }
            #[cfg(feature = "benchmark-harness")]
            let b3_released_ns = hold_for_release.then(|| total_cold.elapsed().as_nanos());
            concurrent_barrier.wait().await;
            let mut request_latencies = vec![0_u128; (services * streams_per_service) as usize];
            while let Some(joined) = concurrent_tasks.join_next().await {
                #[cfg(feature = "benchmark-harness")]
                if joined.is_err() && hold_for_release {
                    let diagnostic = format!(
                        "{{\"schema\":\"nbsr-b3-close-diagnostic-v1\",\"role\":\"source\",\"logical_client_id\":{},\"clock_origin\":\"connection_attempt\",\"prepared_elapsed_ns\":{},\"released_elapsed_ns\":{},\"failed_elapsed_ns\":{},\"close_reason\":\"{}\"}}\n",
                        connection_offset + connection_ordinal,
                        b3_prepared_ns.unwrap(),
                        b3_released_ns.unwrap(),
                        total_cold.elapsed().as_nanos(),
                        connection.benchmark_close_reason_category()
                    );
                    // Build the whole line before writing: panic output from sibling
                    // tasks can otherwise split a formatted diagnostic between fields.
                    std::io::Write::write_all(&mut std::io::stderr().lock(), diagnostic.as_bytes())
                        .expect("B3 failure diagnostic write");
                }
                let (stream_ordinal, request_ns) = joined.unwrap();
                request_latencies[stream_ordinal as usize] = request_ns;
                let service = stream_ordinal / streams_per_service;
                let channel = fixed::<16>(&root.join(format!("{service:02}/channel-id.bin")));
                session
                    .release_stream(channel, 4 + 4 * stream_ordinal)
                    .unwrap();
            }
            for (
                service,
                local_stream,
                scenario_started,
                source_admission_ns,
                route_open_rtt_ns,
                channel_binding_ns,
                stream_open_rtt_ns,
            ) in concurrent_metrics
            {
                let stream_ordinal = service * streams_per_service + local_stream;
                let request_latency_ns = request_latencies[stream_ordinal as usize];
                let total_ns = if service == 0 && local_stream == 0 {
                    total_cold.elapsed().as_nanos()
                } else {
                    scenario_started.elapsed().as_nanos()
                };
                println!(
                    "{{\"sample_id\":{sample_id},\"logical_client_id\":{},\"success\":true,\"transport_handshake_ns\":{},\"hello_rtt_ns\":{},\"source_admission_ns\":{},\"destination_admission_ns\":null,\"route_open_rtt_ns\":{},\"channel_binding_ns\":{},\"stream_open_rtt_ns\":{stream_open_rtt_ns},\"ttfab_ns\":{total_ns},\"request_latency_ns\":{request_latency_ns},\"application_processing_ns\":null,\"total_scenario_ns\":{total_ns},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}",
                    connection_offset + connection_ordinal,
                    if service == 0 && local_stream == 0 {
                        handshake_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if service == 0 && local_stream == 0 {
                        hello_rtt_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if local_stream == 0 {
                        source_admission_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if local_stream == 0 {
                        route_open_rtt_ns.to_string()
                    } else {
                        "null".into()
                    },
                    if local_stream == 0 {
                        channel_binding_ns.to_string()
                    } else {
                        "null".into()
                    },
                );
                sample_id += 1;
            }
            while session.pop_audit_event().is_some() {}
        }
        let logical_client_id = connection_offset + connection_ordinal;
        drop(session);
        drop(control);
        let mut terminal = TerminalKind::Completed;
        if hold_for_release {
            drop(connection);
        } else {
            if let Err(error) = connection.close().await {
                handshake_timeline::mark(
                    if matches!(error, nbsr_transport::TransportError::CloseTimeout) {
                        handshake_timeline::Event::TimedOut
                    } else {
                        handshake_timeline::Event::Failed
                    },
                );
                terminal = if matches!(error, nbsr_transport::TransportError::CloseTimeout) {
                    TerminalKind::TimedOut
                } else {
                    TerminalKind::Failed
                };
                println!(
                    "{{\"logical_client_id\":{logical_client_id},\"success\":false,\"phase\":\"close\",\"error\":\"{error:?}\",\"timed_out\":{}}}",
                    matches!(error, nbsr_transport::TransportError::CloseTimeout)
                );
            }
        }
        // close(self) has consumed/dropped the connection even on error.
        // This observation does not change the failed lifecycle outcome.
        handshake_timeline::mark(handshake_timeline::Event::Cleaned);
        if let Some(sender) = &completion {
            sender
                .record(logical_client_id as usize, terminal)
                .await
                .unwrap();
        } else {
            let (extension, contents) = match terminal {
                TerminalKind::Completed => ("ack", b"complete\n".as_slice()),
                _ => ("failed", b"close_failed\n".as_slice()),
            };
            fs::write(
                root.join(format!("connection-{logical_client_id}.{extension}")),
                contents,
            )
            .unwrap();
            if hold_for_release && optional_argument("--diagnostics").is_some() {
                emit_diagnostic(0, &format!("lifecycle_cycle_{logical_client_id}_closed"));
            }
            #[cfg(feature = "benchmark-harness")]
            if let Some(directory) = allocator_directory.as_deref() {
                allocator_snapshot::snapshot(directory, connection_ordinal + 1)
                    .expect("completed-cycle allocator snapshot");
            }
        }
    }
    if hold_for_release
        && completion.is_none()
        && let Some(path) = optional_argument("--lifecycle-final-release")
    {
        b3_support::wait_for_lifecycle_start(Path::new(&path), Duration::from_secs(120))
            .await
            .unwrap();
    }
}

fn client_hello() -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 8);
    field_uint(&mut body, 0, 1);
    field_text(
        &mut body,
        1,
        "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r",
    );
    field_text(&mut body, 2, "source.edge");
    field_text(
        &mut body,
        3,
        "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg",
    );
    field_text(&mut body, 4, "destination.edge");
    field_bytes(&mut body, 5, &(0x60..0x80).collect::<Vec<_>>());
    field_bytes(&mut body, 6, &policy().client_session_public_key);
    field_uint(&mut body, 7, 1_893_456_000);
    envelope(
        1,
        (0x00..0x10).collect::<Vec<_>>().try_into().unwrap(),
        1,
        body,
    )
}

#[cfg(feature = "benchmark-harness")]
struct P2dSourceResult<'a> {
    mode: &'a str,
    concurrency: usize,
    payload_bytes: usize,
    measured_ns: u128,
    latencies: &'a [u64],
    payload_correct: bool,
    remaining_credits: Option<u8>,
    refill_count: u64,
    active_epochs: u8,
    active_epochs_high_water: u8,
    replay_entries: usize,
    replay_limit: usize,
    minimum_remaining_credits: Option<u8>,
    buffer_exhaustions: u64,
}

#[cfg(feature = "benchmark-harness")]
struct P2dSourceRun {
    channel: [u8; 16],
    operations: u64,
    concurrency: usize,
    payload_bytes: usize,
    smoke_exhaustion: bool,
}

#[cfg(feature = "benchmark-harness")]
fn p2d_emit_result(result: P2dSourceResult<'_>) {
    let P2dSourceResult {
        mode,
        concurrency,
        payload_bytes,
        measured_ns,
        latencies,
        payload_correct,
        remaining_credits,
        refill_count,
        active_epochs,
        active_epochs_high_water,
        replay_entries,
        replay_limit,
        minimum_remaining_credits,
        buffer_exhaustions,
    } = result;
    let latency_json = latencies
        .iter()
        .map(u64::to_string)
        .collect::<Vec<_>>()
        .join(",");
    let remaining = remaining_credits.map_or_else(|| "null".into(), |value| value.to_string());
    let minimum =
        minimum_remaining_credits.map_or_else(|| "null".into(), |value| value.to_string());
    println!(
        "{{\"event\":\"p2d_shard\",\"schema\":\"nbsr-p2d-rust-shard-v1\",\"mode\":\"{mode}\",\"concurrency\":{concurrency},\"payload_bytes\":{payload_bytes},\"payload_correct\":{payload_correct},\"completed_operations\":{},\"duration_ns\":{measured_ns},\"errors\":0,\"remaining_credits\":{remaining},\"refill_count\":{refill_count},\"windows_crossed\":{refill_count},\"active_epochs\":{active_epochs},\"active_epochs_high_water\":{active_epochs_high_water},\"replay_entries\":{replay_entries},\"replay_limit\":{replay_limit},\"minimum_remaining_credits\":{minimum},\"buffer_exhaustions\":{buffer_exhaustions},\"latencies_ns\":[{latency_json}]}}",
        latencies.len()
    );
}

#[cfg(feature = "benchmark-harness")]
async fn run_p2d_before(
    connection: nbsr_transport::AuthenticatedConnection,
    mut control: nbsr_transport::ControlStream,
    mut session: ControlSession,
    run: P2dSourceRun,
) {
    let P2dSourceRun {
        channel,
        operations,
        concurrency,
        payload_bytes,
        smoke_exhaustion: _,
    } = run;
    let payload = vec![0x5a; payload_bytes];
    let mut latencies = Vec::with_capacity(operations as usize);
    let measured = Instant::now();
    let mut next = 0_u64;
    while next < operations {
        let batch = usize::min(concurrency, (operations - next) as usize);
        let mut tasks = JoinSet::new();
        for offset in 0..batch {
            let index = next + offset as u64;
            let started = Instant::now();
            let request = stream_open(index);
            session.authorize_stream_open(channel, &request).unwrap();
            control.send_envelope(&request).await.unwrap();
            let accepted = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            session.confirm_stream_accept(channel, &accepted).unwrap();
            let permit = session
                .application_stream_permit(channel, 4 + 4 * index)
                .unwrap();
            let mut application = connection.open_session_stream(&permit).await.unwrap();
            let expected = payload.clone();
            tasks.spawn(async move {
                let stream_id = application.id();
                let response = application.send_and_receive(&expected).await.unwrap();
                (
                    stream_id,
                    started.elapsed().as_nanos() as u64,
                    response == expected,
                )
            });
        }
        while let Some(joined) = tasks.join_next().await {
            let (stream_id, latency, correct) = joined.unwrap();
            assert!(correct);
            latencies.push(latency);
            session.release_stream(channel, stream_id).unwrap();
        }
        while session.pop_audit_event().is_some() {}
        next += batch as u64;
    }
    let measured_ns = measured.elapsed().as_nanos();
    let diagnostics = nbsr_transport::diagnostics::global().snapshot();
    p2d_emit_result(P2dSourceResult {
        mode: "before",
        concurrency,
        payload_bytes,
        measured_ns,
        latencies: &latencies,
        payload_correct: true,
        remaining_credits: None,
        refill_count: 0,
        active_epochs: 0,
        active_epochs_high_water: 0,
        replay_entries: diagnostics.replay_state.current_entries as usize,
        replay_limit: 10_000,
        minimum_remaining_credits: None,
        buffer_exhaustions: 0,
    });
    drop(session);
    connection.close().await.unwrap();
}

#[cfg(feature = "benchmark-harness")]
async fn run_p2d_after(
    connection: nbsr_transport::AuthenticatedConnection,
    mut control: nbsr_transport::ControlStream,
    session: ControlSession,
    run: P2dSourceRun,
) {
    let P2dSourceRun {
        channel,
        operations,
        concurrency,
        payload_bytes,
        smoke_exhaustion,
    } = run;
    let connection = Arc::new(connection);
    let session = nbsr_transport::SharedControlSession::new(session);
    let payload = vec![0x5a; payload_bytes];
    let mut latencies = Vec::with_capacity(operations as usize);
    let mut refill_count = 0_u64;
    let mut active_epochs_high_water = 1_u8;
    let mut minimum_remaining = 64_u8;
    let mut buffer_exhaustions = 0_u64;
    let measured = Instant::now();
    let mut next = 0_u64;
    while next < operations {
        let batch = usize::min(concurrency, (operations - next) as usize);
        let mut tasks = JoinSet::new();
        for _ in 0..batch {
            let task_connection = Arc::clone(&connection);
            let task_session = session.clone();
            let expected = payload.clone();
            let started = Instant::now();
            tasks.spawn(async move {
                let mut application = task_connection
                    .open_credited_session_stream(&task_session, channel)
                    .await
                    .unwrap();
                let stream_id = application.id();
                let response = application.send_and_receive(&expected).await.unwrap();
                (
                    stream_id,
                    started.elapsed().as_nanos() as u64,
                    response == expected,
                )
            });
        }
        while let Some(joined) = tasks.join_next().await {
            let (stream_id, latency, correct) = joined.unwrap();
            assert!(correct);
            latencies.push(latency);
            session
                .update(|session| session.release_stream(channel, stream_id))
                .unwrap();
        }
        session.update(|session| while session.pop_audit_event().is_some() {});
        let snapshot = session
            .inspect(|session| session.stream_credit_snapshot(channel))
            .unwrap();
        minimum_remaining = minimum_remaining.min(snapshot.remaining_credits);
        if let Some(epoch) = snapshot.pending_refill {
            if smoke_exhaustion && snapshot.remaining_credits == 0 {
                assert_eq!(
                    connection
                        .open_credited_session_stream(&session, channel)
                        .await
                        .err(),
                    Some(nbsr_transport::TransportError::ApplicationStreamRejected)
                );
                buffer_exhaustions += 1;
            }
            let refill = StreamCreditRefill {
                channel_id: channel,
                epoch,
            };
            control
                .send_stream_credit_refill_request(refill)
                .await
                .unwrap();
            let grant = control.receive_stream_credit_refill_grant().await.unwrap();
            assert_eq!(grant, refill);
            session
                .update(|session| session.confirm_stream_credit_refill(channel, epoch))
                .unwrap();
            let activated = session
                .inspect(|session| session.stream_credit_snapshot(channel))
                .unwrap();
            active_epochs_high_water = active_epochs_high_water.max(activated.active_epochs);
            session
                .update(|session| session.retire_stream_credit_epoch(channel, epoch - 1))
                .unwrap();
            refill_count += 1;
        }
        next += batch as u64;
    }
    let measured_ns = measured.elapsed().as_nanos();
    let final_state = session
        .inspect(|session| session.stream_credit_snapshot(channel))
        .unwrap();
    p2d_emit_result(P2dSourceResult {
        mode: "after",
        concurrency,
        payload_bytes,
        measured_ns,
        latencies: &latencies,
        payload_correct: true,
        remaining_credits: Some(final_state.remaining_credits),
        refill_count,
        active_epochs: final_state.active_epochs,
        active_epochs_high_water,
        replay_entries: final_state.replay_entries,
        replay_limit: final_state.replay_limit,
        minimum_remaining_credits: Some(minimum_remaining),
        buffer_exhaustions,
    });
    drop(session);
    Arc::try_unwrap(connection)
        .ok()
        .expect("P2D source tasks are complete")
        .close()
        .await
        .unwrap();
}

async fn run(
    group_barrier: Option<Arc<std::sync::Barrier>>,
    group_ordinal: usize,
    completion: Option<CompletionSender>,
    #[cfg(feature = "benchmark-harness")] paced: Option<Arc<b5_driver::Driver>>,
) {
    #[cfg(feature = "benchmark-harness")]
    let paced_guard = paced
        .as_ref()
        .map(|driver| driver.run.group_guard(group_ordinal).unwrap());
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let authority = PathBuf::from(argument("--authority-dir"));
    let default_endpoint = argument("--endpoint");
    #[cfg(feature = "benchmark-harness")]
    let endpoint: SocketAddr = parse_group_endpoints(
        env::args(),
        parse_group_count(env::args()).expect("valid --p2a-groups"),
    )
    .expect("valid --p2a-endpoints")
    .and_then(|endpoints| endpoints.get(group_ordinal).cloned())
    .unwrap_or(default_endpoint)
    .parse()
    .unwrap();
    #[cfg(not(feature = "benchmark-harness"))]
    let endpoint: SocketAddr = default_endpoint.parse().unwrap();
    let samples: u64 = argument("--samples").parse().unwrap();
    let payload_bytes: usize = argument("--payload-bytes").parse().unwrap();
    let offered_rate =
        optional_argument("--offered-rate").map(|value| value.parse::<f64>().unwrap());
    let diagnostics_enabled = optional_argument("--diagnostics").is_some();
    let drain_seconds = optional_argument("--diagnostic-drain-seconds")
        .map_or(0, |value| value.parse::<u64>().unwrap());
    let completion_ack = optional_argument("--diagnostic-completion-ack").map(PathBuf::from);
    let post_load_hold_seconds = optional_argument("--post-load-hold-seconds")
        .map_or(0, |value| value.parse::<u64>().unwrap());
    let post_load_completion_ack =
        optional_argument("--post-load-completion-ack").map(PathBuf::from);
    let p2d_mode = optional_argument("--p2d-mode");
    #[cfg(feature = "benchmark-harness")]
    let p2d_concurrency =
        optional_argument("--p2d-concurrency").map(|value| value.parse::<usize>().unwrap());
    #[cfg(feature = "benchmark-harness")]
    let p2d_smoke_exhaustion = optional_argument("--p2d-smoke-exhaustion").is_some();
    if p2d_mode.is_some() {
        nbsr_transport::diagnostics::enable_global();
    }
    if diagnostics_enabled {
        nbsr_transport::diagnostics::enable_global();
    }
    if let Some(lifecycle_root) = optional_argument("--lifecycle-authority-dir") {
        let logical_clients =
            optional_argument("--lifecycle-clients").map(|value| value.parse::<usize>().unwrap());
        let connections = if logical_clients.is_some() {
            1
        } else {
            argument("--connections").parse::<u64>().unwrap()
        };
        let services = argument("--services").parse::<u64>().unwrap();
        let streams_per_service = optional_argument("--streams-per-service")
            .unwrap_or_else(|| "1".into())
            .parse::<u64>()
            .unwrap();
        let concurrent = optional_argument("--concurrent-streams").is_some();
        let hold_for_release = optional_argument("--hold-for-release").is_some();
        let connection_offset_argument = optional_argument("--connection-offset");
        let connection_offset = connection_offset_argument
            .clone()
            .unwrap_or_else(|| "0".into())
            .parse::<u64>()
            .unwrap()
            + if logical_clients.is_some() {
                group_ordinal as u64
            } else {
                0
            };
        assert!((1..=32).contains(&services));
        assert!((1..=64).contains(&streams_per_service));
        assert!(!hold_for_release || concurrent);
        run_lifecycle(
            &authority,
            endpoint,
            &PathBuf::from(lifecycle_root),
            connections,
            services,
            streams_per_service,
            concurrent,
            connection_offset,
            connection_offset_argument.is_some(),
            hold_for_release,
            payload_bytes,
            completion,
        )
        .await;
        return;
    }
    assert!((1..=10_000_000).contains(&samples));
    assert!(offered_rate.is_none_or(|rate| rate.is_finite() && rate > 0.0));
    assert!(samples <= 100_000 || offered_rate.is_some());
    assert!((1..=1_048_576).contains(&payload_bytes));
    let handshake = Instant::now();
    let config = build_client_config(
        PeerPolicy::new(
            EdgeRole::Source,
            EdgeRole::Destination,
            identity("destination.edge"),
            Duration::from_secs(5),
            Duration::from_secs(30),
        )
        .unwrap(),
        tls_material(&authority),
    )
    .unwrap();
    #[cfg(feature = "benchmark-harness")]
    let connection = nbsr_transport::benchmark_connect_from(
        config,
        endpoint,
        external_bind::client_bind(env::args()).expect("valid benchmark client bind"),
    )
    .await
    .unwrap();
    #[cfg(not(feature = "benchmark-harness"))]
    let connection = connect(config, endpoint).await.unwrap();
    let handshake_ns = handshake.elapsed().as_nanos();
    let mut control = connection.open_control_stream().await.unwrap();
    let client = client_hello();
    control.send_envelope(&client).await.unwrap();
    let edge = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let admission = DestinationAdmission::new_federated(policy(), authorities()).unwrap();
    let trusted_issuers = vec![issuer()];
    let trust_profile = TrustProfileId::new("federation-dev-v1").unwrap();
    let mut session = if p2d_mode.is_some() {
        ControlSession::new_with_replay_history_limit(
            &connection,
            admission,
            trusted_issuers,
            trust_profile,
            nbsr_transport::ReplayHistoryLimit::try_from(10_000).unwrap(),
        )
    } else {
        ControlSession::new(&connection, admission, trusted_issuers, trust_profile)
    };
    session.accept_client_hello(&client).unwrap();
    session.confirm_edge_hello(&edge).unwrap();
    let route_body = root
        .join("vectors/wp8-f75-route-open/route-open-body.cbor")
        .read_bytes();
    let route = envelope(
        3,
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16],
        2,
        route_body,
    );
    let attestations = LocalFederationAdmissionAttestations {
        source: root
            .join("vectors/wp8-local-admission/source.cose")
            .read_bytes(),
        destination: root
            .join("vectors/wp8-local-admission/destination.cose")
            .read_bytes(),
    };
    session
        .accept_federated_route_open(&route, &attestations)
        .unwrap();
    control.send_envelope(&route).await.unwrap();
    let accepted = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let channel: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    if p2d_mode.as_deref() == Some("after") {
        session
            .select_stream_credit_profile(
                channel,
                true,
                Some(nbsr_transport::STREAM_CREDIT_PROFILE_ID),
                false,
            )
            .unwrap();
    }
    session.confirm_route_accept(&accepted).unwrap();
    connection.bind_channel(&mut session, channel).unwrap();
    #[cfg(feature = "benchmark-harness")]
    if let Some(mode) = p2d_mode.as_deref() {
        let concurrency = p2d_concurrency.expect("--p2d-concurrency is required");
        assert!(matches!(concurrency, 1 | 2 | 4 | 8 | 16 | 32 | 64));
        assert!((1..=8_000).contains(&samples));
        assert_eq!(payload_bytes, 1024);
        match mode {
            "before" => {
                run_p2d_before(
                    connection,
                    control,
                    session,
                    P2dSourceRun {
                        channel,
                        operations: samples,
                        concurrency,
                        payload_bytes,
                        smoke_exhaustion: false,
                    },
                )
                .await
            }
            "after" => {
                run_p2d_after(
                    connection,
                    control,
                    session,
                    P2dSourceRun {
                        channel,
                        operations: samples,
                        concurrency,
                        payload_bytes,
                        smoke_exhaustion: p2d_smoke_exhaustion,
                    },
                )
                .await
            }
            _ => panic!("--p2d-mode must be before or after"),
        }
        return;
    }
    #[cfg(feature = "benchmark-harness")]
    if let Some(stream_count) = optional_argument("--p2a-streams") {
        let stream_count = stream_count.parse::<u64>().unwrap();
        assert!((1..=64).contains(&stream_count));
        let outstanding_per_stream = optional_argument("--p2a-outstanding-per-stream")
            .map_or(1, |value| value.parse::<usize>().unwrap());
        assert!((1..=64).contains(&outstanding_per_stream));
        let warmup = Duration::from_secs_f64(argument("--p2a-warmup-seconds").parse().unwrap());
        let duration_seconds =
            optional_argument("--p2a-duration-seconds").map(|value| value.parse().unwrap());
        let measurement = b1_support::measurement_mode(
            duration_seconds,
            optional_argument("--p2a-operations-per-stream").map(|value| value.parse().unwrap()),
        )
        .unwrap();
        let mixed = b4_support::mixed_admission_config(
            optional_argument("--b4-admission-rate").map(|value| value.parse().unwrap()),
            duration_seconds,
        )
        .unwrap();
        let progress_interval = if paced.is_some() {
            None
        } else {
            optional_argument("--p2a-progress-seconds").map(|value| value.parse::<f64>().unwrap())
        };
        if let Some(seconds) = progress_interval {
            assert!(seconds.is_finite() && (1.0..=60.0).contains(&seconds));
            assert!(duration_seconds.is_some());
        }
        let cooldown_seconds = optional_argument("--p2a-cooldown-seconds")
            .map_or(0.0, |value| value.parse::<f64>().unwrap());
        assert!(cooldown_seconds.is_finite() && (0.0..=300.0).contains(&cooldown_seconds));
        let soak_telemetry =
            progress_interval.map(|_| Arc::new(b5_support::SoakTelemetry::new(64).unwrap()));
        let counter_control = optional_argument("--p2a-counter-control")
            .map(|value| value.parse::<SocketAddr>().unwrap());
        nbsr_transport::diagnostics::enable_global();
        let payload = vec![0x5a; payload_bytes];
        let mut applications = Vec::with_capacity(stream_count as usize);
        for index in 0..stream_count {
            let stream = stream_open(index);
            session.authorize_stream_open(channel, &stream).unwrap();
            control.send_envelope(&stream).await.unwrap();
            let accepted = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            session.confirm_stream_accept(channel, &accepted).unwrap();
            let permit = session
                .application_stream_permit(channel, 4 + 4 * index)
                .unwrap();
            applications.push(connection.open_session_stream(&permit).await.unwrap());
        }
        b1_support::counter_phase(counter_control, "setup-complete").unwrap();
        let ready = Arc::new(Barrier::new(stream_count as usize + 1));
        let measure = Arc::new(Barrier::new(stream_count as usize + 1));
        let warmup_deadline = Instant::now() + warmup;
        let mut tasks = JoinSet::new();
        for (ordinal, mut application) in applications.into_iter().enumerate() {
            let ready = Arc::clone(&ready);
            let measure = Arc::clone(&measure);
            let payload = payload.clone();
            let soak_telemetry = soak_telemetry.clone();
            let paced = paced.clone();
            tasks.spawn(async move {
                let mut failure_guard = paced.as_ref().map(|driver| driver.failure_guard());
                let mut sequence = (ordinal as u64) << 56;
                let preflight = encode_frame(sequence, &payload);
                application.benchmark_write_frame(&preflight).await.unwrap();
                let response = application.benchmark_read_frame().await.unwrap();
                decode_frame(&response, sequence, payload.len()).unwrap();
                sequence += 1;
                let mut warmup_tracker = OutstandingTracker::new(outstanding_per_stream).unwrap();
                while Instant::now() < warmup_deadline || warmup_tracker.in_flight() > 0 {
                    while Instant::now() < warmup_deadline && warmup_tracker.can_issue() {
                        let started = Instant::now();
                        let wire = encode_measured_frame(sequence, &payload);
                        application.benchmark_write_frame(&wire).await.unwrap();
                        warmup_tracker.issue(sequence, started).unwrap();
                        sequence += 1;
                    }
                    if let Some(expected) = warmup_tracker.next_sequence() {
                        let response = application.benchmark_read_frame().await.unwrap();
                        decode_measured_frame(&response, expected, &payload).unwrap();
                        warmup_tracker.complete(expected).unwrap();
                    }
                }
                if let Some(driver) = &paced {
                    tokio::select! {
                        _ = ready.wait() => {}
                        _ = driver.run.wait_failed() => panic!("paced warmup failed"),
                    }
                    tokio::select! {
                        _ = measure.wait() => {}
                        _ = driver.run.wait_failed() => panic!("paced measurement readiness failed"),
                    }
                } else {
                    ready.wait().await;
                    measure.wait().await;
                }
                let deadline = match measurement {
                    b1_support::MeasurementMode::Duration(seconds) => {
                        Some(Instant::now() + Duration::from_secs_f64(seconds))
                    }
                    b1_support::MeasurementMode::OperationsPerStream(_) => None,
                };
                let operation_limit = match measurement {
                    b1_support::MeasurementMode::OperationsPerStream(operations) => {
                        Some(operations)
                    }
                    b1_support::MeasurementMode::Duration(_) => None,
                };
                let mut latencies = Vec::new();
                let mut tracker = OutstandingTracker::new(outstanding_per_stream).unwrap();
                loop {
                    if let Some(driver) = &paced {
                        let partition = driver.partition(group_ordinal, ordinal).unwrap();
                        match driver.run.next(partition).unwrap() {
                            b5_driver::Action::Permit => {
                                let started = Instant::now();
                                let wire = encode_measured_frame(sequence, &payload);
                                application.benchmark_write_frame(&wire).await.unwrap();
                                tracker.issue(sequence, started).unwrap();
                                driver.run.issued(partition).unwrap();
                                sequence += 1;
                            }
                            b5_driver::Action::Read => {
                                let expected = tracker.next_sequence().unwrap();
                                let response = application.benchmark_read_frame().await.unwrap();
                                decode_measured_frame(&response, expected, &payload).unwrap();
                                let started = tracker.complete(expected).unwrap();
                                driver.run.completed(partition, u64::try_from(started.elapsed().as_nanos()).unwrap()).unwrap();
                            }
                            b5_driver::Action::WaitUntil(deadline) => driver.idle_until(deadline).await.unwrap(),
                            b5_driver::Action::Draining => break,
                            b5_driver::Action::AwaitReady => driver.run.wait_ready().await.unwrap(),
                        }
                        continue;
                    }
                    while tracker.can_issue()
                        && (deadline.is_some_and(|value| Instant::now() < value)
                            || operation_limit.is_some_and(|value| tracker.sent() < value))
                    {
                        let started = Instant::now();
                        let wire = encode_measured_frame(sequence, &payload);
                        application.benchmark_write_frame(&wire).await.unwrap();
                        tracker.issue(sequence, started).unwrap();
                        sequence += 1;
                    }
                    let Some(expected) = tracker.next_sequence() else {
                        break;
                    };
                    let response = application.benchmark_read_frame().await.unwrap();
                    decode_measured_frame(&response, expected, &payload).unwrap();
                    let started = tracker.complete(expected).unwrap();
                    let latency = started.elapsed().as_nanos() as u64;
                    let completed = tracker.completed();
                    if let Some(telemetry) = &soak_telemetry {
                        telemetry.record(latency);
                        if completed.is_multiple_of(64) {
                            b5_support::record_bounded_tail(&mut latencies, latency, 64);
                        }
                    } else {
                        latencies.push(latency);
                    }
                }
                if let Some(guard) = &mut failure_guard {
                    guard.disarm();
                }
                (
                    tracker.completed(),
                    latencies,
                    tracker.max_in_flight(),
                    sequence,
                    application,
                )
            });
        }
        if let Some(driver) = &paced {
            tokio::select! {
                _ = ready.wait() => {}
                _ = driver.run.wait_failed() => panic!("paced local warmup failed"),
            }
            driver.run.ready(group_ordinal).unwrap();
            driver.run.wait_ready().await.unwrap();
        } else {
            ready.wait().await;
        }
        if let Some(barrier) = group_barrier {
            barrier.wait();
        }
        b1_support::counter_phase(counter_control, "measurement-start").unwrap();
        let before = nbsr_transport::diagnostics::global().snapshot();
        let measured_started = Instant::now();
        if let Some(driver) = &paced {
            tokio::select! {
                _ = measure.wait() => {}
                _ = driver.run.wait_failed() => panic!("paced local measurement readiness failed"),
            }
        } else {
            measure.wait().await;
        }
        let progress_stop = Arc::new(AtomicBool::new(false));
        let progress_notify = Arc::new(Notify::new());
        let progress_task = if let (Some(seconds), Some(telemetry)) =
            (progress_interval, soak_telemetry.clone())
        {
            let stop = Arc::clone(&progress_stop);
            let notify = Arc::clone(&progress_notify);
            Some(tokio::spawn(async move {
                let interval = Duration::from_secs_f64(seconds);
                let mut prior = measured_started;
                let mut window_index = 0_u64;
                let mut completed_total = 0_u64;
                loop {
                    tokio::select! {
                        () = tokio::time::sleep(interval) => {}
                        () = notify.notified() => {}
                    }
                    let now = Instant::now();
                    let interval_ns = now.duration_since(prior).as_nanos() as u64;
                    let elapsed_ns = now.duration_since(measured_started).as_nanos() as u64;
                    let window = telemetry.take_window(interval_ns);
                    if window.completed_operations > 0 {
                        window_index += 1;
                        completed_total += window.completed_operations;
                        let option = |value: Option<u64>| {
                            value.map_or_else(|| "null".into(), |number| number.to_string())
                        };
                        let goodput =
                            2.0 * window.completed_operations as f64 * payload_bytes as f64
                                / (interval_ns as f64 / 1e9);
                        let operations_per_second =
                            window.completed_operations as f64 / (interval_ns as f64 / 1e9);
                        println!(
                            "{{\"event\":\"p2a_progress\",\"schema\":\"nbsr-b5-progress-v1\",\"window_index\":{window_index},\"elapsed_ns\":{elapsed_ns},\"interval_ns\":{interval_ns},\"completed_operations\":{},\"completed_total\":{completed_total},\"operations_per_second\":{operations_per_second},\"request_messages_per_second\":{operations_per_second},\"response_messages_per_second\":{operations_per_second},\"goodput_bytes_per_second\":{goodput},\"p50_latency_ns\":{},\"p95_latency_ns\":{},\"p99_latency_ns\":{},\"latency_sample_count\":{},\"latency_sample_stride\":{},\"errors\":0,\"timeouts\":0}}",
                            window.completed_operations,
                            option(window.p50_latency_ns),
                            option(window.p95_latency_ns),
                            option(window.p99_latency_ns),
                            window.sample_count,
                            window.latency_sample_stride,
                        );
                        emit_diagnostic(elapsed_ns.into(), "steady");
                    }
                    prior = now;
                    if stop.load(Ordering::Relaxed) {
                        break;
                    }
                }
            }))
        } else {
            None
        };
        let mut admission_latencies = Vec::with_capacity(mixed.scheduled as usize);
        let mut admission_lateness = Vec::with_capacity(mixed.scheduled as usize);
        let mut successful_admissions = 0_u64;
        let mut failed_admissions = 0_u64;
        let mut admission_timeouts = 0_u64;
        for admission_ordinal in 0..mixed.scheduled {
            let scheduled = measured_started
                + Duration::from_secs_f64(admission_ordinal as f64 / mixed.rate_per_second);
            tokio::time::sleep_until(scheduled.into()).await;
            admission_lateness.push(
                Instant::now()
                    .saturating_duration_since(scheduled)
                    .as_nanos() as u64,
            );
            let started = Instant::now();
            let index = stream_count + admission_ordinal;
            let admitted = tokio::time::timeout(Duration::from_secs(5), async {
                let stream = stream_open(index);
                session
                    .authorize_stream_open(channel, &stream)
                    .map_err(|_| ())?;
                control.send_envelope(&stream).await.map_err(|_| ())?;
                let accepted = control
                    .receive_envelope(CoreV02Limits::default())
                    .await
                    .map_err(|_| ())?;
                session
                    .confirm_stream_accept(channel, &accepted)
                    .map_err(|_| ())?;
                let permit = session
                    .application_stream_permit(channel, 4 + 4 * index)
                    .map_err(|_| ())?;
                let mut application = connection
                    .open_session_stream(&permit)
                    .await
                    .map_err(|_| ())?;
                let response = application
                    .send_and_receive(&payload)
                    .await
                    .map_err(|_| ())?;
                if response != payload {
                    return Err(());
                }
                session
                    .release_stream(channel, 4 + 4 * index)
                    .map_err(|_| ())?;
                while session.pop_audit_event().is_some() {}
                Ok::<(), ()>(())
            })
            .await;
            match admitted {
                Ok(Ok(())) => {
                    successful_admissions += 1;
                    admission_latencies.push(started.elapsed().as_nanos() as u64);
                }
                Ok(Err(())) => {
                    failed_admissions += 1;
                    break;
                }
                Err(_) => {
                    admission_timeouts += 1;
                    break;
                }
            }
        }
        let mut completed = 0_u64;
        let mut latencies = Vec::new();
        let mut max_outstanding_observed = 0_usize;
        let mut established_streams = Vec::with_capacity(stream_count as usize);
        loop {
            let result = if let Some(driver) = &paced {
                tokio::select! {
                    result = tasks.join_next() => result,
                    _ = driver.run.wait_failed() => panic!("paced stream failed"),
                }
            } else {
                tasks.join_next().await
            };
            let Some(result) = result else {
                break;
            };
            let (count, mut values, max_outstanding, sequence, application) = result.unwrap();
            completed += count;
            latencies.append(&mut values);
            max_outstanding_observed = max_outstanding_observed.max(max_outstanding);
            established_streams.push((sequence, application));
        }
        progress_stop.store(true, Ordering::Relaxed);
        progress_notify.notify_one();
        if let Some(task) = progress_task {
            task.await.unwrap();
        }
        let measured_ns = measured_started.elapsed().as_nanos();
        if let Some(driver) = &paced {
            driver.run.drained(group_ordinal).unwrap();
            driver.run.wait_postflight().await.unwrap();
        }
        for (sequence, application) in &mut established_streams {
            let postflight = encode_frame(*sequence, &payload);
            application
                .benchmark_write_frame(&postflight)
                .await
                .unwrap();
            let response = application.benchmark_read_frame().await.unwrap();
            decode_frame(&response, *sequence, payload.len()).unwrap();
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
        b1_support::counter_phase(counter_control, "measurement-stop").unwrap();
        drop(established_streams);
        if paced.is_some() {
            drop(session);
            connection.close().await.unwrap();
            if let Some(guard) = paced_guard {
                guard.finish().unwrap();
            }
            return;
        }
        let after = nbsr_transport::diagnostics::global().snapshot();
        latencies.sort_unstable();
        admission_latencies.sort_unstable();
        admission_lateness.sort_unstable();
        let percentile = |p: f64| latencies[((latencies.len() - 1) as f64 * p).round() as usize];
        let admission_percentile = |p: f64| {
            b4_support::percentile(&admission_latencies, p)
                .map_or_else(|| "null".into(), |value| value.to_string())
        };
        let max_admission_lateness = admission_lateness.last().copied().unwrap_or(0);
        let latency_stride = if progress_interval.is_some() { 64 } else { 1 };
        let final_record = format!(
            "{{\"schema\":\"nbsr-p2a-repeat-v2\",\"path\":\"nbsr\",\"streams\":{stream_count},\"payload_bytes\":{payload_bytes},\"model\":\"bounded-outstanding-per-stream\",\"outstanding_per_stream\":{outstanding_per_stream},\"configured_total_outstanding\":{},\"max_outstanding_per_stream_observed\":{max_outstanding_observed},\"completed_operations\":{completed},\"measured_ns\":{measured_ns},\"p50_latency_ns\":{},\"p95_latency_ns\":{},\"p99_latency_ns\":{},\"latency_sample_count\":{},\"latency_sample_stride\":{latency_stride},\"scheduled_admissions\":{},\"successful_admissions\":{},\"failed_admissions\":{},\"admission_timeouts\":{},\"admission_p50_latency_ns\":{},\"admission_p95_latency_ns\":{},\"admission_p99_latency_ns\":{},\"max_admission_start_lateness_ns\":{},\"errors\":{},\"missing\":0,\"duplicates\":0,\"corrupt\":0,\"wrong_request\":0,\"transport_sessions_created_delta\":{},\"service_channels_created_delta\":{},\"application_streams_created_delta\":{},\"replay_entries_delta\":{}}}",
            stream_count as usize * outstanding_per_stream,
            percentile(0.50),
            percentile(0.95),
            percentile(0.99),
            latencies.len(),
            mixed.scheduled,
            successful_admissions,
            failed_admissions,
            admission_timeouts,
            admission_percentile(0.50),
            admission_percentile(0.95),
            admission_percentile(0.99),
            max_admission_lateness,
            failed_admissions,
            after.transport_sessions.created - before.transport_sessions.created,
            after.service_channels.created - before.service_channels.created,
            after.application_streams.created - before.application_streams.created,
            after.replay_state.current_entries as i64 - before.replay_state.current_entries as i64
        );
        drop(session);
        connection.close().await.unwrap();
        if cooldown_seconds > 0.0 {
            emit_diagnostic(measured_started.elapsed().as_nanos(), "cooldown_start");
            let cooldown_deadline = Instant::now() + Duration::from_secs_f64(cooldown_seconds);
            while Instant::now() < cooldown_deadline {
                tokio::time::sleep(Duration::from_secs(1)).await;
                emit_diagnostic(measured_started.elapsed().as_nanos(), "cooldown");
            }
            emit_diagnostic(measured_started.elapsed().as_nanos(), "post_cooldown");
        }
        println!("{final_record}");
        return;
    }
    let payload = vec![0x5a; payload_bytes];
    let mut records = if offered_rate.is_some() {
        Vec::new()
    } else {
        Vec::with_capacity(samples as usize)
    };
    let schedule_origin = offered_rate.map(|_| Instant::now());
    let diagnostic_origin = Instant::now();
    let mut next_diagnostic = Duration::ZERO;
    if diagnostics_enabled {
        emit_diagnostic(0, "initial");
        next_diagnostic = Duration::from_secs(1);
    }
    for index in 0..samples {
        let total = Instant::now();
        let (scheduled_ns, started_ns, start_lateness_ns) =
            if let (Some(rate), Some(origin)) = (offered_rate, schedule_origin) {
                let offset = Duration::from_secs_f64(index as f64 / rate);
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
        #[cfg(feature = "benchmark-harness")]
        let profile_prepare = Instant::now();
        let stream = stream_open(index);
        let prepared = session.authorize_stream_open(channel, &stream);
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::SourcePrepareAuthorize,
            profile_prepare.elapsed().as_nanos() as u64,
            prepared.is_ok(),
        );
        prepared.unwrap();
        let stream_started = Instant::now();
        #[cfg(feature = "benchmark-harness")]
        let profile_write = Instant::now();
        let sent = control.send_envelope(&stream).await;
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::SourceControlWrite,
            profile_write.elapsed().as_nanos() as u64,
            sent.is_ok(),
        );
        sent.unwrap();
        #[cfg(feature = "benchmark-harness")]
        let profile_wait = Instant::now();
        let received = control.receive_envelope(CoreV02Limits::default()).await;
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::SourceAdmissionWaitRead,
            profile_wait.elapsed().as_nanos() as u64,
            received.is_ok(),
        );
        let stream_accepted = received.unwrap();
        #[cfg(feature = "benchmark-harness")]
        let profile_confirm = Instant::now();
        let confirmed = session.confirm_stream_accept(channel, &stream_accepted);
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::SourceAdmissionConfirm,
            profile_confirm.elapsed().as_nanos() as u64,
            confirmed.is_ok(),
        );
        confirmed.unwrap();
        let stream_ns = stream_started.elapsed().as_nanos();
        let permit = session
            .application_stream_permit(channel, 4 + 4 * index)
            .unwrap();
        let opened = connection.open_session_stream(&permit).await;
        let mut application = opened.unwrap();
        let request_started = Instant::now();
        let response_result = application.send_and_receive(&payload).await;
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::SourceFirstExchange,
            request_started.elapsed().as_nanos() as u64,
            response_result.is_ok(),
        );
        let response = response_result.unwrap();
        let service_ns = request_started.elapsed().as_nanos();
        let request_ns = schedule_origin.map_or(service_ns, |origin| {
            origin.elapsed().as_nanos() - scheduled_ns
        });
        assert_eq!(response, payload);
        #[cfg(feature = "benchmark-harness")]
        let profile_release = Instant::now();
        let released = session.release_stream(channel, 4 + 4 * index);
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::SourceReleaseCleanup,
            profile_release.elapsed().as_nanos() as u64,
            released.is_ok(),
        );
        released.unwrap();
        let record = format!(
            "{{\"sample_id\":{index},\"success\":true,\"transport_handshake_ns\":{},\"stream_open_rtt_ns\":{stream_ns},\"request_latency_ns\":{request_ns},\"service_latency_ns\":{service_ns},\"scheduled_ns\":{scheduled_ns},\"started_ns\":{started_ns},\"completed_ns\":{},\"start_lateness_ns\":{start_lateness_ns},\"ttfab_ns\":{request_ns},\"total_scenario_ns\":{},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}",
            if index == 0 {
                handshake_ns.to_string()
            } else {
                "null".into()
            },
            schedule_origin.map_or(0, |origin| origin.elapsed().as_nanos()),
            total.elapsed().as_nanos()
        );
        if offered_rate.is_some() {
            println!("{record}");
        } else {
            records.push(record);
        }
        while session.pop_audit_event().is_some() {}
        if diagnostics_enabled && diagnostic_origin.elapsed() >= next_diagnostic {
            emit_diagnostic(diagnostic_origin.elapsed().as_nanos(), "load");
            next_diagnostic += Duration::from_secs(1);
        }
    }
    #[cfg(feature = "benchmark-harness")]
    if std::env::var_os("NBSR_P2B_PROFILE").is_some() {
        println!(
            "{}",
            nbsr_transport::lifecycle_profile::global()
                .snapshot()
                .to_json("source")
        );
    }
    drop(session);
    connection.close().await.unwrap();
    if let Some(path) = post_load_completion_ack {
        fs::write(
            path,
            b"destination diagnostics measured transport complete\n",
        )
        .unwrap();
    }
    if post_load_hold_seconds > 0 {
        std::thread::sleep(Duration::from_secs(post_load_hold_seconds));
    }
    if diagnostics_enabled {
        if let Some(path) = completion_ack {
            fs::write(path, b"diagnostic source completed measured transport\n").unwrap();
        }
        emit_diagnostic(diagnostic_origin.elapsed().as_nanos(), "drain_start");
        let drain_deadline = Instant::now() + Duration::from_secs(drain_seconds);
        while Instant::now() < drain_deadline {
            tokio::time::sleep(Duration::from_secs(1)).await;
            emit_diagnostic(diagnostic_origin.elapsed().as_nanos(), "drain");
        }
        emit_diagnostic(diagnostic_origin.elapsed().as_nanos(), "post_drain");
    }
    for record in records {
        println!("{record}");
    }
}

#[cfg(feature = "benchmark-harness")]
fn main() {
    if optional_argument("--b3-allocator-directory").is_some() {
        allocator_snapshot::ensure_supported().expect("supported allocator observer");
        assert!(
            optional_argument("--lifecycle-authority-dir").is_some()
                && optional_argument("--hold-for-release").is_some()
                && optional_argument("--lifecycle-clients").is_none(),
            "allocator observer requires sequential held lifecycle mode"
        );
    }
    external_bind::client_bind(env::args()).expect("valid benchmark client bind");
    let workers = parse_runtime_workers(env::args()).expect("valid --p2a-runtime-workers");
    if let Some(driver) =
        b5_driver::prepare(env::args()).expect("valid paced benchmark configuration")
    {
        let groups = parse_group_count(env::args()).expect("valid --p2a-groups");
        let cleanup_report =
            post_close::prepare(optional_argument("--p2a-cleanup-report").map(PathBuf::from));
        let ownership_observer = optional_argument("--diagnostics").map(|_| {
            nbsr_transport::diagnostics::enable_global();
            Arc::new(|elapsed: u64, phase: &'static str| {
                use std::io::Write as _;
                let line = nbsr_transport::diagnostics::global().snapshot().json_line(
                    "source",
                    elapsed.into(),
                    phase,
                );
                let mut output = std::io::stdout().lock();
                writeln!(output, "{line}")?;
                output.flush()
            }) as b5_driver::OwnershipObserver
        });
        let publisher = if ownership_observer.is_some() {
            driver.start_publisher_with_observer(ownership_observer)
        } else {
            driver.start_publisher()
        }
        .expect("paced publisher");
        if groups == 1 {
            build_benchmark_runtime(workers)
                .expect("paced benchmark runtime")
                .block_on(async {
                    tokio::select! {
                        () = run(None, 0, None, Some(Arc::clone(&driver))) => {}
                        _ = driver.run.wait_failed() => panic!("paced group failed"),
                    }
                    post_close::write(cleanup_report.as_deref(), "source", "runtime_alive");
                });
        } else {
            let handles: Vec<_> = (0..groups)
                .map(|ordinal| {
                    let driver = Arc::clone(&driver);
                    std::thread::spawn(move || {
                        let mut failure = driver.failure_guard();
                        build_benchmark_runtime(1)
                            .expect("paced group runtime")
                            .block_on(async {
                                tokio::select! {
                                    () = run(None, ordinal, None, Some(Arc::clone(&driver))) => {}
                                    _ = driver.run.wait_failed() => panic!("paced group failed"),
                                }
                            });
                        failure.disarm();
                    })
                })
                .collect();
            let mut failed = false;
            for handle in handles {
                if handle.join().is_err() {
                    driver.run.fail();
                    failed = true;
                }
            }
            assert!(!failed, "paced NBSR group failed");
            emit_diagnostic(0, "group_cleanup");
            post_close::write(
                cleanup_report.as_deref(),
                "source",
                "all_group_runtimes_joined",
            );
        }
        publisher
            .join()
            .expect("paced publisher thread")
            .expect("paced publication");
        println!(
            "{}",
            driver
                .final_record_after_joins(r#"{"status":"SEPARATE_REPORT_REQUIRED"}"#)
                .expect("paced final evidence")
        );
        return;
    }
    if let Some(logical_clients) = optional_argument("--lifecycle-clients") {
        let logical_clients = logical_clients
            .parse::<usize>()
            .expect("valid --lifecycle-clients");
        let live_bundles = cfg!(feature = "benchmark-harness")
            && optional_argument("--b3-keep-alive-seconds").as_deref() == Some("1")
            && optional_argument("--hold-for-release").is_some();
        let maximum_clients = if live_bundles { 4096 } else { 1024 };
        assert!((1..=maximum_clients).contains(&logical_clients));
        let timeline = handshake_timeline::Region::open(logical_clients, 1);
        let shards = lifecycle_shards::parse_shards(
            optional_argument("--lifecycle-source-shards").as_deref(),
        )
        .expect("valid lifecycle source shards");
        let lifecycle_root = optional_argument("--lifecycle-authority-dir")
            .map(PathBuf::from)
            .expect("lifecycle authority directory");
        let (coordinator, completion) =
            CompletionCoordinator::with_evidence(logical_clients, lifecycle_root);
        let release_gate = batch_release::BatchRelease::from_options(
            optional_argument("--lifecycle-release-batch")
                .map(|value| value.parse::<usize>().expect("valid release batch")),
            optional_argument("--lifecycle-release-interval-ms")
                .map(|value| value.parse::<u64>().expect("valid release interval")),
            optional_argument("--lifecycle-offered-rate")
                .map(|value| value.parse::<f64>().expect("valid offered rate")),
        )
        .expect("valid diagnostic lifecycle release configuration");
        if shards == 1 {
            eprintln!(
                "{{\"event\":\"lifecycle_source_shard\",\"shard\":0,\"thread_id\":{}}}",
                lifecycle_shards::current_os_thread_id()
            );
            build_benchmark_runtime(1)
                .expect("lifecycle driver Tokio runtime")
                .block_on(run_lifecycle_clients(
                    (0..logical_clients).collect(),
                    timeline,
                    release_gate,
                    completion.clone(),
                ));
        } else {
            let shard_completion = completion.clone();
            lifecycle_shards::run_fixed_shards(shards, move |shard| {
                let clients = lifecycle_shards::assigned_clients(logical_clients, shards, shard)
                    .expect("valid lifecycle shard assignment");
                run_lifecycle_clients(
                    clients,
                    timeline.clone(),
                    release_gate,
                    shard_completion.clone(),
                )
            })
            .expect("bounded lifecycle source shards");
        }
        drop(completion);
        let summary = build_benchmark_runtime(1)
            .expect("lifecycle completion runtime")
            .block_on(coordinator.finish(Duration::from_secs(10)))
            .expect("bounded lifecycle evidence completion");
        assert_eq!(summary.recorded, logical_clients);
        assert_eq!(summary.written, logical_clients);
        assert!(summary.writer_thread.is_some());
        if optional_argument("--diagnostics").is_some() {
            emit_diagnostic(0, "lifecycle_cleanup");
        }
        return;
    }
    let groups = parse_group_count(env::args()).expect("valid --p2a-groups");
    let cleanup_report =
        post_close::prepare(optional_argument("--p2a-cleanup-report").map(PathBuf::from));
    if groups > 1 {
        run_current_thread_groups(groups, |ordinal, barrier| async move {
            run(Some(barrier), ordinal, None, None).await
        })
        .expect("independently authorized NBSR benchmark groups");
        emit_diagnostic(0, "group_cleanup");
        post_close::write(
            cleanup_report.as_deref(),
            "source",
            "all_group_runtimes_joined",
        );
        return;
    }
    build_benchmark_runtime(workers)
        .expect("benchmark Tokio runtime")
        .block_on(async {
            run(None, 0, None, None).await;
            post_close::write(cleanup_report.as_deref(), "source", "runtime_alive");
        });
    if optional_argument("--lifecycle-authority-dir").is_some()
        && optional_argument("--diagnostics").is_some()
    {
        emit_diagnostic(0, "lifecycle_cleanup");
    }
}

#[cfg(not(feature = "benchmark-harness"))]
#[tokio::main(flavor = "current_thread")]
async fn main() {
    assert!(
        optional_argument("--b3-allocator-directory").is_none(),
        "allocator observer requires benchmark-harness"
    );
    run(None, 0, None).await;
}

trait ReadBytes {
    fn read_bytes(&self) -> Vec<u8>;
}
impl ReadBytes for PathBuf {
    fn read_bytes(&self) -> Vec<u8> {
        fs::read(self).unwrap()
    }
}
