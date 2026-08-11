use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use crate::session::SessionClock;
use crate::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, DestinationAdmission, EdgeIdentity,
    EdgeRole, PeerPolicy, ResumeReject, RouteGrantIssuer, SessionReject, StreamCreditPreface,
    StreamCreditReject, TransportListener, TrustProfileId, build_client_config,
    build_server_config, connect, decode_control_envelope,
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

    fn set_unix(&self, value: u64) {
        self.unix.store(value, Ordering::SeqCst);
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
        authorized_services: BTreeMap::from([
            (
                "service-a".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: [0xa0; 32],
                },
            ),
            (
                "service.example".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: [
                        0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4,
                        0xe2, 0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22,
                        0x58, 0xd2, 0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                    ],
                },
            ),
        ]),
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

fn trusted_issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn credited_admission_commits_slot_and_replay_together_under_live_authority() {
    let (listener, source, destination) = connection_pair().await;
    let clock = Arc::new(ManualClock::new());
    let mut session = ControlSession::new_with_clock(
        &destination,
        admission(),
        vec![trusted_issuer()],
        TrustProfileId::new("test-profile").unwrap(),
        clock.clone(),
    );
    session
        .accept_client_hello(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/client-hello.cbor"),
                crate::CoreV02Limits::default(),
            )
            .unwrap(),
        )
        .unwrap();
    session
        .confirm_edge_hello(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/edge-hello.cbor"),
                crate::CoreV02Limits::default(),
            )
            .unwrap(),
        )
        .unwrap();
    let channel = session
        .accept_route_open(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/route-open.cbor"),
                crate::CoreV02Limits::default(),
            )
            .unwrap(),
        )
        .unwrap();
    assert_eq!(
        session.select_stream_credit_profile(channel.channel_id, true, None, false),
        Err(SessionReject::StreamCredit(StreamCreditReject::Downgrade))
    );
    session
        .select_stream_credit_profile(
            channel.channel_id,
            true,
            Some(crate::STREAM_CREDIT_PROFILE_ID),
            false,
        )
        .unwrap();
    session
        .confirm_route_accept(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/route-accept.cbor"),
                crate::CoreV02Limits::default(),
            )
            .unwrap(),
        )
        .unwrap();
    destination
        .bind_channel(&mut session, channel.channel_id)
        .unwrap();

    let preface = |slot, stream_id| StreamCreditPreface {
        channel_id: channel.channel_id,
        channel_generation: 1,
        credit_epoch: 1,
        credit_slot: slot,
        quic_stream_id: stream_id,
    };
    session.authorize_credited_stream(preface(0, 4)).unwrap();
    session
        .application_stream_permit(channel.channel_id, 4)
        .unwrap();
    assert_eq!(
        session.authorize_credited_stream(preface(1, 4)),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );
    session
        .authorize_credited_stream(preface(1, 8))
        .expect("P1F rejection did not consume slot one");
    assert_eq!(
        session.authorize_credited_stream(preface(1, 12)),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateSlot
        ))
    );
    clock.set_unix(u64::MAX);
    assert_eq!(
        session.authorize_credited_stream(preface(2, 12)),
        Err(SessionReject::StreamCredit(StreamCreditReject::Expired))
    );
    clock.set_unix(NOW);
    session
        .authorize_credited_stream(preface(2, 12))
        .expect("expiry rejection did not consume slot or replay state");
    clock.set_monotonic(3_600);
    assert_eq!(
        session.authorize_credited_stream(preface(3, 16)),
        Err(SessionReject::InvalidChannelState)
    );

    let mut legacy = ControlSession::new_with_clock(
        &destination,
        admission(),
        vec![trusted_issuer()],
        TrustProfileId::new("test-profile").unwrap(),
        Arc::new(ManualClock::new()),
    );
    for fixture in ["client-hello.cbor", "edge-hello.cbor"] {
        let envelope = decode_control_envelope(
            &vector(&format!("artifacts/valid/envelopes/{fixture}")),
            crate::CoreV02Limits::default(),
        )
        .unwrap();
        if fixture.starts_with("client") {
            legacy.accept_client_hello(&envelope).unwrap();
        } else {
            legacy.confirm_edge_hello(&envelope).unwrap();
        }
    }
    let legacy_channel = legacy
        .accept_route_open(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/route-open.cbor"),
                crate::CoreV02Limits::default(),
            )
            .unwrap(),
        )
        .unwrap();
    legacy
        .confirm_route_accept(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/route-accept.cbor"),
                crate::CoreV02Limits::default(),
            )
            .unwrap(),
        )
        .unwrap();
    destination
        .bind_channel(&mut legacy, legacy_channel.channel_id)
        .unwrap();
    assert_eq!(
        legacy.authorize_credited_stream(StreamCreditPreface {
            channel_id: legacy_channel.channel_id,
            channel_generation: 1,
            credit_epoch: 1,
            credit_slot: 0,
            quic_stream_id: 4,
        }),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::ProfileUnsupported
        ))
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
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

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn shared_absolute_clock_keeps_old_and_new_session_ages_independent() {
    let (listener, source, destination) = connection_pair().await;
    let clock = Arc::new(ManualClock::new());
    let old = session(&destination, clock.clone());
    assert_eq!(old.monotonic_created_at(), 0);
    assert_eq!(old.monotonic_hard_deadline(), 3_600);

    clock.set_monotonic(3_599);
    let new = session(&destination, clock.clone());
    assert_eq!(new.monotonic_created_at(), 3_599);
    assert_eq!(new.monotonic_hard_deadline(), 7_199);

    clock.set_monotonic(3_600);
    assert_eq!(old.monotonic_age(), 3_600);
    assert_eq!(new.monotonic_age(), 1);
    assert!(old.session_expired());
    assert!(!new.session_expired());
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}
