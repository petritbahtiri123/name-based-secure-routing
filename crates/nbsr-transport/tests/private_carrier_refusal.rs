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
// Test-local policy; no runtime authority or shared-listener cleanup semantics.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Failure {
    InvalidDeadline,
    Error,
    Expired,
    Cancelled,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Release {
    Timely,
    LateConfirmed,
}
#[derive(Default)]
struct DeadlineTicket {
    started: bool,
    invalid: bool,
    deadline: Option<Duration>,
    last: Option<Duration>,
    failure: Option<Failure>,
    complete: [bool; 2],
    released: Option<Release>,
}
impl DeadlineTicket {
    fn fail(&mut self, reason: Failure) {
        self.invalid |= reason == Failure::InvalidDeadline;
        self.failure.get_or_insert(reason);
    }
    fn begin(&mut self, now: Duration) {
        if self.started {
            return;
        }
        self.started = true;
        self.last = Some(now);
        self.deadline = now.checked_add(Duration::from_secs(3));
        if self.deadline.is_none() {
            self.fail(Failure::InvalidDeadline);
        }
    }
    fn sample(&mut self, now: Duration) -> bool {
        if !self.started || self.last.is_some_and(|last| now < last) {
            self.fail(Failure::InvalidDeadline);
            return false;
        }
        self.last = Some(now);
        match self.deadline {
            Some(deadline) if now < deadline => true,
            Some(_) => {
                self.fail(Failure::Expired);
                false
            }
            None => {
                self.fail(Failure::InvalidDeadline);
                false
            }
        }
    }
    fn observe(&mut self, now: Duration, both: [bool; 2]) -> Option<Release> {
        if self.released.is_some() {
            return None;
        }
        let timely = self.sample(now);
        // Evidence is scoped to this synthetic ticket. Production evidence absent.
        self.complete[0] |= both[0];
        self.complete[1] |= both[1];
        if timely && self.failure.is_none() && self.complete == [true; 2] {
            self.released = Some(Release::Timely);
            return self.released;
        }
        None
    }
    fn reconcile(&mut self, now: Duration, both: [bool; 2]) -> Option<Release> {
        if self.released.is_some() || self.invalid {
            return None;
        }
        // Validate through the shared sampler so rollback latches invalidity.
        self.sample(now);
        if self.invalid {
            return None;
        }
        // Fresh explicit both-complete evidence, not a cached single-side count.
        if self.failure.is_some() && both == [true; 2] {
            self.released = Some(Release::LateConfirmed);
            return self.released;
        }
        None
    }
}

struct CloseTicket<T = (Endpoint, Endpoint)> {
    endpoints: Option<T>,
    policy: DeadlineTicket,
    origin: Instant,
}
impl<T> CloseTicket<T> {
    fn new(endpoints: T) -> Self {
        Self {
            endpoints: Some(endpoints),
            policy: DeadlineTicket::default(),
            origin: Instant::now(),
        }
    }
    fn classify(&mut self, now: Duration, both: [bool; 2], late: bool) -> Option<Release> {
        self.endpoints.as_ref()?;
        let result = if late {
            self.policy.reconcile(now, both)
        } else {
            self.policy.observe(now, both)
        };
        if result.is_some() {
            self.endpoints.take();
        }
        result
    }
}
// Dropping a polled confirmation records cancellation while retaining endpoints.
struct Confirmation<'a, T>(&'a mut CloseTicket<T>, bool);
impl<T> Drop for Confirmation<'_, T> {
    fn drop(&mut self) {
        if !self.1 {
            self.0.policy.fail(Failure::Cancelled);
        }
    }
}
impl<T> CloseTicket<T> {
    // Both the endpoint wrapper and deterministic tests execute this async path.
    async fn confirm_with<A, B>(
        &mut self,
        budget: Duration,
        start: impl FnOnce() -> (A, B),
    ) -> Result<(), &'static str>
    where
        A: std::future::Future<Output = ()>,
        B: std::future::Future<Output = ()>,
    {
        if self.endpoints.is_none() {
            return Err("already released");
        }
        if budget != Duration::from_secs(3) {
            self.policy.fail(Failure::InvalidDeadline);
            return Err("invalid fixture budget");
        }
        self.policy.begin(self.origin.elapsed());
        let deadline = self
            .policy
            .deadline
            .and_then(|d| self.origin.checked_add(d));
        let Some(deadline) = deadline else {
            self.policy.fail(Failure::InvalidDeadline);
            return Err("invalid deadline");
        };
        let mut guard = Confirmation(self, false);
        let (a, b) = start();
        let result = tokio::time::timeout_at(deadline, async {
            tokio::join!(a, b);
        })
        .await;
        let now = guard.0.origin.elapsed();
        let outcome = if result.is_ok() {
            guard.0.classify(now, [true, true], false)
        } else {
            guard.0.policy.fail(Failure::Expired);
            None
        };
        guard.1 = true;
        if outcome == Some(Release::Timely) {
            Ok(())
        } else {
            Err("uncertain close")
        }
    }
    // LateConfirmed means separate settlement AFTER FAILURE, possibly before deadline.
    // Poll once: no new waiting budget and no change to original failed outcome.
    async fn settle_with<A, B>(&mut self, a: A, b: B) -> Option<Release>
    where
        A: std::future::Future<Output = ()>,
        B: std::future::Future<Output = ()>,
    {
        use std::{future::poll_fn, task::Poll};
        let mut left = std::pin::pin!(a);
        let mut right = std::pin::pin!(b);
        let both = poll_fn(|cx| {
            Poll::Ready([
                left.as_mut().poll(cx).is_ready(),
                right.as_mut().poll(cx).is_ready(),
            ])
        })
        .await;
        self.classify(self.origin.elapsed(), both, true)
    }
}
impl CloseTicket {
    async fn confirm(&mut self, budget: Duration) -> Result<(), &'static str> {
        let (a, b) = self.endpoints.as_ref().ok_or("already released")?;
        let (a, b) = (a.clone(), b.clone());
        self.confirm_with(budget, move || {
            a.close(VarInt::from_u32(0), b"fixture complete");
            b.close(VarInt::from_u32(0), b"fixture complete");
            (async move { a.wait_idle().await }, async move {
                b.wait_idle().await
            })
        })
        .await
    }
    async fn settle_late(&mut self) -> Option<Release> {
        let (a, b) = self.endpoints.as_ref()?;
        let (a, b) = (a.clone(), b.clone());
        self.settle_with(async move { a.wait_idle().await }, async move {
            b.wait_idle().await
        })
        .await
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
    let mut ticket = CloseTicket::new((client, server));
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

#[cfg(test)]
mod tests {
    use super::*;
    fn s(v: u64) -> Duration {
        Duration::from_secs(v)
    }
    #[test]
    fn capture_once_and_both_required() {
        let mut t = DeadlineTicket::default();
        t.begin(s(10));
        t.begin(s(12));
        assert_eq!(t.deadline, Some(s(13)));
        assert_eq!(t.observe(s(11), [true, false]), None);
        assert_eq!(t.observe(s(12), [false, true]), Some(Release::Timely));
        assert_eq!(t.observe(s(12), [true, true]), None);
    }
    #[test]
    fn equality_and_late_retain_then_release_once_without_rewriting_failure() {
        for elapsed in [3, 4] {
            let mut t = DeadlineTicket::default();
            t.begin(s(0));
            assert_eq!(t.observe(s(elapsed), [true, true]), None);
            assert_eq!(t.failure, Some(Failure::Expired));
            assert_eq!(t.reconcile(s(elapsed), [true, false]), None);
            assert_eq!(
                t.reconcile(s(elapsed), [true, true]),
                Some(Release::LateConfirmed)
            );
            assert_eq!(t.failure, Some(Failure::Expired));
            assert_eq!(t.reconcile(s(elapsed), [true, true]), None);
        }
    }
    #[test]
    fn errors_and_cancellation_are_sticky() {
        for failure in [Failure::Error, Failure::Cancelled] {
            let mut t = DeadlineTicket::default();
            t.begin(s(1));
            t.fail(failure);
            assert_eq!(t.observe(s(2), [true, true]), None);
            t.begin(s(100));
            assert_eq!(t.deadline, Some(s(4)));
            assert_eq!(
                t.reconcile(s(5), [true, true]),
                Some(Release::LateConfirmed)
            );
            assert_eq!(t.failure, Some(failure));
        }
    }
    #[test]
    fn overflow_unstarted_and_rollback_fail_closed() {
        let mut t = DeadlineTicket::default();
        t.begin(Duration::MAX);
        assert_eq!(t.observe(Duration::MAX, [true, true]), None);
        assert_eq!(t.reconcile(Duration::MAX, [true, true]), None);
        assert_eq!(t.failure, Some(Failure::InvalidDeadline));
        let mut u = DeadlineTicket::default();
        assert_eq!(u.observe(s(0), [true, true]), None);
        u.begin(s(1));
        assert_eq!(u.observe(s(2), [true, true]), None);
        let mut v = DeadlineTicket::default();
        v.begin(s(5));
        assert_eq!(v.observe(s(4), [true, true]), None);
        assert_eq!(v.failure, Some(Failure::InvalidDeadline));
    }
    #[test]
    fn reconcile_rollback_latches_invalid_and_prevents_later_release() {
        for earlier_failure in [None, Some(Failure::Error), Some(Failure::Cancelled)] {
            let mut t = DeadlineTicket::default();
            t.begin(s(10));
            if let Some(reason) = earlier_failure {
                t.fail(reason);
            }
            assert_eq!(t.reconcile(s(9), [true, true]), None);
            assert!(t.invalid);
            assert_eq!(
                t.failure,
                earlier_failure.or(Some(Failure::InvalidDeadline))
            );
            assert_eq!(t.observe(s(11), [true, true]), None);
            assert_eq!(t.reconcile(s(14), [true, true]), None);
            assert_eq!(t.released, None);
            assert!(t.invalid);
            assert_eq!(
                t.failure,
                earlier_failure.or(Some(Failure::InvalidDeadline))
            );
        }
    }
}

#[test]
fn actual_ticket_classification_retains_then_releases_once() {
    use std::sync::atomic::{AtomicUsize, Ordering};
    struct Probe(Arc<AtomicUsize>);
    impl Drop for Probe {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }
    let drops = Arc::new(AtomicUsize::new(0));
    let mut ticket = CloseTicket::new(Probe(drops.clone()));
    ticket.policy.begin(Duration::ZERO);
    assert_eq!(
        ticket.classify(Duration::from_secs(3), [true, true], false),
        None
    );
    assert_eq!(drops.load(Ordering::SeqCst), 0);
    assert_eq!(
        ticket.classify(Duration::from_secs(4), [true, true], true),
        Some(Release::LateConfirmed)
    );
    assert_eq!(ticket.policy.failure, Some(Failure::Expired));
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(
        ticket.classify(Duration::from_secs(4), [true, true], true),
        None
    );
    assert_eq!(drops.load(Ordering::SeqCst), 1);
}

#[cfg(test)]
mod async_adapter_tests {
    use super::*;
    use std::{
        future::{Future, pending, ready},
        task::{Context, Poll, Waker},
    };
    const BUDGET: Duration = Duration::from_secs(3);

    #[tokio::test(flavor = "current_thread")]
    async fn timely_async_success_releases_without_failure() {
        let mut ticket = CloseTicket::new(());
        assert_eq!(
            ticket.confirm_with(BUDGET, || (ready(()), ready(()))).await,
            Ok(())
        );
        assert_eq!(ticket.policy.released, Some(Release::Timely));
        assert_eq!(ticket.policy.failure, None);
        assert!(ticket.endpoints.is_none());
        assert_eq!(
            ticket.confirm_with(BUDGET, || (ready(()), ready(()))).await,
            Err("already released")
        );
    }

    #[tokio::test(flavor = "current_thread")]
    async fn endpoint_settlement_after_release_is_noop() {
        // Empty endpoint ticket exercises the real wrapper's terminal guard,
        // without creating sockets or claiming real endpoint drain coverage.
        let mut ticket: CloseTicket = CloseTicket {
            endpoints: None,
            policy: DeadlineTicket::default(),
            origin: Instant::now(),
        };
        ticket.policy.fail(Failure::Cancelled);
        ticket.policy.released = Some(Release::LateConfirmed);
        assert_eq!(ticket.settle_late().await, None);
        assert_eq!(ticket.policy.failure, Some(Failure::Cancelled));
        assert_eq!(ticket.policy.released, Some(Release::LateConfirmed));
    }

    #[tokio::test(flavor = "current_thread")]
    async fn unpolled_drop_does_not_start_or_cancel() {
        let mut ticket = CloseTicket::new(());
        let future = ticket.confirm_with(BUDGET, || (pending::<()>(), pending::<()>()));
        drop(future);
        assert!(!ticket.policy.started);
        assert_eq!(ticket.policy.failure, None);
        assert!(ticket.endpoints.is_some());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn polled_drop_and_retry_preserve_deadline_and_failure() {
        let mut ticket = CloseTicket::new(());
        let mut context = Context::from_waker(Waker::noop());
        let mut future = Box::pin(ticket.confirm_with(BUDGET, || (ready(()), pending::<()>())));
        assert!(matches!(future.as_mut().poll(&mut context), Poll::Pending));
        drop(future);
        let deadline = ticket.policy.deadline;
        assert!(deadline.is_some());
        assert_eq!(ticket.policy.failure, Some(Failure::Cancelled));
        assert!(ticket.endpoints.is_some());
        assert_eq!(
            ticket.confirm_with(BUDGET, || (ready(()), ready(()))).await,
            Err("uncertain close")
        );
        assert_eq!(ticket.policy.deadline, deadline);
        assert_eq!(ticket.policy.failure, Some(Failure::Cancelled));
        assert!(ticket.endpoints.is_some());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn elapsed_absolute_deadline_times_out_and_retains() {
        let mut ticket = CloseTicket::new(());
        // Move only the fixture clock origin; avoid real sleeps or timeout bump.
        ticket.origin = Instant::now().checked_sub(Duration::from_secs(4)).unwrap();
        ticket.policy.begin(Duration::ZERO);
        assert_eq!(
            ticket
                .confirm_with(BUDGET, || (ready(()), pending::<()>()))
                .await,
            Err("uncertain close")
        );
        assert_eq!(ticket.policy.deadline, Some(BUDGET));
        assert_eq!(ticket.policy.failure, Some(Failure::Expired));
        assert!(ticket.endpoints.is_some());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn pending_settlement_retains_then_both_idle_releases_with_failure() {
        let mut ticket = CloseTicket::new(());
        let mut context = Context::from_waker(Waker::noop());
        let mut future = Box::pin(ticket.confirm_with(BUDGET, || (ready(()), pending::<()>())));
        assert!(matches!(future.as_mut().poll(&mut context), Poll::Pending));
        drop(future);
        let deadline = ticket.policy.deadline;
        assert_eq!(ticket.settle_with(ready(()), pending::<()>()).await, None);
        assert!(ticket.endpoints.is_some());
        assert_eq!(
            ticket.settle_with(ready(()), ready(())).await,
            Some(Release::LateConfirmed)
        );
        assert!(ticket.endpoints.is_none());
        assert_eq!(ticket.policy.failure, Some(Failure::Cancelled));
        assert_eq!(ticket.policy.deadline, deadline);
        assert_eq!(ticket.settle_with(ready(()), ready(())).await, None);
        assert_eq!(ticket.policy.failure, Some(Failure::Cancelled));
    }
}
