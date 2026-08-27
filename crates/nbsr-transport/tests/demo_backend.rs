use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Envelope,
    CoreV02Limits, DestinationAdmission, EdgeIdentity, EdgeRole,
    LocalFederationAdmissionAttestations, PeerPolicy, RouteGrantIssuer, STREAM_CREDIT_PROFILE_ID,
    SharedControlSession, TransportListener, TrustProfileId, build_client_config,
    build_server_config, connect, decode_control_envelope,
};
use sha2::{Digest, Sha256};

#[allow(dead_code)]
#[path = "../src/bin/wp8_interop_server.rs"]
mod interop_server;
mod support;

use interop_server::run_verified_executable_for_test;
use interop_server::{
    DemoBackendError, DemoBackendThreadFailure, accept_configured_route, authorities, edge_hello,
    ensure_demo_backend_binding, ensure_runtime_admission_binding,
    ensure_runtime_route_grant_binding, issuer, load_demo_backend_map,
    load_runtime_admission_config, open_verified_executable_for_test, policy, relay_demo_backend,
    relay_demo_backend_with_timeout, route_accept, run_demo_backend, run_demo_backend_connector,
    run_demo_backend_server_operation_with_timeout, run_demo_backend_with_thread_failure,
    run_demo_backend_with_timeout, verified_executable_spawn_path_for_test,
    verify_executable_with_limit_for_test,
};

fn runtime_admission_text() -> String {
    let proof_public = [0x31_u8; 32];
    let proof_thumbprint = Sha256::digest(proof_public);
    format!(
        "NBSR-RUNTIME-ADMISSION-v1\nsource_operator=source.operator\nsource_edge=source.edge\ndestination_operator=destination.operator\ndestination_edge=destination.edge\nservice_identity=nbsr-demo-service-a-v1\nservice_digest={}\ntransport=tcp\nport=8080\nrecord_sequence=1\npolicy_hash={}\nnow=1893456000\nproof_thumbprint={}\nproof_public_key={}\nedge_nonce={}\nissuer_kid=nbsr-demo-route-grant-v1\nissuer_public_key={}\n",
        "07ed4ff0a2365cc91649cf8a9405d2f1cd1261fcb201a922acdbf4f4bcf213b5",
        hex32(Sha256::digest(b"demo-policy-v1").into()),
        hex32(proof_thumbprint.into()),
        hex32(proof_public),
        hex32([0x80; 32]),
        hex32([0x41; 32]),
    )
}

fn hex32(value: [u8; 32]) -> String {
    value.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[test]
fn runtime_admission_config_is_strict_public_policy_and_issuer_trust() {
    let root = TestRoot::new();
    let path = root.join("admission.conf");
    fs::write(&path, runtime_admission_text()).unwrap();
    let loaded = load_runtime_admission_config(&path).expect("strict runtime admission config");
    assert_eq!(loaded.policy.authorized_services.len(), 1);
    assert_eq!(loaded.service_identity, "nbsr-demo-service-a-v1");
    assert_eq!(loaded.transport, "tcp");
    assert_eq!(loaded.port, 8080);
    assert_eq!(loaded.trusted_issuer.kid, b"nbsr-demo-route-grant-v1");
    assert_eq!(loaded.policy.client_session_public_key, [0x31; 32]);
}

#[test]
fn runtime_admission_config_rejects_malformed_unknown_duplicate_private_and_oversized_inputs() {
    let root = TestRoot::new();
    let cases = [
        ("unknown", runtime_admission_text() + "unknown=value\n"),
        ("duplicate", runtime_admission_text() + "port=8080\n"),
        ("private", runtime_admission_text() + "private_key=00\n"),
        (
            "backend",
            runtime_admission_text() + "executable=C:\\backend.exe\n",
        ),
        (
            "bad hash",
            runtime_admission_text().replace("service_digest=07", "service_digest=zz"),
        ),
        (
            "bad kid",
            runtime_admission_text().replace("issuer_kid=nbsr", "issuer_kid=../nbsr"),
        ),
        (
            "path-like identity",
            runtime_admission_text().replace(
                "service_identity=nbsr-demo-service-a-v1",
                "service_identity=..",
            ),
        ),
        (
            "proof mismatch",
            runtime_admission_text().replace("proof_thumbprint=", "proof_thumbprint=00"),
        ),
        ("oversized", "x".repeat(16_385)),
    ];
    for (name, contents) in cases {
        let file_name = format!("{name}.conf");
        let path = root.join(&file_name);
        fs::write(&path, contents).unwrap();
        assert!(
            load_runtime_admission_config(&path).is_err(),
            "accepted {name}"
        );
    }
}

#[test]
fn historical_admission_defaults_are_unchanged_without_runtime_config() {
    assert!(policy().authorized_services.contains_key("service.example"));
    assert_eq!(issuer().kid, b"nbsr-test-route-grant-key");
}

#[tokio::test]
async fn runtime_admission_does_not_reuse_historical_federation_attestations() {
    let ConnectorSetup {
        mut destination_session,
        route,
        source,
        destination,
        listener,
        ..
    } = connector_setup().await;
    let root = TestRoot::new();
    let path = root.join("runtime.conf");
    fs::write(&path, historical_runtime_admission_text(&issuer())).unwrap();
    let config = load_runtime_admission_config(&path).unwrap();
    assert!(
        accept_configured_route(
            &mut destination_session,
            &route,
            &federation_attestations(),
            Some(&config),
        )
        .is_err(),
        "runtime admission must require the non-federated runtime RouteOpen path"
    );
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

fn historical_runtime_admission_text(trusted: &RouteGrantIssuer) -> String {
    let admission = policy();
    let service = admission
        .authorized_services
        .get("service.example")
        .unwrap();
    let service_digest = federated_route_open()
        .validated_route_grant_service_digest(&[issuer()])
        .unwrap();
    let proof_thumbprint: [u8; 32] = Sha256::digest(admission.client_session_public_key).into();
    format!(
        "NBSR-RUNTIME-ADMISSION-v1\nsource_operator={}\nsource_edge={}\ndestination_operator={}\ndestination_edge={}\nservice_identity=service.example\nservice_digest={}\ntransport=tcp\nport=8443\nrecord_sequence={}\npolicy_hash={}\nnow={}\nproof_thumbprint={}\nproof_public_key={}\nedge_nonce={}\nissuer_kid={}\nissuer_public_key={}\n",
        admission.source_operator_id,
        admission.source_edge_id,
        admission.destination_operator_id,
        admission.destination_edge_id,
        hex32(service_digest),
        service.accepted_record_sequence,
        hex32(service.policy_hash),
        admission.now,
        hex32(proof_thumbprint),
        hex32(admission.client_session_public_key),
        hex32(admission.edge_nonce),
        String::from_utf8(trusted.kid.clone()).unwrap(),
        hex32(trusted.public_key),
    )
}

#[test]
fn runtime_issuer_trust_is_local_and_rejects_kid_or_public_key_disagreement() {
    let root = TestRoot::new();
    let route = federated_route_open();
    let attestations = federation_attestations();
    for (name, trusted, accepted) in [
        ("exact", issuer(), true),
        (
            "kid",
            RouteGrantIssuer {
                kid: b"other-route-grant-key".to_vec(),
                ..issuer()
            },
            false,
        ),
        (
            "public",
            RouteGrantIssuer {
                public_key: [0x42; 32],
                ..issuer()
            },
            false,
        ),
    ] {
        let file_name = format!("issuer-{name}.conf");
        let path = root.join(&file_name);
        fs::write(&path, historical_runtime_admission_text(&trusted)).unwrap();
        let config = load_runtime_admission_config(&path).unwrap();
        let mut admission =
            DestinationAdmission::new_federated(config.policy.clone(), authorities()).unwrap();
        let result = admission.admit_federated_route_open(
            &route,
            &[config.trusted_issuer],
            config.policy.now,
            &attestations,
        );
        assert_eq!(result.is_ok(), accepted, "issuer case {name}: {result:?}");
    }
}

#[test]
fn runtime_service_digest_must_match_the_locally_trusted_signed_grant() {
    let root = TestRoot::new();
    let path = root.join("digest.conf");
    fs::write(&path, historical_runtime_admission_text(&issuer())).unwrap();
    let config = load_runtime_admission_config(&path).unwrap();
    let route = federated_route_open();
    assert_eq!(ensure_runtime_route_grant_binding(&config, &route), Ok(()));
    let mut wrong = config;
    wrong.service_digest[0] ^= 1;
    assert_eq!(
        ensure_runtime_route_grant_binding(&wrong, &route),
        Err(DemoBackendError::ServiceMismatch)
    );
}

#[test]
fn runtime_proof_public_identity_is_locally_pinned() {
    let root = TestRoot::new();
    let path = root.join("proof.conf");
    fs::write(&path, historical_runtime_admission_text(&issuer())).unwrap();
    let mut config = load_runtime_admission_config(&path).unwrap();
    let wrong_public = [0x42; 32];
    config.policy.client_session_public_key = wrong_public;
    config.proof_thumbprint = Sha256::digest(wrong_public).into();
    let mut admission =
        DestinationAdmission::new_federated(config.policy.clone(), authorities()).unwrap();
    assert!(
        admission
            .admit_federated_route_open(
                &federated_route_open(),
                &[config.trusted_issuer],
                config.policy.now,
                &federation_attestations(),
            )
            .is_err()
    );
}

#[test]
fn runtime_admission_binding_rejects_service_transport_and_port_disagreement() {
    let root = TestRoot::new();
    let path = root.join("admission.conf");
    fs::write(&path, runtime_admission_text()).unwrap();
    let config = load_runtime_admission_config(&path).unwrap();
    let accepted = ActiveChannel {
        channel_id: [1; 16],
        route_id: [2; 16],
        service_id: config.service_identity.clone(),
        route_grant_digest: [3; 32],
        transport: config.transport.clone(),
        port: config.port,
    };
    assert_eq!(ensure_runtime_admission_binding(&config, &accepted), Ok(()));
    for candidate in [
        ActiveChannel {
            service_id: "other".into(),
            ..accepted.clone()
        },
        ActiveChannel {
            transport: "udp".into(),
            ..accepted.clone()
        },
        ActiveChannel {
            port: 8443,
            ..accepted.clone()
        },
    ] {
        assert_eq!(
            ensure_runtime_admission_binding(&config, &candidate),
            Err(DemoBackendError::ServiceMismatch)
        );
    }
}

const REQUEST: &[u8] =
    b"GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nUser-Agent: rust-test\r\n\r\n";
const RESPONSE: &[u8] = b"HTTP/1.1 200 OK\r\nContent-Length: 33\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nhello from service-a through NBSR";

static DEMO_BACKEND_TEST_LOCK: Mutex<()> = Mutex::new(());

struct TestRoot {
    path: PathBuf,
    _serial: MutexGuard<'static, ()>,
}

impl TestRoot {
    fn new() -> Self {
        let serial = DEMO_BACKEND_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path =
            std::env::temp_dir().join(format!("nbsr-demo-backend-{}-{unique}", std::process::id()));
        fs::create_dir_all(&path).unwrap();
        Self {
            path,
            _serial: serial,
        }
    }

    fn join(&self, name: &str) -> PathBuf {
        self.path.join(name)
    }
}

impl Drop for TestRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

fn executable_name(name: &str) -> String {
    if cfg!(windows) {
        format!("{name}.exe")
    } else {
        name.to_owned()
    }
}

fn build_go_backend(root: &TestRoot, name: &str) -> PathBuf {
    let output = root.join(&executable_name(name));
    let demo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../client/nbsr-go-client/demo");
    let status = Command::new("go")
        .current_dir(demo)
        .args(["build", "-o"])
        .arg(&output)
        .arg("./cmd/nbsr-demo-backend")
        .status()
        .expect("run Go compiler");
    assert!(status.success(), "build deterministic Go backend");
    output
}

fn build_lifecycle_helper(root: &TestRoot) -> PathBuf {
    let source = root.join("helper.go");
    fs::write(
        &source,
        r#"package main
import (
    "bytes"
    "fmt"
    "io"
    "os"
    "os/exec"
    "path/filepath"
    "strings"
    "time"
)
func main() {
    if len(os.Args) == 2 && os.Args[1] == "descendant-child" {
        time.Sleep(3 * time.Second)
        return
    }
    name := filepath.Base(os.Args[0])
    switch {
    case strings.Contains(name, "crash"):
        os.Exit(7)
    case strings.Contains(name, "hang"):
        time.Sleep(30 * time.Second)
    case strings.Contains(name, "marker"):
        _ = os.WriteFile(os.Args[0]+".started", []byte("started"), 0600)
        time.Sleep(30 * time.Second)
    case strings.Contains(name, "descendant"):
        child := exec.Command(os.Args[0], "descendant-child")
        child.Stdout = os.Stdout
        child.Stderr = os.Stderr
        if child.Start() == nil {
            _ = os.WriteFile(os.Args[0]+".descendant-started", []byte("started"), 0600)
        }
        time.Sleep(30 * time.Second)
    case strings.Contains(name, "oversize"):
        _, _ = io.Copy(io.Discard, os.Stdin)
        _, _ = os.Stdout.Write(bytes.Repeat([]byte{'x'}, 4097))
        _, _ = fmt.Fprintln(os.Stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok")
    }
}
"#,
    )
    .unwrap();
    let output = root.join(&executable_name("helper"));
    let status = Command::new("go")
        .arg("build")
        .arg("-o")
        .arg(&output)
        .arg(&source)
        .status()
        .expect("run Go compiler");
    assert!(status.success(), "build lifecycle helper");
    output
}

#[cfg(any(windows, target_os = "linux"))]
fn build_handle_probe_backend(root: &TestRoot, inherited_handle: usize) -> PathBuf {
    let source = root.join("handle-probe.go");
    fs::write(
        &source,
        format!(
            r#"package main
import (
    "fmt"
    "io"
    "os"
)
func main() {{
    sentinel := os.NewFile(uintptr({inherited_handle}), "sentinel")
    if sentinel != nil {{
        if _, err := sentinel.Write([]byte("inherited")); err == nil {{
            _ = sentinel.Sync()
        }}
    }}
    _, _ = io.Copy(io.Discard, os.Stdin)
    _, _ = os.Stdout.Write([]byte("HTTP/1.1 200 OK\r\nContent-Length: 33\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nhello from service-a through NBSR"))
    _, _ = fmt.Fprintln(os.Stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok")
}}
"#
        ),
    )
    .unwrap();
    let output = root.join(&executable_name("handle-probe"));
    let status = Command::new("go")
        .arg("build")
        .arg("-o")
        .arg(&output)
        .arg(&source)
        .status()
        .expect("run Go compiler");
    assert!(status.success(), "build inherited-handle probe");
    output
}

#[cfg(target_os = "linux")]
fn inheritable_sentinel(path: &Path) -> fs::File {
    use std::os::fd::AsRawFd;

    unsafe extern "C" {
        fn fcntl(fd: i32, command: i32, argument: i32) -> i32;
    }
    let sentinel = fs::OpenOptions::new()
        .create(true)
        .truncate(true)
        .read(true)
        .write(true)
        .open(path)
        .unwrap();
    assert_eq!(
        unsafe { fcntl(sentinel.as_raw_fd(), 2, 0) },
        0,
        "clear FD_CLOEXEC for inheritance sentinel"
    );
    assert!(
        PathBuf::from(format!("{}.descendant-started", descendant.display())).exists(),
        "lifecycle helper must start the stdio-retaining descendant"
    );
    sentinel
}

#[cfg(windows)]
fn inheritable_sentinel(path: &Path) -> std::os::windows::io::OwnedHandle {
    use std::ffi::c_void;
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::FromRawHandle;

    #[repr(C)]
    struct SecurityAttributes {
        length: u32,
        security_descriptor: *mut c_void,
        inherit_handle: i32,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreateFileW(
            file_name: *const u16,
            desired_access: u32,
            share_mode: u32,
            security_attributes: *mut SecurityAttributes,
            creation_disposition: u32,
            flags_and_attributes: u32,
            template_file: *mut c_void,
        ) -> *mut c_void;
    }
    let name = path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let mut attributes = SecurityAttributes {
        length: std::mem::size_of::<SecurityAttributes>() as u32,
        security_descriptor: std::ptr::null_mut(),
        inherit_handle: 1,
    };
    let raw = unsafe {
        CreateFileW(
            name.as_ptr(),
            0x4000_0000,
            0x0000_0001 | 0x0000_0002,
            &mut attributes,
            2,
            0x0000_0080,
            std::ptr::null_mut(),
        )
    };
    assert_ne!(raw as isize, -1, "create inheritable sentinel handle");
    unsafe { std::os::windows::io::OwnedHandle::from_raw_handle(raw) }
}

fn copy_executable(source: &Path, root: &TestRoot, name: &str) -> PathBuf {
    let target = root.join(&executable_name(name));
    fs::copy(source, &target).unwrap();
    target
}

fn sha256(path: &Path) -> String {
    Sha256::digest(fs::read(path).unwrap())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn write_map(root: &TestRoot, executable: &Path, service: &str, digest: &str) -> PathBuf {
    let path = root.join("backend.map");
    fs::write(
        &path,
        format!(
            "NBSR-DEMO-BACKEND-MAP-v1\nservice_id={service}\nexecutable={}\nsha256={digest}\n",
            executable.display()
        ),
    )
    .unwrap();
    path
}

fn channel(service: &str) -> ActiveChannel {
    ActiveChannel {
        channel_id: [0x40; 16],
        route_id: [0x20; 16],
        service_id: service.to_owned(),
        route_grant_digest: [0x11; 32],
        transport: "tcp".to_owned(),
        port: 8080,
    }
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

fn control_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    let policy = AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
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
    };
    ControlSession::new(
        connection,
        DestinationAdmission::new(policy).expect("valid admission policy"),
        vec![RouteGrantIssuer {
            kid: b"nbsr-test-route-grant-key".to_vec(),
            public_key: [
                0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
                0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
                0xf7, 0x07, 0x51, 0x1a,
            ],
        }],
        TrustProfileId::new("test-profile").expect("trust profile"),
    )
}

async fn connection_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).unwrap(),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .unwrap();
    let remote = listener.local_addr().unwrap();
    let (destination, source) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy, pki.source_material()).unwrap(),
            remote,
        )
    );
    (listener, source.unwrap(), destination.unwrap())
}

fn listener_without_peer() -> TransportListener {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).unwrap(),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .unwrap()
}

fn credited_session(
    connection: &nbsr_transport::AuthenticatedConnection,
) -> (SharedControlSession, ActiveChannel) {
    let mut session = control_session(connection);
    for fixture in ["client-hello.cbor", "edge-hello.cbor"] {
        let envelope = decode_control_envelope(
            &vector(&format!("artifacts/valid/envelopes/{fixture}")),
            CoreV02Limits::default(),
        )
        .unwrap();
        if fixture == "client-hello.cbor" {
            session.accept_client_hello(&envelope).unwrap();
        } else {
            session.confirm_edge_hello(&envelope).unwrap();
        }
    }
    let route_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-open.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let route_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-accept.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let channel = session.accept_route_open(&route_open).unwrap();
    session
        .select_stream_credit_profile(
            channel.channel_id,
            true,
            Some(STREAM_CREDIT_PROFILE_ID),
            false,
        )
        .unwrap();
    session.confirm_route_accept(&route_accept).unwrap();
    connection
        .bind_channel(&mut session, channel.channel_id)
        .unwrap();
    (SharedControlSession::new(session), channel)
}

async fn prime_control_stream(
    source: &nbsr_transport::AuthenticatedConnection,
    destination: &nbsr_transport::AuthenticatedConnection,
) {
    let hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let mut source_control = source.open_control_stream().await.unwrap();
    source_control.send_envelope(&hello).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
}

fn federation_attestations() -> LocalFederationAdmissionAttestations {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    LocalFederationAdmissionAttestations {
        source: fs::read(root.join("vectors/wp8-local-admission/source.cose")).unwrap(),
        destination: fs::read(root.join("vectors/wp8-local-admission/destination.cose")).unwrap(),
    }
}

fn federated_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    ControlSession::new(
        connection,
        DestinationAdmission::new_federated(policy(), authorities()).unwrap(),
        vec![issuer()],
        TrustProfileId::new("federation-dev-v1").unwrap(),
    )
}

fn federated_client_hello() -> CoreV02Envelope {
    let mut body = Vec::new();
    map_cbor(&mut body, 8);
    field_uint_cbor(&mut body, 0, 1);
    field_text_cbor(&mut body, 1, &policy().source_operator_id);
    field_text_cbor(&mut body, 2, "source.edge");
    field_text_cbor(&mut body, 3, &policy().destination_operator_id);
    field_text_cbor(&mut body, 4, "destination.edge");
    field_bytes_cbor(&mut body, 5, &(0x60..0x80).collect::<Vec<_>>());
    field_bytes_cbor(&mut body, 6, &policy().client_session_public_key);
    field_uint_cbor(&mut body, 7, 1_893_456_000);
    envelope_cbor(
        1,
        (0x00..0x10).collect::<Vec<_>>().try_into().unwrap(),
        1,
        body,
    )
}

fn federated_route_open() -> CoreV02Envelope {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let body = fs::read(root.join("vectors/wp8-f75-route-open/route-open-body.cbor")).unwrap();
    envelope_cbor(
        3,
        [
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
            0x0e, 0x10,
        ],
        2,
        body,
    )
}

fn envelope_cbor(message: u64, request: [u8; 16], sequence: u64, body: Vec<u8>) -> CoreV02Envelope {
    let mut wire = Vec::new();
    map_cbor(&mut wire, 6);
    field_uint_cbor(&mut wire, 0, 2);
    field_uint_cbor(&mut wire, 1, message);
    field_bytes_cbor(&mut wire, 2, &request);
    field_bytes_cbor(&mut wire, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint_cbor(&mut wire, 4, sequence);
    uint_cbor(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default()).unwrap()
}

fn field_uint_cbor(target: &mut Vec<u8>, key: u64, value: u64) {
    uint_cbor(target, key);
    uint_cbor(target, value);
}

fn field_bytes_cbor(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint_cbor(target, key);
    argument_cbor(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn field_text_cbor(target: &mut Vec<u8>, key: u64, value: &str) {
    uint_cbor(target, key);
    argument_cbor(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}

fn uint_cbor(target: &mut Vec<u8>, value: u64) {
    argument_cbor(target, 0, value);
}

fn map_cbor(target: &mut Vec<u8>, value: u64) {
    argument_cbor(target, 5, value);
}

fn argument_cbor(target: &mut Vec<u8>, major: u8, value: u64) {
    let initial = major << 5;
    match value {
        0..=23 => target.push(initial | value as u8),
        24..=0xff => target.extend_from_slice(&[initial | 24, value as u8]),
        0x100..=0xffff => {
            target.push(initial | 25);
            target.extend_from_slice(&(value as u16).to_be_bytes());
        }
        0x1_0000..=0xffff_ffff => {
            target.push(initial | 26);
            target.extend_from_slice(&(value as u32).to_be_bytes());
        }
        _ => {
            target.push(initial | 27);
            target.extend_from_slice(&value.to_be_bytes());
        }
    }
}

async fn federated_credited_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
    SharedControlSession,
    SharedControlSession,
    ActiveChannel,
    ActiveChannel,
) {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.unwrap();
    let hello = federated_client_hello();
    source_control.send_envelope(&hello).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    let mut destination_session = federated_session(&destination);
    destination_session
        .accept_client_hello(
            &destination_control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap(),
        )
        .unwrap();
    let edge = edge_hello();
    destination_session.confirm_edge_hello(&edge).unwrap();
    destination_control.send_envelope(&edge).await.unwrap();
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();

    let route = federated_route_open();
    let attestations = federation_attestations();
    let mut source_session = federated_session(&source);
    source_session.accept_client_hello(&hello).unwrap();
    source_session.confirm_edge_hello(&edge).unwrap();
    let source_channel = source_session
        .accept_federated_route_open(&route, &attestations)
        .unwrap();
    source_control.send_envelope(&route).await.unwrap();
    let destination_channel = destination_session
        .accept_federated_route_open(
            &destination_control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap(),
            &attestations,
        )
        .unwrap();
    let accepted = route_accept();
    for session in [&mut source_session, &mut destination_session] {
        session
            .select_stream_credit_profile(
                destination_channel.channel_id,
                true,
                Some(STREAM_CREDIT_PROFILE_ID),
                false,
            )
            .unwrap();
        session.confirm_route_accept(&accepted).unwrap();
    }
    destination_control.send_envelope(&accepted).await.unwrap();
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    source
        .bind_channel(&mut source_session, source_channel.channel_id)
        .unwrap();
    destination
        .bind_channel(&mut destination_session, destination_channel.channel_id)
        .unwrap();
    (
        listener,
        source,
        destination,
        SharedControlSession::new(source_session),
        SharedControlSession::new(destination_session),
        source_channel,
        destination_channel,
    )
}

struct ConnectorSetup {
    listener: TransportListener,
    source: nbsr_transport::AuthenticatedConnection,
    destination: nbsr_transport::AuthenticatedConnection,
    source_control: nbsr_transport::ControlStream,
    destination_control: nbsr_transport::ControlStream,
    source_session: ControlSession,
    destination_session: ControlSession,
    source_channel: ActiveChannel,
    route: CoreV02Envelope,
}

async fn connector_setup() -> ConnectorSetup {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.unwrap();
    let hello = federated_client_hello();
    source_control.send_envelope(&hello).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    let mut destination_session = federated_session(&destination);
    destination_session
        .accept_client_hello(
            &destination_control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap(),
        )
        .unwrap();
    let edge = edge_hello();
    destination_session.confirm_edge_hello(&edge).unwrap();
    destination_control.send_envelope(&edge).await.unwrap();
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let route = federated_route_open();
    let mut source_session = federated_session(&source);
    source_session.accept_client_hello(&hello).unwrap();
    source_session.confirm_edge_hello(&edge).unwrap();
    let source_channel = source_session
        .accept_federated_route_open(&route, &federation_attestations())
        .unwrap();
    source_control.send_envelope(&route).await.unwrap();
    let route = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    ConnectorSetup {
        listener,
        source,
        destination,
        source_control,
        destination_control,
        source_session,
        destination_session,
        source_channel,
        route,
    }
}

async fn activate_connector_source(
    source: &nbsr_transport::AuthenticatedConnection,
    source_control: &mut nbsr_transport::ControlStream,
    source_session: &mut ControlSession,
    source_channel: &ActiveChannel,
) {
    let accepted = source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    source_session
        .select_stream_credit_profile(
            source_channel.channel_id,
            true,
            Some(STREAM_CREDIT_PROFILE_ID),
            false,
        )
        .unwrap();
    source_session.confirm_route_accept(&accepted).unwrap();
    source
        .bind_channel(source_session, source_channel.channel_id)
        .unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn admitted_service_runs_one_pinned_backend_without_shell_expansion() {
    let root = TestRoot::new();
    let executable = build_go_backend(&root, "backend & not-a-command");
    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).expect("strict private map");
    ensure_demo_backend_binding(&map, &channel("service.example")).expect("admitted binding");

    let response = run_demo_backend(&map, &channel("service.example"), REQUEST)
        .await
        .expect("one child exchange");
    assert_eq!(response, RESPONSE);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn credited_application_stream_relays_to_backend_only_after_same_stream_accept() {
    let root = TestRoot::new();
    let executable = build_go_backend(&root, "credited-backend");
    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).unwrap();
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (source_session, source_channel) = credited_session(&source);
    let (destination_session, admitted_channel) = credited_session(&destination);
    assert_eq!(source_channel.channel_id, admitted_channel.channel_id);

    let (mut accepted, mut opened) = tokio::join!(
        destination
            .accept_credited_session_stream(&destination_session, admitted_channel.channel_id),
        source.open_credited_session_stream(&source_session, source_channel.channel_id),
    );
    let accepted = accepted.as_mut().expect("destination credited admission");
    let opened = opened.as_mut().expect("source sees same-stream ACCEPT");
    let (relayed, response) = tokio::join!(
        relay_demo_backend(accepted, &map, &admitted_channel),
        opened.send_and_receive(REQUEST),
    );
    assert_eq!(relayed.unwrap(), RESPONSE);
    assert_eq!(response.unwrap(), RESPONSE);

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn admitted_stream_withholding_payload_times_out_without_starting_child() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    let executable = copy_executable(&helper, &root, "marker-withheld");
    let marker = PathBuf::from(format!("{}.started", executable.display()));
    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).unwrap();
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (source_session, source_channel) = credited_session(&source);
    let (destination_session, admitted_channel) = credited_session(&destination);

    let (accepted, opened) = tokio::join!(
        destination
            .accept_credited_session_stream(&destination_session, admitted_channel.channel_id),
        source.open_credited_session_stream(&source_session, source_channel.channel_id),
    );
    let mut accepted = accepted.expect("destination credited admission");
    let _opened = opened.expect("source sees same-stream ACCEPT but withholds payload");
    assert_eq!(
        relay_demo_backend_with_timeout(
            &mut accepted,
            &map,
            &admitted_channel,
            Duration::from_millis(75),
        )
        .await,
        Err(DemoBackendError::TimedOut)
    );
    assert!(
        !marker.exists(),
        "withheld payload must not start backend child"
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn federated_route_and_same_stream_credit_gate_backend_spawn() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    let marker_executable = copy_executable(&helper, &root, "marker-pre-admission");
    let marker = PathBuf::from(format!("{}.started", marker_executable.display()));
    let marker_map_path = write_map(
        &root,
        &marker_executable,
        "service.example",
        &sha256(&marker_executable),
    );
    let marker_map = load_demo_backend_map(&marker_map_path).unwrap();

    let (denied_listener, denied_source, denied_destination) = connection_pair().await;
    let mut denied_session = federated_session(&denied_destination);
    let hello = federated_client_hello();
    denied_session.accept_client_hello(&hello).unwrap();
    denied_session.confirm_edge_hello(&edge_hello()).unwrap();
    let mut invalid_attestations = federation_attestations();
    invalid_attestations.source[0] ^= 1;
    assert!(
        denied_session
            .accept_federated_route_open(&federated_route_open(), &invalid_attestations)
            .is_err(),
        "invalid F75 evidence must deny route before backend selection"
    );
    assert!(!marker.exists(), "denied route must be zero-spawn");
    denied_source.close().await.unwrap();
    denied_destination.close().await.unwrap();
    denied_listener.close().await.unwrap();

    let (
        invalid_listener,
        invalid_source,
        invalid_destination,
        invalid_source_session,
        invalid_destination_session,
        invalid_source_channel,
        invalid_destination_channel,
    ) = federated_credited_pair().await;
    ensure_demo_backend_binding(&marker_map, &invalid_destination_channel).unwrap();
    let (destination_reject, source_reject) = tokio::join!(
        invalid_destination
            .accept_credited_session_stream(&invalid_destination_session, [0xee; 16],),
        invalid_source.open_credited_session_stream(
            &invalid_source_session,
            invalid_source_channel.channel_id,
        ),
    );
    assert!(destination_reject.is_err());
    assert!(source_reject.is_err());
    assert!(
        !marker.exists(),
        "invalid same-stream credit must be zero-spawn"
    );
    invalid_source.close().await.unwrap();
    invalid_destination.close().await.unwrap();
    invalid_listener.close().await.unwrap();

    let backend = build_go_backend(&root, "federated-backend");
    let backend_map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let backend_map = load_demo_backend_map(&backend_map_path).unwrap();
    let (
        listener,
        source,
        destination,
        source_session,
        destination_session,
        source_channel,
        destination_channel,
    ) = federated_credited_pair().await;
    let (accepted, opened) = tokio::join!(
        destination
            .accept_credited_session_stream(&destination_session, destination_channel.channel_id,),
        source.open_credited_session_stream(&source_session, source_channel.channel_id),
    );
    let mut accepted = accepted.unwrap();
    let mut opened = opened.unwrap();
    let (relayed, response) = tokio::join!(
        relay_demo_backend(&mut accepted, &backend_map, &destination_channel),
        opened.send_and_receive(REQUEST),
    );
    assert_eq!(relayed.unwrap(), RESPONSE);
    assert_eq!(response.unwrap(), RESPONSE);
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn backend_exiting_first_fails_application_stream_and_is_reaped() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    let crash = copy_executable(&helper, &root, "crash-application-stream");
    let map_path = write_map(&root, &crash, "service.example", &sha256(&crash));
    let map = load_demo_backend_map(&map_path).unwrap();
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (source_session, source_channel) = credited_session(&source);
    let (destination_session, destination_channel) = credited_session(&destination);
    let (accepted, opened) = tokio::join!(
        destination
            .accept_credited_session_stream(&destination_session, destination_channel.channel_id,),
        source.open_credited_session_stream(&source_session, source_channel.channel_id),
    );
    let accepted = accepted.unwrap();
    let mut opened = opened.unwrap();
    let relay_channel = destination_channel.clone();
    let (relayed, source_result) = tokio::join!(
        async move {
            let mut accepted = accepted;
            relay_demo_backend(&mut accepted, &map, &relay_channel).await
        },
        opened.send_and_receive(REQUEST),
    );
    assert_eq!(relayed, Err(DemoBackendError::ChildFailed));
    if let Ok(response) = source_result {
        assert!(response.is_empty(), "no backend response may be fabricated");
    }
    fs::remove_file(&crash).expect("backend-first child was reaped");
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[cfg(windows)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn backend_child_does_not_inherit_unlisted_parent_handle() {
    use std::os::windows::io::AsRawHandle;

    let root = TestRoot::new();
    let sentinel_path = root.join("inherited-handle-sentinel");
    let sentinel = inheritable_sentinel(&sentinel_path);
    let backend = build_handle_probe_backend(&root, sentinel.as_raw_handle() as usize);
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    assert_eq!(
        run_demo_backend(&map, &channel("service.example"), REQUEST).await,
        Ok(RESPONSE.to_vec())
    );
    assert_eq!(
        fs::read(&sentinel_path).unwrap(),
        Vec::<u8>::new(),
        "direct spawn must not inherit unrelated handles"
    );
    drop(sentinel);
}

#[cfg(target_os = "linux")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn linux_executes_sealed_verified_bytes_after_source_mutation() {
    let root = TestRoot::new();
    let backend = build_handle_probe_backend(&root, usize::MAX);
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    let verified = open_verified_executable_for_test(&map).unwrap();
    fs::write(&backend, b"mutated after verification").unwrap();
    assert_eq!(
        run_verified_executable_for_test(
            verified,
            &channel("service.example"),
            REQUEST,
            Duration::from_secs(5),
        )
        .await,
        Ok(RESPONSE.to_vec()),
        "execution must use immutable verified bytes, not the mutated source path"
    );
}

#[cfg(target_os = "linux")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn linux_backend_child_does_not_inherit_unlisted_descriptor() {
    use std::os::fd::AsRawFd;

    let root = TestRoot::new();
    let sentinel_path = root.join("linux-inherited-descriptor-sentinel");
    let sentinel = inheritable_sentinel(&sentinel_path);
    let backend = build_handle_probe_backend(&root, sentinel.as_raw_fd() as usize);
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    assert_eq!(
        run_demo_backend(&map, &channel("service.example"), REQUEST).await,
        Ok(RESPONSE.to_vec())
    );
    assert_eq!(
        fs::read(&sentinel_path).unwrap(),
        Vec::<u8>::new(),
        "direct spawn must mark unrelated descriptors close-on-exec"
    );
    drop(sentinel);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn mismatched_service_early_close_and_oversized_request_never_touch_executable() {
    let root = TestRoot::new();
    let executable = build_go_backend(&root, "backend");
    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).unwrap();
    fs::remove_file(&executable).expect("remove after map validation");

    assert_eq!(
        ensure_demo_backend_binding(&map, &channel("other.service")),
        Err(DemoBackendError::ServiceMismatch)
    );
    assert_eq!(
        run_demo_backend(&map, &channel("other.service"), REQUEST).await,
        Err(DemoBackendError::ServiceMismatch)
    );
    assert_eq!(
        run_demo_backend(&map, &channel("service.example"), b"").await,
        Err(DemoBackendError::EmptyRequest)
    );
    assert_eq!(
        run_demo_backend(&map, &channel("service.example"), &vec![b'x'; 4097]).await,
        Err(DemoBackendError::RequestTooLarge)
    );
}

#[test]
fn private_map_rejects_malformed_duplicate_injected_and_unpinned_entries() {
    let root = TestRoot::new();
    let executable = build_go_backend(&root, "backend");
    let digest = sha256(&executable);
    let cases = [
        "",
        "NBSR-DEMO-BACKEND-MAP-v1\nservice_id=service.example;evil\nexecutable=x\nsha256=00\n",
        "NBSR-DEMO-BACKEND-MAP-v1\nservice_id=service.example\nservice_id=other\nexecutable=x\nsha256=00\n",
        "NBSR-DEMO-BACKEND-MAP-v1\nservice_id=service.example\nexecutable=x\nsha256=00\narguments=--injected\n",
    ];
    for (index, contents) in cases.into_iter().enumerate() {
        let path = root.join(&format!("invalid-{index}.map"));
        fs::write(&path, contents).unwrap();
        assert_eq!(
            load_demo_backend_map(&path),
            Err(DemoBackendError::InvalidMap),
            "case {index}"
        );
    }

    let wrong_hash = write_map(&root, &executable, "service.example", &"00".repeat(32));
    assert_eq!(
        load_demo_backend_map(&wrong_hash),
        Err(DemoBackendError::ExecutableHashMismatch)
    );
    assert_ne!(digest, "00".repeat(32));
}

#[test]
fn map_and_executable_reads_reject_limit_plus_one_and_pin_spawn_handle() {
    let root = TestRoot::new();
    let oversized_map = root.join("oversized.map");
    fs::write(&oversized_map, vec![b'x'; 4097]).unwrap();
    assert_eq!(
        load_demo_backend_map(&oversized_map),
        Err(DemoBackendError::InvalidMap)
    );

    let executable = build_go_backend(&root, "bounded-executable");
    let length = fs::metadata(&executable).unwrap().len();
    assert_eq!(
        verify_executable_with_limit_for_test(&executable, length - 1),
        Err(DemoBackendError::SpawnFailed)
    );

    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).unwrap();
    let guard = open_verified_executable_for_test(&map).expect("verified spawn guard");
    #[cfg(windows)]
    {
        let staged = verified_executable_spawn_path_for_test(&guard);
        assert!(
            fs::OpenOptions::new()
                .write(true)
                .truncate(true)
                .open(staged)
                .is_err(),
            "staged executable handle must deny replacement writes"
        );
        assert!(
            fs::remove_file(staged).is_err(),
            "staged executable handle must deny delete/replace"
        );
    }
    drop(guard);
}

#[cfg(windows)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn windows_executes_private_staged_bytes_after_source_namespace_substitution() {
    let root = TestRoot::new();
    let source_dir = root.join("source");
    fs::create_dir(&source_dir).unwrap();
    let source = source_dir.join(executable_name("backend"));
    fs::copy(build_go_backend(&root, "staging-source"), &source).unwrap();
    let map_path = write_map(&root, &source, "service.example", &sha256(&source));
    let map = load_demo_backend_map(&map_path).unwrap();
    let verified = open_verified_executable_for_test(&map).unwrap();
    let staged = verified_executable_spawn_path_for_test(&verified).to_owned();

    assert_ne!(staged, fs::canonicalize(&source).unwrap());
    assert!(staged.starts_with(
        fs::canonicalize(std::env::current_exe().unwrap().parent().unwrap()).unwrap()
    ));
    fs::rename(&source_dir, root.join("source-held")).unwrap();
    fs::create_dir(&source_dir).unwrap();
    fs::write(
        source_dir.join(executable_name("backend")),
        b"substituted executable bytes",
    )
    .unwrap();

    assert_eq!(
        run_verified_executable_for_test(
            verified,
            &channel("service.example"),
            REQUEST,
            Duration::from_secs(5),
        )
        .await,
        Ok(RESPONSE.to_vec())
    );
    assert!(
        !staged.exists(),
        "staged executable must be cleaned after child completion"
    );
    assert!(
        !staged.parent().unwrap().exists(),
        "private staging directory must be cleaned"
    );
}

#[cfg(windows)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn windows_reparse_substitution_cannot_redirect_staged_execution() {
    use std::os::windows::fs::symlink_dir;

    let root = TestRoot::new();
    let source_dir = root.join("reparse-source");
    let replacement_dir = root.join("reparse-replacement");
    fs::create_dir(&source_dir).unwrap();
    fs::create_dir(&replacement_dir).unwrap();
    let source = source_dir.join(executable_name("backend"));
    fs::copy(build_go_backend(&root, "reparse-staging-source"), &source).unwrap();
    fs::write(
        replacement_dir.join(executable_name("backend")),
        b"replacement through reparse namespace",
    )
    .unwrap();
    let map_path = write_map(&root, &source, "service.example", &sha256(&source));
    let map = load_demo_backend_map(&map_path).unwrap();
    let verified = open_verified_executable_for_test(&map).unwrap();
    let staged = verified_executable_spawn_path_for_test(&verified).to_owned();

    fs::rename(&source_dir, root.join("reparse-source-held")).unwrap();
    symlink_dir(&replacement_dir, &source_dir)
        .expect("Windows developer mode or symlink privilege is required for reparse test");
    assert_eq!(
        run_verified_executable_for_test(
            verified,
            &channel("service.example"),
            REQUEST,
            Duration::from_secs(5),
        )
        .await,
        Ok(RESPONSE.to_vec())
    );
    assert!(!staged.exists());
    assert!(!staged.parent().unwrap().exists());
}

#[cfg(windows)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn windows_staging_churn_reaps_children_and_removes_each_private_copy() {
    let root = TestRoot::new();
    let source = build_go_backend(&root, "staging-churn");
    let map_path = write_map(&root, &source, "service.example", &sha256(&source));
    let map = load_demo_backend_map(&map_path).unwrap();

    for _ in 0..16 {
        let verified = open_verified_executable_for_test(&map).unwrap();
        let staged = verified_executable_spawn_path_for_test(&verified).to_owned();
        assert_eq!(
            run_verified_executable_for_test(
                verified,
                &channel("service.example"),
                REQUEST,
                Duration::from_secs(5),
            )
            .await,
            Ok(RESPONSE.to_vec())
        );
        assert!(!staged.exists());
        assert!(!staged.parent().unwrap().exists());
    }
    fs::remove_file(source).expect("all staged children were reaped");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn whole_operation_deadline_bounds_connection_accept_before_backend_admission() {
    let root = TestRoot::new();
    let backend = build_go_backend(&root, "never-spawned-before-admission");
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    let listener = listener_without_peer();
    let started = std::time::Instant::now();

    assert!(matches!(
        run_demo_backend_server_operation_with_timeout(&listener, &map, Duration::from_millis(75))
            .await,
        Err(DemoBackendError::TimedOut)
    ));
    assert!(started.elapsed() < Duration::from_secs(1));
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn whole_operation_deadline_bounds_peer_that_withholds_control_stream() {
    let root = TestRoot::new();
    let backend = build_go_backend(&root, "never-spawned-without-control");
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).unwrap(),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .unwrap();
    let remote = listener.local_addr().unwrap();
    let started = std::time::Instant::now();
    let (server, source) = tokio::join!(
        run_demo_backend_server_operation_with_timeout(&listener, &map, Duration::from_millis(150)),
        connect(
            build_client_config(source_policy, pki.source_material()).unwrap(),
            remote,
        )
    );
    assert!(matches!(server, Err(DemoBackendError::TimedOut)));
    assert!(started.elapsed() < Duration::from_secs(1));
    source.unwrap().close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn whole_operation_deadline_bounds_peer_that_withholds_route_open() {
    let root = TestRoot::new();
    let backend = build_go_backend(&root, "never-spawned-without-route");
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).unwrap(),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .unwrap();
    let remote = listener.local_addr().unwrap();
    let client = async {
        let source = connect(
            build_client_config(source_policy, pki.source_material()).unwrap(),
            remote,
        )
        .await
        .unwrap();
        let mut control = source.open_control_stream().await.unwrap();
        control
            .send_envelope(&federated_client_hello())
            .await
            .unwrap();
        control
            .receive_envelope(CoreV02Limits::default())
            .await
            .unwrap();
        tokio::time::sleep(Duration::from_millis(250)).await;
        source
    };
    let started = std::time::Instant::now();
    let (server, source) = tokio::join!(
        run_demo_backend_server_operation_with_timeout(&listener, &map, Duration::from_millis(150)),
        client,
    );
    assert!(matches!(server, Err(DemoBackendError::TimedOut)));
    assert!(started.elapsed() < Duration::from_secs(1));
    source.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn response_send_failure_after_backend_completion_reaps_child() {
    let root = TestRoot::new();
    let executable = build_go_backend(&root, "response-send-failure");
    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).unwrap();
    let (listener, source, destination) = connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let (source_session, source_channel) = credited_session(&source);
    let (destination_session, admitted_channel) = credited_session(&destination);
    let (accepted, opened) = tokio::join!(
        destination
            .accept_credited_session_stream(&destination_session, admitted_channel.channel_id,),
        source.open_credited_session_stream(&source_session, source_channel.channel_id),
    );
    let mut accepted = accepted.unwrap();
    let mut opened = opened.unwrap();
    opened.send_payload(REQUEST).await.unwrap();
    source.close().await.unwrap();

    assert_eq!(
        relay_demo_backend(&mut accepted, &map, &admitted_channel).await,
        Err(DemoBackendError::StreamFailed)
    );
    fs::remove_file(&executable).expect("response-send failure child was reaped");
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn child_crash_timeout_oversized_output_and_cancellation_are_reaped() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);

    let crash = copy_executable(&helper, &root, "crash");
    let crash_map_path = write_map(&root, &crash, "service.example", &sha256(&crash));
    let crash_map = load_demo_backend_map(&crash_map_path).unwrap();
    assert_eq!(
        run_demo_backend(&crash_map, &channel("service.example"), REQUEST).await,
        Err(DemoBackendError::ChildFailed)
    );
    fs::remove_file(&crash).expect("crashed child was reaped");

    let oversize = copy_executable(&helper, &root, "oversize");
    let oversize_map_path = write_map(&root, &oversize, "service.example", &sha256(&oversize));
    let oversize_map = load_demo_backend_map(&oversize_map_path).unwrap();
    assert_eq!(
        run_demo_backend(&oversize_map, &channel("service.example"), REQUEST).await,
        Err(DemoBackendError::ResponseTooLarge)
    );
    fs::remove_file(&oversize).expect("oversized child was reaped");

    let timed = copy_executable(&helper, &root, "hang-timeout");
    let timed_map_path = write_map(&root, &timed, "service.example", &sha256(&timed));
    let timed_map = load_demo_backend_map(&timed_map_path).unwrap();
    assert_eq!(
        run_demo_backend_with_timeout(
            &timed_map,
            &channel("service.example"),
            REQUEST,
            Duration::from_millis(100),
        )
        .await,
        Err(DemoBackendError::TimedOut)
    );
    fs::remove_file(&timed).expect("timed-out child was killed and reaped");

    let cancelled = copy_executable(&helper, &root, "hang-cancel");
    let cancelled_map_path = write_map(&root, &cancelled, "service.example", &sha256(&cancelled));
    let cancelled_map = load_demo_backend_map(&cancelled_map_path).unwrap();
    let task = tokio::spawn(async move {
        run_demo_backend_with_timeout(
            &cancelled_map,
            &channel("service.example"),
            REQUEST,
            Duration::from_secs(10),
        )
        .await
    });
    tokio::time::sleep(Duration::from_millis(100)).await;
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    let mut removed = false;
    for _ in 0..100 {
        match fs::remove_file(&cancelled) {
            Ok(()) => {
                removed = true;
                break;
            }
            Err(error)
                if error.kind() == io::ErrorKind::PermissionDenied
                    || error.raw_os_error() == Some(32) =>
            {
                tokio::time::sleep(Duration::from_millis(20)).await;
            }
            Err(error) => panic!("remove cancelled child: {error}"),
        }
    }
    assert!(removed, "cancelled child was not killed and reaped");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn timeout_kills_backend_process_tree_that_retains_stdio() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    let descendant = copy_executable(&helper, &root, "descendant-timeout");
    let map_path = write_map(&root, &descendant, "service.example", &sha256(&descendant));
    let map = load_demo_backend_map(&map_path).unwrap();
    let bounded = tokio::time::timeout(
        Duration::from_millis(750),
        run_demo_backend_with_timeout(
            &map,
            &channel("service.example"),
            REQUEST,
            Duration::from_millis(100),
        ),
    )
    .await;
    assert_eq!(
        bounded,
        Ok(Err(DemoBackendError::TimedOut)),
        "timeout cleanup must terminate descendants retaining stdout/stderr"
    );
    fs::remove_file(descendant).expect("backend process tree was reaped");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn every_worker_start_failure_and_disconnected_result_reap_child() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    for failure in [
        DemoBackendThreadFailure::Supervisor,
        DemoBackendThreadFailure::Writer,
        DemoBackendThreadFailure::Stdout,
        DemoBackendThreadFailure::Stderr,
        DemoBackendThreadFailure::DisconnectResult,
    ] {
        let executable = copy_executable(&helper, &root, &format!("marker-thread-{failure:?}"));
        let marker = PathBuf::from(format!("{}.started", executable.display()));
        let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
        let map = load_demo_backend_map(&map_path).unwrap();
        assert_eq!(
            run_demo_backend_with_thread_failure(
                &map,
                &channel("service.example"),
                REQUEST,
                Duration::from_secs(10),
                failure,
            )
            .await,
            Err(DemoBackendError::SpawnFailed),
            "failure stage {failure:?}"
        );
        if failure == DemoBackendThreadFailure::Supervisor {
            assert!(!marker.exists(), "supervisor failure must precede spawn");
        }
        fs::remove_file(&executable).expect("failed worker child was reaped");
    }
}

#[tokio::test(flavor = "current_thread")]
async fn delayed_verification_obeys_total_deadline_without_spawning() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    let executable = copy_executable(&helper, &root, "marker-delayed-verification");
    let marker = PathBuf::from(format!("{}.started", executable.display()));
    let map_path = write_map(&root, &executable, "service.example", &sha256(&executable));
    let map = load_demo_backend_map(&map_path).unwrap();
    let started = std::time::Instant::now();
    assert_eq!(
        run_demo_backend_with_thread_failure(
            &map,
            &channel("service.example"),
            REQUEST,
            Duration::from_millis(50),
            DemoBackendThreadFailure::DelayVerification,
        )
        .await,
        Err(DemoBackendError::TimedOut)
    );
    assert!(
        started.elapsed() < Duration::from_millis(500),
        "deadline must include off-thread verification/setup"
    );
    assert!(!marker.exists(), "expired verification must be zero-spawn");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn main_connector_function_denies_route_before_marker_spawn() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);
    let marker_executable = copy_executable(&helper, &root, "marker-main-connector-denied");
    let marker = PathBuf::from(format!("{}.started", marker_executable.display()));
    let map_path = write_map(
        &root,
        &marker_executable,
        "service.example",
        &sha256(&marker_executable),
    );
    let map = load_demo_backend_map(&map_path).unwrap();
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.unwrap();
    let hello = federated_client_hello();
    source_control.send_envelope(&hello).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    let mut destination_session = federated_session(&destination);
    destination_session
        .accept_client_hello(
            &destination_control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap(),
        )
        .unwrap();
    let edge = edge_hello();
    destination_session.confirm_edge_hello(&edge).unwrap();
    destination_control.send_envelope(&edge).await.unwrap();
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    source_control
        .send_envelope(&federated_route_open())
        .await
        .unwrap();
    let route = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let mut invalid_attestations = federation_attestations();
    invalid_attestations.source[0] ^= 1;
    assert_eq!(
        run_demo_backend_connector(
            &destination,
            &mut destination_control,
            destination_session,
            &route,
            &invalid_attestations,
            &map,
        )
        .await,
        Err(DemoBackendError::StreamFailed)
    );
    assert!(
        !marker.exists(),
        "denied connector route must be zero-spawn"
    );
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn main_connector_function_rejects_service_and_invalid_credit_without_spawn() {
    let root = TestRoot::new();
    let helper = build_lifecycle_helper(&root);

    let service_marker = copy_executable(&helper, &root, "marker-main-service-mismatch");
    let service_marker_path = PathBuf::from(format!("{}.started", service_marker.display()));
    let service_map_path = write_map(
        &root,
        &service_marker,
        "other.service",
        &sha256(&service_marker),
    );
    let service_map = load_demo_backend_map(&service_map_path).unwrap();
    let ConnectorSetup {
        listener: service_listener,
        source: service_source,
        destination: service_destination,
        mut destination_control,
        destination_session,
        route,
        ..
    } = connector_setup().await;
    assert_eq!(
        run_demo_backend_connector(
            &service_destination,
            &mut destination_control,
            destination_session,
            &route,
            &federation_attestations(),
            &service_map,
        )
        .await,
        Err(DemoBackendError::ServiceMismatch)
    );
    assert!(!service_marker_path.exists());
    service_source.close().await.unwrap();
    service_destination.close().await.unwrap();
    service_listener.close().await.unwrap();

    let credit_marker = copy_executable(&helper, &root, "marker-main-invalid-credit");
    let credit_marker_path = PathBuf::from(format!("{}.started", credit_marker.display()));
    let credit_map_path = write_map(
        &root,
        &credit_marker,
        "service.example",
        &sha256(&credit_marker),
    );
    let credit_map = load_demo_backend_map(&credit_map_path).unwrap();
    let ConnectorSetup {
        listener,
        source,
        destination,
        mut source_control,
        mut destination_control,
        mut source_session,
        destination_session,
        source_channel,
        route,
    } = connector_setup().await;
    let credit_attestations = federation_attestations();
    let (connector_result, ()) = tokio::join!(
        run_demo_backend_connector(
            &destination,
            &mut destination_control,
            destination_session,
            &route,
            &credit_attestations,
            &credit_map,
        ),
        async {
            activate_connector_source(
                &source,
                &mut source_control,
                &mut source_session,
                &source_channel,
            )
            .await;
            let source_session = SharedControlSession::new(source_session);
            assert!(
                source
                    .open_credited_session_stream(&source_session, [0xee; 16])
                    .await
                    .is_err(),
                "wrong-channel credit must be rejected"
            );
        },
    );
    assert_eq!(connector_result, Err(DemoBackendError::StreamFailed));
    assert!(
        !credit_marker_path.exists(),
        "invalid credit must be zero-spawn"
    );
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn main_connector_function_relays_positive_federated_credit() {
    let root = TestRoot::new();
    let backend = build_go_backend(&root, "main-connector-positive");
    let map_path = write_map(&root, &backend, "service.example", &sha256(&backend));
    let map = load_demo_backend_map(&map_path).unwrap();
    let ConnectorSetup {
        listener,
        source,
        destination,
        mut source_control,
        mut destination_control,
        mut source_session,
        destination_session,
        source_channel,
        route,
    } = connector_setup().await;
    let positive_attestations = federation_attestations();
    let (connector_result, source_result) = tokio::join!(
        run_demo_backend_connector(
            &destination,
            &mut destination_control,
            destination_session,
            &route,
            &positive_attestations,
            &map,
        ),
        async {
            activate_connector_source(
                &source,
                &mut source_control,
                &mut source_session,
                &source_channel,
            )
            .await;
            let source_session = SharedControlSession::new(source_session);
            let mut stream = source
                .open_credited_session_stream(&source_session, source_channel.channel_id)
                .await
                .unwrap();
            stream.send_and_receive(REQUEST).await.unwrap()
        },
    );
    assert_eq!(connector_result, Ok(RESPONSE.to_vec()));
    assert_eq!(source_result, RESPONSE);
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}
