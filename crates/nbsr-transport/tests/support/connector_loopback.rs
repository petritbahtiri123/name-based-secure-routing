//! Explicitly synthetic authority over real isolated loopback TLS. Not a runtime.
#![allow(dead_code)]
use crate::{
    cleanup,
    codec::{self, Value as V, get, map},
    owner::{self, Authority, Binding, Decision, Gateway, Transport},
};
use quinn::{Endpoint, VarInt, crypto::rustls::QuicServerConfig};
use rcgen::{
    BasicConstraints, CertificateParams, CertifiedIssuer, ExtendedKeyUsagePurpose, IsCa, KeyPair,
    KeyUsagePurpose, PKCS_ED25519,
};
use rustls::{
    RootCertStore,
    pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer},
    server::WebPkiClientVerifier,
};
use sha2::{Digest, Sha256};
use std::{
    io::Write,
    process::{Child, Command, Stdio},
    sync::Arc,
    time::{Duration, SystemTime},
};
use tokio::time::timeout;
const LIMIT: Duration = Duration::from_secs(5);
struct ChildGuard(Child);
impl Drop for ChildGuard {
    fn drop(&mut self) {
        if self.0.try_wait().ok().flatten().is_none() {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}
struct Pki {
    ca: CertificateDer<'static>,
    cert: CertificateDer<'static>,
    key: Vec<u8>,
    client: CertificateDer<'static>,
    client_key: Vec<u8>,
    other: CertificateDer<'static>,
    other_key: Vec<u8>,
    server_public: Vec<u8>,
    client_public: Vec<u8>,
}
fn params(name: &str) -> CertificateParams {
    let mut p = CertificateParams::new(vec![name.into()]).unwrap();
    let now = SystemTime::now();
    p.not_before = (now - Duration::from_secs(60)).into();
    p.not_after = (now + Duration::from_secs(3600)).into();
    p.key_usages = vec![KeyUsagePurpose::DigitalSignature];
    p
}
fn pki() -> Pki {
    let mut cp = params("isolated-connector-test-ca");
    cp.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
    cp.key_usages = vec![
        KeyUsagePurpose::KeyCertSign,
        KeyUsagePurpose::DigitalSignature,
    ];
    let ca =
        CertifiedIssuer::self_signed(cp, KeyPair::generate_for(&PKCS_ED25519).unwrap()).unwrap();
    let leaf = |name: &str, usage| {
        let mut p = params(name);
        p.extended_key_usages = vec![usage];
        let k = KeyPair::generate_for(&PKCS_ED25519).unwrap();
        let c = p.signed_by(&k, &ca).unwrap();
        (
            c.der().clone(),
            k.serialize_der(),
            k.public_key_raw().to_vec(),
        )
    };
    let (cert, key, server_public) = leaf(
        "connector-gateway.test",
        ExtendedKeyUsagePurpose::ServerAuth,
    );
    let (client, client_key, client_public) =
        leaf("connector-origin.test", ExtendedKeyUsagePurpose::ClientAuth);
    let (other, other_key, _) = leaf("connector-origin.test", ExtendedKeyUsagePurpose::ClientAuth);
    Pki {
        ca: ca.der().clone(),
        cert,
        key,
        client,
        client_key,
        other,
        other_key,
        server_public,
        client_public,
    }
}
fn endpoint(p: &Pki) -> Endpoint {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let mut roots = RootCertStore::empty();
    roots.add(p.ca.clone()).unwrap();
    let verifier = WebPkiClientVerifier::builder_with_provider(Arc::new(roots), provider.clone())
        .build()
        .unwrap();
    let mut tls = rustls::ServerConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&rustls::version::TLS13])
        .unwrap()
        .with_client_cert_verifier(verifier)
        .with_single_cert(
            vec![p.cert.clone()],
            PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(p.key.clone())),
        )
        .unwrap();
    tls.alpn_protocols = vec![codec::ALPN.as_bytes().to_vec()];
    tls.max_early_data_size = 0;
    let mut config =
        quinn::ServerConfig::with_crypto(Arc::new(QuicServerConfig::try_from(tls).unwrap()));
    let mut transport = quinn::TransportConfig::default();
    transport.max_concurrent_bidi_streams(VarInt::from_u32(1));
    transport.max_concurrent_uni_streams(VarInt::from_u32(0));
    transport.max_idle_timeout(Some(Duration::from_secs(5).try_into().unwrap()));
    config.transport_config(Arc::new(transport));
    let socket = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
    let mut endpoint_config = quinn::EndpointConfig::default();
    endpoint_config.supported_versions(vec![1]);
    Endpoint::new(
        endpoint_config,
        Some(config),
        socket,
        Arc::new(quinn::TokioRuntime),
    )
    .unwrap()
}
struct LiveTransport(quinn::Connection);
impl Transport for LiveTransport {
    fn protocol(&self) -> &str {
        codec::ALPN
    }
    fn export(&mut self, label: &str, context: &[u8]) -> codec::Result<[u8; 32]> {
        let mut out = [0; 32];
        self.0
            .export_keying_material(&mut out, label.as_bytes(), context)
            .map_err(|_| "TLS exporter unavailable")?;
        Ok(out)
    }
    fn nonce(&mut self) -> codec::Result<[u8; 32]> {
        let k = KeyPair::generate_for(&PKCS_ED25519).map_err(|_| "random nonce")?;
        Ok(Sha256::digest(k.public_key_raw()).into())
    }
    fn close(&mut self, _: u64) -> codec::Result<()> {
        Err("real endpoint cleanup must be confirmed asynchronously")
    }
}
struct SyntheticAuthority {
    template: V,
    peer: [u8; 32],
    revision: u64,
    stale: bool,
    calls: u64,
}
impl Authority for SyntheticAuthority {
    fn verify(&mut self, b: &Binding, r: &V, now: u64) -> codec::Result<Decision> {
        if b.peer != self.peer
            || b.connection != 1
            || b.session != [b's'; 16]
            || b.profile != "connector-registration-development-v1"
            || b.action != 24576
            || now != 100
            || b.digest != <[u8; 32]>::from(Sha256::digest(codec::encode(r)))
        {
            return Err("synthetic exact binding");
        }
        for k in [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14] {
            if get(map(r)?, k)? != get(map(&self.template)?, k)? {
                return Err("synthetic exact fixture policy");
            }
        }
        self.calls += 1;
        let revision = self.revision;
        if self.stale && self.calls == 2 {
            self.revision += 1
        }
        Ok(Decision {
            binding: b.clone(),
            revision,
            expires: 1000,
        })
    }
    fn revision(&self) -> u64 {
        self.revision
    }
}
async fn read_frame(r: &mut quinn::RecvStream) -> Result<Vec<u8>, &'static str> {
    let mut first = [0];
    r.read_exact(&mut first).await.map_err(|_| "read prefix")?;
    let width = 1usize << (first[0] >> 6);
    if width == 8 {
        return Err("wide prefix");
    };
    let mut prefix = vec![0; width];
    prefix[0] = first[0];
    r.read_exact(&mut prefix[1..])
        .await
        .map_err(|_| "read prefix")?;
    let mut n = (prefix[0] & 63) as usize;
    for b in &prefix[1..] {
        n = (n << 8) | *b as usize
    }
    if n == 0 || n > 65536 || (width == 2 && n < 64) || (width == 4 && n < 16384) {
        return Err("noncanonical length");
    };
    let mut raw = vec![0; n];
    r.read_exact(&mut raw).await.map_err(|_| "read body")?;
    Ok(raw)
}
async fn send_frame(s: &mut quinn::SendStream, raw: &[u8]) {
    let mut out = vec![
        0;
        if raw.len() < 64 {
            1
        } else if raw.len() < 16384 {
            2
        } else {
            4
        }
    ];
    let n = raw.len();
    match out.len() {
        1 => out[0] = n as u8,
        2 => {
            out[0] = 64 | (n >> 8) as u8;
            out[1] = n as u8
        }
        4 => out.copy_from_slice(&(0x80000000 | n as u32).to_be_bytes()),
        _ => panic!("frame"),
    };
    out.extend(raw);
    s.write_all(&out).await.unwrap();
}
pub async fn run_matrix() {
    let binary = std::env::var("NBSR_CONNECTOR_GO_TEST")
        .expect("explicit prebuilt Go test executable required");
    for case in [
        "positive",
        "untrusted",
        "wrong_alpn",
        "wrong_server_key",
        "wrong_peer",
        "wrong_service",
        "wrong_gateway",
        "wrong_pin",
        "missing_authority",
        "stale_revision",
        "bad_exporter",
        "replay",
        "deny_new",
        "terminate",
        "duplicate",
        "cross_session",
        "withheld_proof",
        "failed_close",
        "cancel_io",
    ] {
        timeout(Duration::from_secs(12), run_case(&binary, case))
            .await
            .expect("case deadline; trial failed");
        println!("loopback case={case} PASS synthetic_authority=true cleanup=confirmed");
    }
}
async fn run_case(binary: &str, case: &str) {
    let p = pki();
    let fingerprint = |raw: &[u8]| {
        Sha256::digest(raw)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>()
    };
    println!(
        "loopback_fixture case={case} ca_sha256={} client_cert_sha256={} server_cert_sha256={}",
        fingerprint(p.ca.as_ref()),
        fingerprint(p.client.as_ref()),
        fingerprint(p.cert.as_ref())
    );
    let ep = endpoint(&p);
    let port = ep.local_addr().unwrap();
    let vector = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/connector-registration-development-v1/request.cbor"),
    )
    .unwrap();
    let mut env = map(&codec::decode(codec::ALPN, &vector).unwrap())
        .unwrap()
        .clone();
    let mut body = map(get(&env, 5).unwrap()).unwrap().clone();
    let peer: [u8; 32] = Sha256::digest(&p.client_public).into();
    body.insert(8, V::Bytes(peer.to_vec()));
    body.insert(14, V::Uint(100));
    let policy = V::Map(body.clone());
    let mut gateway = Gateway::new(policy.clone(), [42; 16], 0).unwrap();
    match case {
        "wrong_service" => {
            body.insert(3, V::Bytes(vec![0; 32]));
        }
        "wrong_gateway" => {
            body.insert(6, V::Text("wrong-gateway".into()));
        }
        "wrong_pin" => {
            body.insert(2, V::Text("wrong-connector".into()));
        }
        _ => {}
    }
    env.insert(5, V::Map(body));
    env.insert(3, V::Bytes(vec![b's'; 16]));
    let mut rid = vec![b's'; 8];
    rid.extend(1u64.to_be_bytes());
    env.insert(2, V::Bytes(rid));
    env.insert(4, V::Uint(1));
    let mut server_public = p.server_public.clone();
    if case == "wrong_server_key" {
        server_public[0] ^= 1
    }
    let (client, key) = if case == "wrong_peer" {
        (&p.other, &p.other_key)
    } else {
        (&p.client, &p.client_key)
    };
    let input = serde_json::json!({"Endpoint":port.to_string(),"Case":case,"CA":p.ca.as_ref(),"Cert":client.as_ref(),"Key":key,"ServerKey":server_public,"Request":codec::encode(&V::Map(env))});
    let mut command = Command::new(binary);
    command
        .args([
            "-test.run=^TestDevelopmentLoopbackProcess$",
            "-test.count=1",
            "-test.timeout=10s",
        ])
        .env("NBSR_CONNECTOR_LOOPBACK", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = ChildGuard(command.spawn().unwrap());
    println!(
        "loopback_owned case={case} rust_pid={} go_pid={} gateway={port}",
        std::process::id(),
        child.0.id()
    );
    child
        .0
        .stdin
        .take()
        .unwrap()
        .write_all(serde_json::to_vec(&input).unwrap().as_slice())
        .unwrap();
    let incoming = timeout(LIMIT, ep.accept()).await.unwrap().unwrap();
    let handshake = timeout(LIMIT, incoming).await.unwrap();
    let mut tickets: Vec<cleanup::CleanupTicket> = Vec::new();
    let positive = [
        "positive",
        "duplicate",
        "cross_session",
        "failed_close",
        "cancel_io",
    ]
    .contains(&case);
    if ["untrusted", "wrong_alpn", "wrong_server_key"].contains(&case) {
        if let Ok(c) = handshake {
            c.close(VarInt::from_u32(1), b"");
            assert!(case == "wrong_server_key", "unexpected server handshake")
        }
    } else {
        let conn = handshake.expect("mutual TLS");
        let certs = conn
            .peer_identity()
            .unwrap()
            .downcast::<Vec<CertificateDer<'static>>>()
            .unwrap();
        if case == "wrong_peer" {
            assert_ne!(certs[0], p.client);
            conn.close(VarInt::from_u32(1), b"");
        } else {
            assert_eq!(certs[0], p.client);
            let (_, parsed) = x509_parser::parse_x509_certificate(certs[0].as_ref()).unwrap();
            assert_eq!(
                parsed.public_key().subject_public_key.data.as_ref(),
                p.client_public
            );
            let handshake = conn
                .handshake_data()
                .unwrap()
                .downcast::<quinn::crypto::rustls::HandshakeData>()
                .unwrap();
            assert_eq!(handshake.protocol.as_deref(), Some(codec::ALPN.as_bytes()));
            gateway.attach(1, [b's'; 16], peer, 100).unwrap();
            let mut transport = LiveTransport(conn.clone());
            let mut authority = SyntheticAuthority {
                template: policy.clone(),
                peer,
                revision: 1,
                stale: case == "stale_revision",
                calls: 0,
            };
            let (mut send, mut recv) = timeout(LIMIT, conn.accept_bi()).await.unwrap().unwrap();
            assert_eq!(u64::from(send.id()), 0);
            let target = if case == "positive" {
                4
            } else if ["replay", "deny_new", "terminate"].contains(&case) {
                3
            } else if [
                "bad_exporter",
                "stale_revision",
                "duplicate",
                "cross_session",
                "withheld_proof",
                "failed_close",
                "cancel_io",
            ]
            .contains(&case)
            {
                2
            } else {
                1
            };
            for index in 0..target {
                if case == "withheld_proof" && index == 1 {
                    let result = timeout(LIMIT, read_frame(&mut recv)).await;
                    assert!(
                        !matches!(result, Ok(Ok(_))),
                        "withheld proof unexpectedly arrived"
                    );
                    assert!(gateway.owner.is_none());
                    break;
                }
                let raw = timeout(LIMIT, read_frame(&mut recv))
                    .await
                    .unwrap()
                    .expect("control frame");
                if index == 2 && (case == "deny_new" || case == "terminate") {
                    let dep = gateway.owner.as_ref().unwrap().binding.dependencies;
                    let mode = if case == "deny_new" {
                        owner::Invalidation::DenyNew
                    } else {
                        owner::Invalidation::Terminate
                    };
                    let result = gateway.invalidate(dep, mode, &mut transport);
                    if case == "terminate" {
                        assert!(result.is_err())
                    } else {
                        result.unwrap()
                    };
                    assert!(!gateway.owner.as_ref().unwrap().eligible);
                }
                let result = gateway.handle(
                    1,
                    &raw,
                    100,
                    if case == "missing_authority" {
                        None
                    } else {
                        Some(&mut authority)
                    },
                    &mut transport,
                );
                let expected_reject = !positive && index + 1 == target;
                if expected_reject {
                    assert!(result.is_err(), "negative did not reject: {case}");
                    break;
                }
                send_frame(&mut send, &result.unwrap().unwrap()).await;
            }
            if case == "duplicate" || case == "cross_session" {
                let old = gateway.owner.clone().unwrap();
                let second = timeout(LIMIT, ep.accept()).await.unwrap().unwrap();
                let second = timeout(LIMIT, second).await.unwrap().unwrap();
                let certs = second
                    .peer_identity()
                    .unwrap()
                    .downcast::<Vec<CertificateDer<'static>>>()
                    .unwrap();
                assert_eq!(certs[0], p.client);
                gateway.attach(2, [b't'; 16], peer, 100).unwrap();
                let (mut s, mut r) = timeout(LIMIT, second.accept_bi()).await.unwrap().unwrap();
                assert_eq!(u64::from(s.id()), 0);
                let raw = timeout(LIMIT, read_frame(&mut r)).await.unwrap().unwrap();
                let mut tr = LiveTransport(second.clone());
                assert_eq!(
                    gateway.handle(2, &raw, 100, Some(&mut authority), &mut tr),
                    Err(if case == "duplicate" {
                        "duplicate owner"
                    } else {
                        "session/sequence"
                    })
                );
                assert_eq!(gateway.owner.as_ref(), Some(&old));
                tickets.push(gateway.begin_cleanup(2).unwrap());
                r.stop(VarInt::from_u32(0)).ok();
                s.reset(VarInt::from_u32(0)).ok();
                second.close(VarInt::from_u32(0), b"");
            }
            if positive {
                assert!(gateway.owner.as_ref().unwrap().eligible);
                assert_eq!(gateway.owner.as_ref().unwrap().generation, 1);
                let mut marker = [0];
                assert_eq!(
                    timeout(LIMIT, recv.read(&mut marker))
                        .await
                        .unwrap()
                        .unwrap(),
                    None,
                    "child FIN after validated renewal"
                )
            }
            let t = gateway.begin_cleanup(1).unwrap();
            assert!(gateway.finish_cleanup(&t).is_err());
            tickets.push(t);
            recv.stop(VarInt::from_u32(0)).ok();
            send.reset(VarInt::from_u32(0)).ok();
            drop(recv);
            drop(send);
            conn.close(VarInt::from_u32(0), b"");
            drop(transport);
        }
    }
    ep.close(VarInt::from_u32(0), b"");
    timeout(LIMIT, ep.wait_idle())
        .await
        .expect("endpoint cleanup confirmation");
    drop(ep);
    let status = timeout(LIMIT, async {
        loop {
            if let Some(s) = child.0.try_wait().unwrap() {
                break s;
            }
            tokio::time::sleep(Duration::from_millis(10)).await
        }
    })
    .await
    .unwrap();
    let mut output = String::new();
    use std::io::Read;
    child
        .0
        .stdout
        .take()
        .unwrap()
        .read_to_string(&mut output)
        .unwrap();
    if !status.success() {
        panic!("Go child failure case={case}: {output}")
    }
    for line in output
        .lines()
        .filter(|line| line.starts_with("loopback_socket_released="))
    {
        println!("case={case} {line}")
    }
    // Closing the endpoint must release the actual loopback UDP socket.
    timeout(LIMIT, async {
        loop {
            match std::net::UdpSocket::bind(port) {
                Ok(probe) => {
                    drop(probe);
                    break;
                }
                Err(_) => tokio::time::sleep(Duration::from_millis(10)).await,
            }
        }
    })
    .await
    .expect("Rust UDP socket released");
    for t in tickets {
        t.complete(Ok(()));
        gateway.finish_cleanup(&t).unwrap();
    }
    assert!(gateway.owner.is_none());
    println!(
        "loopback_reaped case={case} go_pid={} gateway_socket_released=true owner_count=0",
        child.0.id()
    );
}
