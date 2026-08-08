use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use nbsr_transport::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Limits, DestinationAdmission,
    EdgeIdentity, EdgeRole, LocalFederationAdmissionAttestations,
    LocalFederationAdmissionAuthorities, PeerPolicy, RouteGrantIssuer, TlsMaterial, TrustProfileId,
    build_client_config, connect, decode_control_envelope,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};

fn argument(name: &str) -> String {
    let values = env::args().collect::<Vec<_>>();
    let index = values
        .iter()
        .position(|value| value == name)
        .unwrap_or_else(|| panic!("missing {name}"));
    values[index + 1].clone()
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

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let authority = PathBuf::from(argument("--authority-dir"));
    let endpoint: SocketAddr = argument("--endpoint").parse().unwrap();
    let samples: u64 = argument("--samples").parse().unwrap();
    let payload_bytes: usize = argument("--payload-bytes").parse().unwrap();
    assert!((1..=100_000).contains(&samples));
    assert!((1..=1_048_576).contains(&payload_bytes));
    let handshake = Instant::now();
    let connection = connect(
        build_client_config(
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
        .unwrap(),
        endpoint,
    )
    .await
    .unwrap();
    let handshake_ns = handshake.elapsed().as_nanos();
    let mut control = connection.open_control_stream().await.unwrap();
    let client = client_hello();
    control.send_envelope(&client).await.unwrap();
    let edge = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let mut session = ControlSession::new(
        &connection,
        DestinationAdmission::new_federated(policy(), authorities()).unwrap(),
        vec![issuer()],
        TrustProfileId::new("federation-dev-v1").unwrap(),
    );
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
    session.confirm_route_accept(&accepted).unwrap();
    let channel: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    connection.bind_channel(&mut session, channel).unwrap();
    let payload = vec![0x5a; payload_bytes];
    let mut records = Vec::with_capacity(samples as usize);
    for index in 0..samples {
        let total = Instant::now();
        let stream = stream_open(index);
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
        let stream_ns = stream_started.elapsed().as_nanos();
        let permit = session
            .application_stream_permit(channel, 4 + 4 * index)
            .unwrap();
        let request_started = Instant::now();
        let response = connection
            .open_session_stream(&permit)
            .await
            .unwrap()
            .send_and_receive(&payload)
            .await
            .unwrap();
        let request_ns = request_started.elapsed().as_nanos();
        assert_eq!(response, payload);
        session.release_stream(channel, 4 + 4 * index).unwrap();
        records.push(format!(
            "{{\"sample_id\":{index},\"success\":true,\"transport_handshake_ns\":{},\"stream_open_rtt_ns\":{stream_ns},\"request_latency_ns\":{request_ns},\"ttfab_ns\":{request_ns},\"total_scenario_ns\":{},\"bytes_transmitted\":{payload_bytes},\"bytes_received\":{payload_bytes}}}",
            if index == 0 {
                handshake_ns.to_string()
            } else {
                "null".into()
            },
            total.elapsed().as_nanos()
        ));
    }
    connection.close().await.unwrap();
    for record in records {
        println!("{record}");
    }
}

trait ReadBytes {
    fn read_bytes(&self) -> Vec<u8>;
}
impl ReadBytes for PathBuf {
    fn read_bytes(&self) -> Vec<u8> {
        fs::read(self).unwrap()
    }
}
