use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use quinn::{TransportConfig, VarInt};

use crate::channel_streams::ReplayHistoryLimit;
use crate::quinn_adapter::CreditedAdmissionCleanup;
use crate::session::SessionClock;
use crate::{
    ActiveChannel, AdmissionPolicy, AuthorizedServicePolicy, ControlSession, DestinationAdmission,
    EdgeIdentity, EdgeRole, PeerPolicy, ResumeReject, RouteGrantIssuer, SessionReject,
    SharedControlSession, StreamCreditPreface, StreamCreditReject, TransportListener,
    TrustProfileId, build_client_config, build_server_config, connect, decode_control_envelope,
    decode_stream_credit_preface, encode_stream_credit_preface,
};
use ed25519_dalek::SigningKey;

#[path = "../tests/support/mod.rs"]
mod support;

const NOW: u64 = 1_893_456_000;

struct ManualClock {
    unix: AtomicU64,
    unix_after_next_read: AtomicU64,
    monotonic: AtomicU64,
}

impl ManualClock {
    fn new() -> Self {
        Self {
            unix: AtomicU64::new(NOW),
            unix_after_next_read: AtomicU64::new(0),
            monotonic: AtomicU64::new(0),
        }
    }

    fn set_monotonic(&self, value: u64) {
        self.monotonic.store(value, Ordering::SeqCst);
    }

    fn set_unix(&self, value: u64) {
        self.unix.store(value, Ordering::SeqCst);
    }

    fn set_unix_after_next_read(&self, value: u64) {
        self.unix_after_next_read.store(value, Ordering::SeqCst);
    }
}

impl SessionClock for ManualClock {
    fn unix_seconds(&self) -> u64 {
        let current = self.unix.load(Ordering::SeqCst);
        let next = self.unix_after_next_read.swap(0, Ordering::SeqCst);
        if next != 0 {
            self.unix.store(next, Ordering::SeqCst);
        }
        current
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

async fn zero_source_receive_window_connection_pair() -> (
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
    let mut source_config = build_client_config(source_policy, pki.source_material()).unwrap();
    let mut transport = TransportConfig::default();
    transport.stream_receive_window(VarInt::from_u32(0));
    source_config.quinn.transport_config(Arc::new(transport));
    let (destination, source) = tokio::join!(listener.accept_one(), connect(source_config, remote));
    (listener, source.unwrap(), destination.unwrap())
}

async fn prime_control_stream(
    source: &crate::AuthenticatedConnection,
    destination: &crate::AuthenticatedConnection,
) {
    let hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        crate::CoreV02Limits::default(),
    )
    .unwrap();
    let mut source_control = source.open_control_stream().await.unwrap();
    source_control.send_envelope(&hello).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    destination_control
        .receive_envelope(crate::CoreV02Limits::default())
        .await
        .unwrap();
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

fn credited_session(
    destination: &crate::AuthenticatedConnection,
    clock: Arc<ManualClock>,
    replay_history_limit: ReplayHistoryLimit,
) -> (ControlSession, ActiveChannel) {
    let mut session = ControlSession::new_with_clock_and_replay_history_limit(
        destination,
        admission(),
        vec![trusted_issuer()],
        TrustProfileId::new("test-profile").unwrap(),
        clock,
        replay_history_limit,
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
    (session, channel)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn dropping_destination_admission_before_accept_releases_live_but_retains_credit_and_p1f() {
    let (listener, source, destination) = connection_pair().await;
    let (mut session, channel) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    let channel_id = channel.channel_id;
    session
        .authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 0,
                quic_stream_id: 4,
            },
            4,
        )
        .unwrap();
    let shared = SharedControlSession::new(session);

    drop(CreditedAdmissionCleanup::new(shared.clone(), channel_id, 4));

    assert!(
        shared
            .inspect(|session| session.application_stream_permit(channel_id, 4))
            .is_err()
    );
    assert_eq!(
        shared.update(|session| session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        )),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );
    assert_eq!(
        shared.inspect(|session| session.stream_credit_test_state(channel_id, 1)),
        (true, true, Some(1), false)
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn aborting_destination_future_blocked_before_accept_releases_committed_live_entry() {
    let (listener, source, destination) = zero_source_receive_window_connection_pair().await;
    prime_control_stream(&source, &destination).await;
    let source = Arc::new(source);
    let destination = Arc::new(destination);
    let (source_session, channel) = credited_session(
        &source,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    let source_session = SharedControlSession::new(source_session);
    let (destination_session, _) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    let destination_session = SharedControlSession::new(destination_session);
    let channel_id = channel.channel_id;

    let opening_connection = Arc::clone(&source);
    let opening_session = source_session.clone();
    let opening = tokio::spawn(async move {
        opening_connection
            .open_credited_session_stream(&opening_session, channel_id)
            .await
    });
    let accepting_connection = Arc::clone(&destination);
    let accepting_session = destination_session.clone();
    let mut accepting = tokio::spawn(async move {
        accepting_connection
            .accept_credited_session_stream(&accepting_session, channel_id)
            .await
    });

    tokio::time::timeout(Duration::from_secs(1), async {
        loop {
            if destination_session
                .inspect(|session| session.application_stream_permit(channel_id, 4))
                .is_ok()
            {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("destination commits before its flow-control-blocked ACCEPT write");
    assert!(
        tokio::time::timeout(Duration::from_millis(25), &mut accepting)
            .await
            .is_err()
    );

    accepting.abort();
    let cancellation = match accepting.await {
        Err(error) => error,
        Ok(_) => panic!("aborted destination admission unexpectedly completed"),
    };
    assert!(cancellation.is_cancelled());
    assert!(
        destination_session
            .inspect(|session| session.application_stream_permit(channel_id, 4))
            .is_err()
    );
    assert_eq!(
        destination_session.update(|session| session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 1,
                quic_stream_id: 4,
            },
            4,
        )),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );
    assert_eq!(
        destination_session.inspect(|session| session.stream_credit_test_state(channel_id, 1)),
        (true, true, Some(1), false)
    );

    let opening_result = tokio::time::timeout(Duration::from_secs(1), opening)
        .await
        .expect("destination cancellation resets the source admission")
        .expect("source admission task did not panic");
    assert_eq!(
        opening_result.err(),
        Some(crate::TransportError::ApplicationStreamRejected)
    );

    Arc::try_unwrap(source)
        .ok()
        .expect("all source task owners dropped")
        .close()
        .await
        .unwrap();
    Arc::try_unwrap(destination)
        .ok()
        .expect("all destination task owners dropped")
        .close()
        .await
        .unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn terminal_cleanup_removes_live_entry_after_session_starts_closing() {
    let (listener, source, destination) = connection_pair().await;
    let (mut session, channel) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    let channel_id = channel.channel_id;
    session.allocate_credited_stream(channel_id, 4).unwrap();
    session.begin_session_drain(0, NOW, 1).unwrap();
    assert_eq!(
        session.release_stream(channel_id, 4),
        Err(SessionReject::InvalidChannelState)
    );

    assert!(session.release_credited_stream_terminal(channel_id, 4));
    assert!(!session.release_credited_stream_terminal(channel_id, 4));
    assert_eq!(
        session.stream_credit_test_state(channel_id, 1),
        (true, true, None, false),
        "closing hides the no-longer-live binding bitmap but retains its bounded window"
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn terminal_cleanup_removes_live_entry_after_session_expires() {
    let (listener, source, destination) = connection_pair().await;
    let clock = Arc::new(ManualClock::new());
    let (mut session, channel) =
        credited_session(&destination, clock.clone(), ReplayHistoryLimit::MAX);
    let channel_id = channel.channel_id;
    session.allocate_credited_stream(channel_id, 4).unwrap();
    clock.set_monotonic(3_600);
    assert_eq!(
        session.release_stream(channel_id, 4),
        Err(SessionReject::InvalidChannelState)
    );

    assert!(session.release_credited_stream_terminal(channel_id, 4));
    assert!(!session.release_credited_stream_terminal(channel_id, 4));
    assert_eq!(
        session.stream_credit_test_state(channel_id, 1),
        (true, true, Some(1), false)
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn revocation_after_preface_parse_before_commit_is_rechecked() {
    let (listener, source, destination) = connection_pair().await;
    let (mut session, channel) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    let preface = StreamCreditPreface {
        channel_id: channel.channel_id,
        channel_generation: 1,
        credit_epoch: 1,
        credit_slot: 0,
        quic_stream_id: 4,
    };
    let context = session
        .credited_stream_context(channel.channel_id, 4)
        .unwrap();
    let wire = encode_stream_credit_preface(&preface).unwrap();
    let parsed = decode_stream_credit_preface(&wire, context).unwrap();

    session.revoke_channel(channel.channel_id, NOW).unwrap();

    assert_eq!(
        session.authorize_credited_stream(parsed, 4),
        Err(SessionReject::InvalidChannelState)
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
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
    assert_eq!(
        session.authorize_credited_stream(preface(0, 4), 8),
        Err(SessionReject::StreamCredit(StreamCreditReject::WrongStream))
    );
    session
        .authorize_credited_stream(preface(0, 4), 4)
        .expect("mismatched actual stream did not consume credit or replay state");
    session
        .application_stream_permit(channel.channel_id, 4)
        .unwrap();
    assert_eq!(
        session.authorize_credited_stream(preface(1, 4), 4),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateStream
        ))
    );
    session
        .authorize_credited_stream(preface(1, 8), 8)
        .expect("P1F rejection did not consume slot one");
    assert_eq!(
        session.authorize_credited_stream(preface(1, 12), 12),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::DuplicateSlot
        ))
    );
    clock.set_unix(u64::MAX);
    assert_eq!(
        session.authorize_credited_stream(preface(2, 12), 12),
        Err(SessionReject::StreamCredit(StreamCreditReject::Expired))
    );
    clock.set_unix(NOW);
    session
        .authorize_credited_stream(preface(2, 12), 12)
        .expect("expiry rejection did not consume slot or replay state");
    clock.set_unix(NOW + 300);
    clock.set_unix_after_next_read(NOW + 301);
    assert_eq!(
        session.authorize_credited_stream(preface(3, 16), 16),
        Err(SessionReject::StreamCredit(StreamCreditReject::Expired))
    );
    clock.set_unix(NOW + 300);
    session
        .authorize_credited_stream(preface(3, 16), 16)
        .expect("post-audit expiry did not consume credit or replay state");
    clock.set_unix(NOW + 301);
    assert_eq!(
        session.authorize_credited_stream(preface(4, 20), 20),
        Err(SessionReject::StreamCredit(StreamCreditReject::Expired))
    );
    clock.set_unix(NOW);
    clock.set_monotonic(3_600);
    assert_eq!(
        session.authorize_credited_stream(preface(4, 20), 20),
        Err(SessionReject::InvalidChannelState)
    );
    clock.set_monotonic(0);
    session.revoke_channel(channel.channel_id, NOW).unwrap();
    assert_eq!(
        session.authorize_credited_stream(preface(4, 20), 20),
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
        legacy.authorize_credited_stream(
            StreamCreditPreface {
                channel_id: legacy_channel.channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 0,
                quic_stream_id: 4,
            },
            4,
        ),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::ProfileUnsupported
        ))
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn audit_full_rejection_leaves_credit_and_replay_uncommitted() {
    let (listener, source, destination) = connection_pair().await;
    let (mut session, channel) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    let preface = StreamCreditPreface {
        channel_id: channel.channel_id,
        channel_generation: 1,
        credit_epoch: 1,
        credit_slot: 0,
        quic_stream_id: 4,
    };

    session.fill_audit_for_test(channel.channel_id);
    assert_eq!(
        session.authorize_credited_stream(preface, 4),
        Err(SessionReject::AuditUnavailable)
    );
    assert_eq!(
        session.stream_credit_test_state(channel.channel_id, 1),
        (true, true, Some(0), false)
    );
    session.pop_audit_event().expect("one audit slot available");
    session
        .authorize_credited_stream(preface, 4)
        .expect("audit failure did not consume credit or replay state");
    assert_eq!(
        session.stream_credit_test_state(channel.channel_id, 1),
        (true, true, Some(1), false)
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn low_p1f_cap_rejection_does_not_consume_the_prepared_credit() {
    let (listener, source, destination) = connection_pair().await;
    let (mut session, channel) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::try_from(1).unwrap(),
    );
    let preface = |slot, stream_id| StreamCreditPreface {
        channel_id: channel.channel_id,
        channel_generation: 1,
        credit_epoch: 1,
        credit_slot: slot,
        quic_stream_id: stream_id,
    };

    session.authorize_credited_stream(preface(0, 4), 4).unwrap();
    assert_eq!(
        session.authorize_credited_stream(preface(1, 8), 8),
        Err(SessionReject::StreamCredit(
            StreamCreditReject::ReplayCapacity
        ))
    );
    assert_eq!(
        session.stream_credit_test_state(channel.channel_id, 1),
        (true, true, Some(1), false)
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn audit_unavailable_resume_rollback_always_clears_credit_authority() {
    let (listener, source, destination) = connection_pair().await;
    let (mut session, channel) = credited_session(
        &destination,
        Arc::new(ManualClock::new()),
        ReplayHistoryLimit::MAX,
    );
    assert_eq!(
        session.stream_credit_test_state(channel.channel_id, 1),
        (true, true, Some(0), false)
    );
    session.fill_audit_for_test(channel.channel_id);

    assert_eq!(
        session.rollback_resume_admission(channel.channel_id),
        Err(ResumeReject::AuditUnavailable)
    );
    assert_eq!(session.active_channels(), 0);
    assert_eq!(
        session.stream_credit_test_state(channel.channel_id, 1),
        (false, false, None, false)
    );
    assert_eq!(
        session.authorize_credited_stream(
            StreamCreditPreface {
                channel_id: channel.channel_id,
                channel_generation: 1,
                credit_epoch: 1,
                credit_slot: 0,
                quic_stream_id: 4,
            },
            4,
        ),
        Err(SessionReject::UnexpectedMessage)
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
