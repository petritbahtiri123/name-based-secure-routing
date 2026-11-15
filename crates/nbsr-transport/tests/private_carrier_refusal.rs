//! PRIVATE transport fixture only. No registration bytes, principal mapping or authority.
use quinn::{
    Connection, Endpoint, VarInt,
    crypto::rustls::{QuicClientConfig, QuicServerConfig},
};
use rcgen::{BasicConstraints, CertificateParams, CertifiedIssuer, IsCa, KeyPair, PKCS_ED25519};
use rustls::{
    RootCertStore,
    pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer},
};
use std::{sync::Arc, time::Duration};
use tokio::time::{Instant, timeout};
use x509_parser::prelude::*;

const ALPN: &[u8] = b"nbsr-connector-fixture-refusal-1";
const LABEL: &[u8] = b"EXPORTER-NBSR-Connector-Registration-v1";

fn raw_ed25519(der: &[u8]) -> Result<[u8; 32], &'static str> {
    let (rest, cert) = X509Certificate::from_der(der).map_err(|_| "certificate")?;
    let key = cert.public_key();
    if !rest.is_empty()
        || key.algorithm.algorithm.to_id_string() != "1.3.101.112"
        || key.algorithm.parameters.is_some()
        || key.subject_public_key.unused_bits != 0
    {
        return Err("not canonical Ed25519");
    }
    key.subject_public_key
        .data
        .as_ref()
        .try_into()
        .map_err(|_| "key length")
}
struct Evidence {
    owner: Arc<()>,
    raw: [u8; 32],
}
struct Peer {
    control_claimed: std::sync::atomic::AtomicBool,
    connection: Connection,
    owner: Arc<()>,
}
impl Peer {
    fn claim_control(&self) -> Result<(), &'static str> {
        if self
            .control_claimed
            .swap(true, std::sync::atomic::Ordering::AcqRel)
        {
            return Err("control stream already claimed");
        }
        Ok(())
    }

    fn evidence(&self, expected: [u8; 32]) -> Result<Evidence, &'static str> {
        let identity = self.connection.peer_identity().ok_or("identity")?;
        let certs = identity
            .downcast::<Vec<CertificateDer<'static>>>()
            .map_err(|_| "identity type")?;
        let raw = raw_ed25519(certs.first().ok_or("leaf")?.as_ref())?;
        if raw != expected {
            return Err("unexpected fixture key");
        }
        Ok(Evidence {
            owner: self.owner.clone(),
            raw,
        })
    }
    fn unavailable(&self, evidence: &Evidence) -> Result<std::convert::Infallible, &'static str> {
        if !Arc::ptr_eq(&self.owner, &evidence.owner) {
            return Err("foreign connection evidence");
        }
        let _ = evidence.raw; // Key possession is transport evidence, never authority.
        Err("authority unavailable")
    }
}
// Ticket retains endpoints even after timeout. No callback clears ownership.
struct CloseTicket<T = (Endpoint, Endpoint)> {
    endpoints: Option<T>,
}
impl<T> CloseTicket<T> {
    fn finish_observation(
        &mut self,
        observation: Result<(), &'static str>,
    ) -> Result<(), &'static str> {
        if self.endpoints.is_none() {
            return Err("already released");
        }
        observation?;
        self.endpoints.take();
        Ok(())
    }
}
impl CloseTicket {
    async fn confirm(&mut self, budget: Duration) -> Result<(), &'static str> {
        let (a, b) = self.endpoints.as_ref().ok_or("already released")?;
        a.close(VarInt::from_u32(0), b"fixture complete");
        b.close(VarInt::from_u32(0), b"fixture complete");
        let observation = timeout(budget, async {
            tokio::join!(a.wait_idle(), b.wait_idle());
        })
        .await
        .map_err(|_| "uncertain close");
        self.finish_observation(observation)
    }
}
fn leaf(
    ca: &CertifiedIssuer<'_, KeyPair>,
    name: &str,
    ed: bool,
) -> (CertificateDer<'static>, Vec<u8>) {
    let key = if ed {
        KeyPair::generate_for(&PKCS_ED25519).unwrap()
    } else {
        KeyPair::generate().unwrap()
    };
    let params = CertificateParams::new(vec![name.into()]).unwrap();
    let cert = params.signed_by(&key, ca).unwrap();
    (cert.der().clone(), key.serialize_der())
}
fn ca() -> CertifiedIssuer<'static, KeyPair> {
    let mut params = CertificateParams::default();
    params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
    CertifiedIssuer::self_signed(params, KeyPair::generate_for(&PKCS_ED25519).unwrap()).unwrap()
}
fn private_key(key: Vec<u8>) -> PrivateKeyDer<'static> {
    PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(key))
}

#[test]
fn strict_extraction_rejects_other_algorithm_and_trailing_data() {
    let ca = ca();
    let (ed, _) = leaf(&ca, "gateway.fixture", true);
    assert!(raw_ed25519(&ed).is_ok());
    let (other, _) = leaf(&ca, "gateway.fixture", false);
    assert!(raw_ed25519(&other).is_err());
    let mut trailing = ed.to_vec();
    trailing.push(0);
    assert!(raw_ed25519(&trailing).is_err());
    assert!(raw_ed25519(&[]).is_err());
}

#[tokio::test(flavor = "current_thread")]
async fn private_mutual_tls_refuses_authority_and_confirms_dedicated_cleanup() {
    let ca = ca();
    let (client_cert, client_key) = leaf(&ca, "connector.fixture", true);
    let (server_cert, server_key) = leaf(&ca, "gateway.fixture", true);
    let client_raw = raw_ed25519(&client_cert).unwrap();
    let server_raw = raw_ed25519(&server_cert).unwrap();
    let mut roots = RootCertStore::empty();
    roots.add(ca.der().clone()).unwrap();
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let verifier = rustls::server::WebPkiClientVerifier::builder_with_provider(
        Arc::new(roots.clone()),
        provider.clone(),
    )
    .build()
    .unwrap();
    let mut server_tls = rustls::ServerConfig::builder_with_provider(provider.clone())
        .with_protocol_versions(&[&rustls::version::TLS13])
        .unwrap()
        .with_client_cert_verifier(verifier)
        .with_single_cert(vec![server_cert], private_key(server_key))
        .unwrap();
    server_tls.alpn_protocols = vec![ALPN.to_vec()];
    server_tls.max_early_data_size = 0;
    let mut client_tls = rustls::ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&rustls::version::TLS13])
        .unwrap()
        .with_root_certificates(roots)
        .with_client_auth_cert(vec![client_cert], private_key(client_key))
        .unwrap();
    client_tls.alpn_protocols = vec![ALPN.to_vec()];
    client_tls.enable_early_data = false;
    client_tls.resumption = rustls::client::Resumption::disabled();
    let mut transport = quinn::TransportConfig::default();
    transport.max_concurrent_bidi_streams(1_u32.into());
    transport.max_concurrent_uni_streams(0_u32.into());
    transport.datagram_receive_buffer_size(None);
    let transport = Arc::new(transport);
    let mut server_config =
        quinn::ServerConfig::with_crypto(Arc::new(QuicServerConfig::try_from(server_tls).unwrap()));
    server_config.transport_config(transport.clone());
    let server = Endpoint::server(server_config, "127.0.0.1:0".parse().unwrap()).unwrap();
    let remote = server.local_addr().unwrap();
    let mut client = Endpoint::client("127.0.0.1:0".parse().unwrap()).unwrap();
    let mut client_config =
        quinn::ClientConfig::new(Arc::new(QuicClientConfig::try_from(client_tls).unwrap()));
    client_config.transport_config(transport);
    client.set_default_client_config(client_config);
    let mut ticket = CloseTicket {
        endpoints: Some((client, server)),
    };
    let started = Instant::now();
    let (client, server) = ticket.endpoints.as_ref().unwrap();
    let (client, server) = (client.clone(), server.clone());
    let mut worker = tokio::spawn(async move {
        let (left, right) = tokio::join!(
            async {
                client
                    .connect(remote, "gateway.fixture")
                    .unwrap()
                    .await
                    .unwrap()
            },
            async { server.accept().await.unwrap().await.unwrap() }
        );
        let left = Peer {
            control_claimed: std::sync::atomic::AtomicBool::new(false),
            connection: left,
            owner: Arc::new(()),
        };
        let right = Peer {
            control_claimed: std::sync::atomic::AtomicBool::new(false),
            connection: right,
            owner: Arc::new(()),
        };
        for peer in [&left, &right] {
            let data = peer
                .connection
                .handshake_data()
                .unwrap()
                .downcast::<quinn::crypto::rustls::HandshakeData>()
                .unwrap();
            assert_eq!(data.protocol.as_deref(), Some(ALPN));
            assert!(
                peer.connection
                    .send_datagram(bytes::Bytes::from_static(b"forbidden"))
                    .is_err()
            );
        }
        let evidence = right.evidence(client_raw).unwrap();
        // Real second TLS connection with the SAME credentials and endpoints:
        // identity equality must not permit evidence replay across connections.
        let (second_client, second_server) = tokio::join!(
            async {
                client
                    .connect(remote, "gateway.fixture")
                    .unwrap()
                    .await
                    .unwrap()
            },
            async { server.accept().await.unwrap().await.unwrap() }
        );
        let second = Peer {
            control_claimed: std::sync::atomic::AtomicBool::new(false),
            connection: second_server,
            owner: Arc::new(()),
        };
        let second_evidence = second.evidence(client_raw).unwrap();
        assert_eq!(second_evidence.raw, evidence.raw);
        assert_eq!(
            second.unavailable(&evidence).unwrap_err(),
            "foreign connection evidence"
        );
        assert_eq!(
            right.unavailable(&second_evidence).unwrap_err(),
            "foreign connection evidence"
        );
        assert_eq!(
            second.unavailable(&second_evidence).unwrap_err(),
            "authority unavailable"
        );
        drop((second_evidence, second, second_client));
        assert!(right.evidence(server_raw).is_err());
        assert!(left.evidence(server_raw).is_ok());
        assert_eq!(
            left.unavailable(&evidence).unwrap_err(),
            "foreign connection evidence"
        );
        assert_eq!(
            right.unavailable(&evidence).unwrap_err(),
            "authority unavailable"
        );
        // Arbitrary labelled fixture context, NOT a registration transcript or proof.
        let context = b"private transport fixture; no registration";
        let mut a = [0; 32];
        let mut b = [0; 32];
        left.connection
            .export_keying_material(&mut a, LABEL, context)
            .unwrap();
        right
            .connection
            .export_keying_material(&mut b, LABEL, context)
            .unwrap();
        assert_eq!(a, b);
        let mut different = [0; 32];
        right
            .connection
            .export_keying_material(&mut different, LABEL, b"other fixture context")
            .unwrap();
        assert_ne!(a, different);
        // Opening alone is lazy: finish empty stream to make stream0 observable.
        // No registration frame or application payload is sent.
        left.claim_control().unwrap();
        assert!(left.claim_control().is_err());
        let (mut send, recv) = left.connection.open_bi().await.unwrap();
        assert_eq!(u64::from(send.id()), 0);
        send.finish().unwrap();
        right.claim_control().unwrap();
        assert!(right.claim_control().is_err());
        let (send2, mut recv2) = right.connection.accept_bi().await.unwrap();
        assert_eq!(u64::from(recv2.id()), 0);
        assert!(recv2.read_to_end(0).await.unwrap().is_empty());
        drop((send, recv, send2, recv2, evidence, left, right));
    });
    let result = timeout(Duration::from_secs(5), &mut worker).await;
    if result.is_err() {
        worker.abort();
        let _ = worker.await;
    }
    // Always attempt endpoint cleanup even if outer operation timed out.
    let cleanup = ticket.confirm(Duration::from_secs(3)).await;
    assert!(cleanup.is_ok(), "dedicated endpoint cleanup unresolved");
    assert!(ticket.endpoints.is_none());
    assert!(
        matches!(result, Ok(Ok(()))),
        "transport experiment timed out after {:?}",
        started.elapsed()
    );
}

#[test]
fn strict_extraction_rejects_parseable_nonzero_unused_key_bits() {
    let ca = ca();
    let (certificate, _) = leaf(&ca, "gateway.fixture", true);
    let mut der = certificate.to_vec();
    // Exact Ed25519 SubjectPublicKeyInfo header, including BIT STRING length.
    // This test edits public fixture bytes; signature validity is NOT asserted.
    let header = [
        0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00,
    ];
    let matches: Vec<_> = der
        .windows(header.len())
        .enumerate()
        .filter_map(|(offset, bytes)| (bytes == header).then_some(offset))
        .collect();
    assert_eq!(matches.len(), 1);
    let offset = matches[0];
    der[offset + 11] = 1;
    der[offset + 43] &= 0xfe;
    let (rest, parsed) = X509Certificate::from_der(&der).unwrap();
    assert!(rest.is_empty());
    assert_eq!(parsed.public_key().subject_public_key.unused_bits, 1);
    assert_eq!(raw_ed25519(&der), Err("not canonical Ed25519"));
}

#[test]
fn cleanup_ticket_retains_after_deadline_until_both_idle_once() {
    use std::{
        future::Future,
        sync::atomic::{AtomicUsize, Ordering},
        task::{Context, Poll, Waker},
    };
    struct OwnedProbe(Arc<AtomicUsize>);
    impl Drop for OwnedProbe {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }
    let releases = Arc::new(AtomicUsize::new(0));
    let mut ticket = CloseTicket {
        endpoints: Some(OwnedProbe(releases.clone())),
    };
    let (client_idle, client_wait) = tokio::sync::oneshot::channel::<()>();
    let server_observed = Arc::new(AtomicUsize::new(0));
    let observed = server_observed.clone();
    let mut pair = Box::pin(async move {
        tokio::join!(
            async {
                client_wait.await.unwrap();
            },
            async {
                observed.store(1, Ordering::SeqCst);
            }
        );
    });
    let mut context = Context::from_waker(Waker::noop());
    assert!(matches!(pair.as_mut().poll(&mut context), Poll::Pending));
    assert_eq!(server_observed.load(Ordering::SeqCst), 1);
    // Deterministically inject the deadline observation while client is pending.
    // No wall-clock sleep or claim about Quinn's drain timer is involved.
    assert_eq!(
        ticket.finish_observation(Err("uncertain close")),
        Err("uncertain close")
    );
    assert!(ticket.endpoints.is_some());
    assert_eq!(releases.load(Ordering::SeqCst), 0);
    client_idle.send(()).unwrap();
    assert!(matches!(pair.as_mut().poll(&mut context), Poll::Ready(())));
    // Late completion does not itself relinquish ownership.
    assert!(ticket.endpoints.is_some());
    assert_eq!(releases.load(Ordering::SeqCst), 0);
    assert_eq!(ticket.finish_observation(Ok(())), Ok(()));
    assert!(ticket.endpoints.is_none());
    assert_eq!(releases.load(Ordering::SeqCst), 1);
    assert_eq!(ticket.finish_observation(Ok(())), Err("already released"));
    assert_eq!(releases.load(Ordering::SeqCst), 1);
}
