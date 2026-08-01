use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use crate::session::SessionClock;
use crate::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, DestinationAdmission, EdgeIdentity,
    EdgeRole, PeerPolicy, ResumeReject, SessionReject, TransportListener, TrustProfileId,
    build_client_config, build_server_config, connect, decode_control_envelope,
};
use ed25519_dalek::SigningKey;

#[path = "../tests/support/mod.rs"]
mod support;

const NOW: u64 = 1_893_456_000;

struct ManualClock {
    unix: AtomicU64,
    monotonic: AtomicU64,
}

impl ManualClock {
    fn new() -> Self {
        Self {
            unix: AtomicU64::new(NOW),
            monotonic: AtomicU64::new(0),
        }
    }

    fn set_monotonic(&self, value: u64) {
        self.monotonic.store(value, Ordering::SeqCst);
    }
}

impl SessionClock for ManualClock {
    fn unix_seconds(&self) -> u64 {
        self.unix.load(Ordering::SeqCst)
    }

    fn monotonic_seconds(&self) -> u64 {
        self.monotonic.load(Ordering::SeqCst)
    }
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn admission() -> DestinationAdmission {
    DestinationAdmission::new(AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "service-a".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: [0xa0; 32],
            },
        )]),
        now: NOW,
        client_session_public_key: SigningKey::from_bytes(&[
            0x4c, 0xcd, 0x08, 0x9b, 0x28, 0xff, 0x96, 0xda, 0x9d, 0xb6, 0xc3, 0x46, 0xec, 0x11,
            0x4e, 0x0f, 0x5b, 0x8a, 0x31, 0x9f, 0x35, 0xab, 0xa6, 0x24, 0xda, 0x8c, 0xf6, 0xed,
            0x4f, 0xb8, 0xa6, 0xfb,
        ])
        .verifying_key()
        .to_bytes(),
        edge_nonce: [
            0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d,
            0x8e, 0x8f, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b,
            0x9c, 0x9d, 0x9e, 0x9f,
        ],
    })
    .expect("valid policy")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

async fn connection_pair() -> (
    TransportListener,
    crate::AuthenticatedConnection,
    crate::AuthenticatedConnection,
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

fn session(
    destination: &crate::AuthenticatedConnection,
    clock: Arc<ManualClock>,
) -> ControlSession {
    ControlSession::new_with_clock(
        destination,
        admission(),
        Vec::new(),
        TrustProfileId::new("test-profile").unwrap(),
        clock,
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn exact_hour_rejects_client_hello_without_mutating_handshake() {
    let (listener, source, destination) = connection_pair().await;
    let clock = Arc::new(ManualClock::new());
    let mut session = session(&destination, clock.clone());
    let hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        crate::CoreV02Limits::default(),
    )
    .unwrap();
    clock.set_monotonic(3_600);
    assert_eq!(
        session.accept_client_hello(&hello),
        Err(SessionReject::InvalidChannelState)
    );
    clock.set_monotonic(3_599);
    session.accept_client_hello(&hello).unwrap();
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn exact_hour_rejects_edge_hello_and_resume_scope_without_mutation() {
    let (listener, source, destination) = connection_pair().await;
    let clock = Arc::new(ManualClock::new());
    let mut session = session(&destination, clock.clone());
    let client = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        crate::CoreV02Limits::default(),
    )
    .unwrap();
    let edge = decode_control_envelope(
        &vector("artifacts/valid/envelopes/edge-hello.cbor"),
        crate::CoreV02Limits::default(),
    )
    .unwrap();
    session.accept_client_hello(&client).unwrap();
    clock.set_monotonic(3_600);
    assert_eq!(
        session.confirm_edge_hello(&edge),
        Err(SessionReject::InvalidChannelState)
    );
    clock.set_monotonic(3_599);
    session.confirm_edge_hello(&edge).unwrap();
    assert!(session.resume_scope().is_ok());
    assert_eq!(session.resume_time_authority().monotonic_seconds, 3_599);
    clock.set_monotonic(3_600);
    assert!(matches!(session.resume_scope(), Err(ResumeReject::Expired)));
    assert_eq!(session.resume_time_authority().monotonic_seconds, 3_600);
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}
