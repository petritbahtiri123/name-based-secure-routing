use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Duration;

use ed25519_dalek::{Signer, SigningKey};
use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuditAction, AuditOutcome, AuditReason,
    AuthorizedServicePolicy, ChannelState, ControlSession, CoreV02Envelope, CoreV02Limits,
    DestinationAdmission, DrainDeadline, DrainEnforcement, EdgeIdentity, EdgeRole, PeerPolicy,
    ResumeAdmissionReject, ResumeHandle, ResumePreflight, ResumeReject, RouteGrantIssuer,
    SameEdgeResumeManager, ServiceChannelContext, SessionReject, TransportListener, TrustProfileId,
    build_client_config, build_server_config, connect, decode_control_envelope,
};
use sha2::{Digest, Sha256};

mod support;

const NOW: u64 = 1_893_456_000;
const POLICY_HASH: [u8; 32] = [0x91; 32];
const ROUTE_GRANT_SEED: [u8; 32] = [
    0x9d, 0x61, 0xb1, 0x9d, 0xef, 0xfd, 0x5a, 0x60, 0xba, 0x84, 0x4a, 0xf4, 0x92, 0xec, 0x2c, 0xc4,
    0x44, 0x49, 0xc5, 0x69, 0x7b, 0x32, 0x69, 0x19, 0x70, 0x3b, 0xac, 0x03, 0x1c, 0xae, 0x7f, 0x60,
];
const SESSION_SEED: [u8; 32] = [
    0x4c, 0xcd, 0x08, 0x9b, 0x28, 0xff, 0x96, 0xda, 0x9d, 0xb6, 0xc3, 0x46, 0xec, 0x11, 0x4e, 0x0f,
    0x5b, 0x8a, 0x31, 0x9f, 0x35, 0xab, 0xa6, 0x24, 0xda, 0x8c, 0xf6, 0xed, 0x4f, 0xb8, 0xa6, 0xfb,
];
const KID: &[u8] = b"nbsr-test-route-grant-key";

#[test]
fn trust_profile_and_resume_handle_inputs_are_bounded_and_redacted() {
    assert!(TrustProfileId::new("regional-prod.1").is_ok());
    assert_eq!(
        TrustProfileId::new(""),
        Err(ResumeReject::InvalidTrustProfileId)
    );
    assert_eq!(
        TrustProfileId::new(&"a".repeat(65)),
        Err(ResumeReject::InvalidTrustProfileId)
    );
    assert_eq!(
        TrustProfileId::new("UPPERCASE"),
        Err(ResumeReject::InvalidTrustProfileId)
    );

    assert_eq!(ResumeHandle::new([0; 32]), Err(ResumeReject::InvalidHandle));
    let handle = ResumeHandle::new([0x5a; 32]).expect("caller-provided CSPRNG bytes");
    assert_eq!(format!("{handle:?}"), "ResumeHandle([REDACTED])");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn authenticated_session_creation_requires_a_caller_approved_trust_profile() {
    let (listener, source, destination) = connection_pair().await;
    assert_eq!(destination.negotiated_alpn(), nbsr_transport::ALPN);
    let mut wrong_version = client_hello(SessionSpec::new(0x10, 0x40, 0x20, 0x80)).encode();
    assert_eq!(&wrong_version[..3], &[0xa6, 0x00, 0x02]);
    wrong_version[2] = 0x01;
    assert!(decode_control_envelope(&wrong_version, CoreV02Limits::default()).is_err());
    let profile = TrustProfileId::new("regional-prod.1").expect("validated profile");
    let _session = ControlSession::new(
        &destination,
        DestinationAdmission::new(AdmissionPolicy {
            source_operator_id: "source.operator".into(),
            source_edge_id: "source.edge".into(),
            destination_operator_id: "destination.operator".into(),
            destination_edge_id: "destination.edge".into(),
            authorized_services: BTreeMap::new(),
            now: 1_893_456_000,
            client_session_public_key: [0x30; 32],
            edge_nonce: [0x80; 32],
        })
        .expect("admission policy"),
        Vec::new(),
        profile,
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn fresh_same_edge_authorization_returns_only_single_use_correlation() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let old_context = old.context();
    let old_exporter = old_destination
        .export_channel_binding(&old_context)
        .expect("old live exporter");
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");

    let handle = ResumeHandle::new([0xa5; 32]).expect("caller CSPRNG handle");
    let mut manager = SameEdgeResumeManager::new();
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle.clone(),
            100,
            NOW,
        )
        .expect("eligible close issues correlation");
    assert_eq!(manager.retained_records(), 1);

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let fresh_spec = SessionSpec::new(0x60, 0x70, 0x30, 0x90);
    let mut fresh_session =
        established_control_session(&new_destination, fresh_spec, "regional-prod.1");
    let preflight = new_destination
        .preflight_same_edge_resume(&mut manager, &handle, &mut fresh_session, 105)
        .expect("same edge preflight capability");
    assert!(matches!(
        new_destination.preflight_same_edge_resume(&mut manager, &handle, &mut fresh_session, 105,),
        Err(ResumeReject::Replay)
    ));
    let (route_open, route_accept) = signed_route(fresh_spec);
    let fresh_channel = new_destination
        .accept_route_open_for_resume(
            &mut manager,
            &preflight,
            &mut fresh_session,
            &route_open,
            105,
        )
        .expect("preflight-gated fresh signed RouteGrant and proof");
    fresh_session
        .confirm_route_accept(&route_accept)
        .expect("correlated ROUTE_ACCEPT");
    new_destination
        .bind_channel(&mut fresh_session, fresh_channel.channel_id)
        .expect("fresh live exporter binding");
    let mut fresh = EstablishedSession {
        session: fresh_session,
        channel: fresh_channel,
        spec: fresh_spec,
    };
    let fresh_context = fresh.context();
    let fresh_exporter = new_destination
        .export_channel_binding(&fresh_context)
        .expect("fresh live exporter");
    assert_ne!(old_exporter, fresh_exporter);
    let correlation = new_destination
        .consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut fresh.session,
            fresh.channel.channel_id,
            105,
            NOW + 5,
        )
        .expect("fresh authorization consumes once");
    assert_eq!(correlation.old_channel_id, old.channel.channel_id);
    assert_eq!(correlation.new_channel_id, fresh.channel.channel_id);
    assert_eq!(manager.retained_records(), 0);
    let audit_before_replay = fresh.session.audit_events().len();
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut fresh.session,
            fresh.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::Replay)
    );
    assert_eq!(fresh.session.audit_events().len(), audit_before_replay + 1);
    let replay = fresh
        .session
        .audit_events()
        .last()
        .expect("replay reject audit");
    assert_eq!(replay.action, AuditAction::ResumeRejected);
    assert_eq!(replay.reason, AuditReason::Replay);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn stale_authority_fields_and_unbound_channels_fail_without_consuming_the_handle() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let old_spec = SessionSpec::new(0x10, 0x40, 0x20, 0x80);
    let mut old = established_bound_session(&old_destination, old_spec, "regional-prod.1");
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let valid_spec = SessionSpec::new(0x60, 0x70, 0x30, 0x90);
    let mut valid = established_bound_session(&new_destination, valid_spec, "regional-prod.1");
    let mut manager = SameEdgeResumeManager::new();

    let cases = [
        (
            "same channel id",
            SessionSpec {
                channel_id: old_spec.channel_id,
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::FreshAuthorizationRequired,
        ),
        (
            "same grant digest route and nonce",
            SessionSpec {
                route_id: old_spec.route_id,
                grant_nonce: old_spec.grant_nonce,
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::FreshAuthorizationRequired,
        ),
        (
            "same route id",
            SessionSpec {
                route_id: old_spec.route_id,
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::FreshAuthorizationRequired,
        ),
        (
            "same grant nonce",
            SessionSpec {
                grant_nonce: old_spec.grant_nonce,
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::FreshAuthorizationRequired,
        ),
        (
            "same client nonce",
            SessionSpec {
                client_nonce: old_spec.client_nonce,
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::FreshAuthorizationRequired,
        ),
        (
            "same edge nonce",
            SessionSpec {
                edge_nonce: old_spec.edge_nonce,
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::FreshAuthorizationRequired,
        ),
        (
            "wrong service",
            SessionSpec {
                service_id: "service.other",
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::Mismatch,
        ),
        (
            "wrong policy hash",
            SessionSpec {
                policy_hash: [0x92; 32],
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::Mismatch,
        ),
        (
            "wrong client key",
            SessionSpec {
                session_seed: [0x42; 32],
                ..valid_spec
            },
            "regional-prod.1",
            true,
            ResumeReject::Mismatch,
        ),
        (
            "unbound new channel",
            valid_spec,
            "regional-prod.1",
            false,
            ResumeReject::Ineligible,
        ),
    ];

    for (index, (name, spec, trust_profile, bind, expected)) in cases.into_iter().enumerate() {
        let handle_bytes = [0xb0_u8.wrapping_add(index as u8); 32];
        let handle = ResumeHandle::new(handle_bytes).expect("unique caller handle");
        manager
            .issue(
                &mut old.session,
                old.channel.channel_id,
                handle.clone(),
                100,
                NOW,
            )
            .expect("independent record");
        let (mut attempt, preflight) = established_resume_session(
            &new_destination,
            &mut manager,
            &handle,
            spec,
            trust_profile,
            bind,
            105,
        );
        let audit_before = attempt.session.audit_events().len();
        assert_eq!(
            new_destination.consume_same_edge_resume(
                &mut manager,
                &preflight,
                &mut attempt.session,
                attempt.channel.channel_id,
                105,
                NOW + 5,
            ),
            Err(expected),
            "{name}"
        );
        assert_eq!(
            attempt.session.audit_events().len(),
            audit_before + 1,
            "{name}"
        );
        assert_eq!(
            attempt
                .session
                .audit_events()
                .last()
                .expect("typed reject audit")
                .action,
            AuditAction::ResumeRejected,
            "{name}"
        );
        assert_eq!(manager.retained_records(), index + 1, "{name}");
    }

    let wrong_trust_handle = ResumeHandle::new([0xcf; 32]).expect("wrong-trust handle");
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            wrong_trust_handle.clone(),
            100,
            NOW,
        )
        .expect("wrong-trust record");
    let mut wrong_trust =
        established_control_session(&new_destination, valid_spec, "regional-prod.2");
    assert_eq!(wrong_trust.active_channels(), 0);
    assert!(matches!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &wrong_trust_handle,
            &mut wrong_trust,
            105,
        ),
        Err(ResumeReject::Mismatch)
    ));
    assert_eq!(wrong_trust.active_channels(), 0);

    let adapter_handle = ResumeHandle::new([0xd2; 32]).expect("adapter handle");
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            adapter_handle.clone(),
            100,
            NOW,
        )
        .expect("adapter negative record");
    let adapter_preflight = new_destination
        .preflight_same_edge_resume(&mut manager, &adapter_handle, &mut valid.session, 105)
        .expect("adapter-bound preflight");
    let audit_before = valid.session.audit_events().len();
    assert_eq!(
        new_source.consume_same_edge_resume(
            &mut manager,
            &adapter_preflight,
            &mut valid.session,
            valid.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::FreshAuthorizationRequired)
    );
    assert_eq!(valid.session.audit_events().len(), audit_before + 1);
    let adapter_reject = valid
        .session
        .audit_events()
        .last()
        .expect("adapter reject audit");
    assert_eq!(adapter_reject.action, AuditAction::ResumeRejected);
    assert_eq!(
        adapter_reject.reason,
        AuditReason::FreshAuthorizationRequired
    );
    assert_eq!(manager.retained_records(), cases.len() + 2);

    drop(valid);
    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cross_edge_preflight_denies_before_channel_allocation_and_preserves_the_handle() {
    let old_pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&old_pki).await;
    let old_spec = SessionSpec::new(0x10, 0x40, 0x20, 0x80);
    let mut old = established_bound_session(&old_destination, old_spec, "regional-prod.1");
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let handle = ResumeHandle::new([0xe1; 32]).expect("caller handle");
    let mut manager = SameEdgeResumeManager::new();
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle.clone(),
            100,
            NOW,
        )
        .expect("eligible record");

    let other_pki = support::TestPki::generate_for("source.other", "destination.edge");
    let (other_listener, other_source, other_destination) =
        connection_pair_with_pki_for(&other_pki, "source.other", "destination.edge").await;
    let other_spec = SessionSpec {
        source_edge_id: "source.other",
        ..SessionSpec::new(0x60, 0x70, 0x30, 0x90)
    };
    let mut other = established_control_session(&other_destination, other_spec, "regional-prod.1");
    assert_eq!(other.active_channels(), 0);
    assert!(matches!(
        other_destination.preflight_same_edge_resume(&mut manager, &handle, &mut other, 105),
        Err(ResumeReject::CrossEdgeDenied)
    ));
    assert_eq!(other.active_channels(), 0);
    assert_eq!(manager.retained_records(), 1);
    let rejection = other
        .audit_events()
        .last()
        .expect("cross-edge reject audit");
    assert_eq!(rejection.action, AuditAction::ResumeRejected);
    assert_eq!(rejection.outcome, AuditOutcome::Denied);
    assert_eq!(rejection.reason, AuditReason::CrossEdge);

    let new_pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&new_pki).await;
    let fresh_spec = SessionSpec::new(0x61, 0x71, 0x31, 0x91);
    let mut fresh = established_control_session(&new_destination, fresh_spec, "regional-prod.1");
    let preflight = new_destination
        .preflight_same_edge_resume(&mut manager, &handle, &mut fresh, 105)
        .expect("exact same-edge preflight capability");

    let (other_route_open, _) = signed_route(other_spec);
    assert_eq!(other.active_channels(), 0);
    assert_eq!(
        other_destination.accept_route_open_for_resume(
            &mut manager,
            &preflight,
            &mut other,
            &other_route_open,
            105,
        ),
        Err(ResumeAdmissionReject::Resume(
            ResumeReject::FreshAuthorizationRequired
        ))
    );
    assert_eq!(other.active_channels(), 0);

    let (ordinary_open, ordinary_accept) = signed_route(fresh_spec);
    let ordinary_channel = fresh
        .accept_route_open(&ordinary_open)
        .expect("ordinary admission remains independently available");
    fresh
        .confirm_route_accept(&ordinary_accept)
        .expect("ordinary correlated ROUTE_ACCEPT");
    new_destination
        .bind_channel(&mut fresh, ordinary_channel.channel_id)
        .expect("ordinary channel binding");
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut fresh,
            ordinary_channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::FreshAuthorizationRequired)
    );
    assert_eq!(manager.retained_records(), 1);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    other_source.close().await.expect("other source close");
    other_destination
        .close()
        .await
        .expect("other destination close");
    other_listener.close().await.expect("other listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn preflight_capability_is_bound_to_its_exact_manager_even_when_ids_collide() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let handle_a = ResumeHandle::new([0xeb; 32]).expect("manager A handle");
    let handle_b = ResumeHandle::new([0xec; 32]).expect("manager B handle");
    let mut manager_a = SameEdgeResumeManager::new();
    let mut manager_b = SameEdgeResumeManager::new();
    manager_a
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle_a.clone(),
            100,
            NOW,
        )
        .expect("manager A record");
    manager_b
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle_b.clone(),
            100,
            NOW,
        )
        .expect("manager B record");

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let mut session_a = established_control_session(
        &new_destination,
        SessionSpec::new(0x60, 0x70, 0x30, 0x90),
        "regional-prod.1",
    );
    let preflight_a = new_destination
        .preflight_same_edge_resume(&mut manager_a, &handle_a, &mut session_a, 105)
        .expect("manager A first preflight");

    let spec_b = SessionSpec::new(0x61, 0x71, 0x31, 0x91);
    let mut session_b = established_control_session(&new_destination, spec_b, "regional-prod.1");
    let preflight_b = new_destination
        .preflight_same_edge_resume(&mut manager_b, &handle_b, &mut session_b, 105)
        .expect("manager B first preflight");
    let (route_open, route_accept) = signed_route(spec_b);
    assert_eq!(session_b.candidate_channels(), 0);
    assert_eq!(session_b.active_channels(), 0);
    assert_eq!(
        new_destination.accept_route_open_for_resume(
            &mut manager_b,
            &preflight_a,
            &mut session_b,
            &route_open,
            105,
        ),
        Err(ResumeAdmissionReject::Resume(ResumeReject::Replay))
    );
    assert_eq!(session_b.candidate_channels(), 0);
    assert_eq!(session_b.active_channels(), 0);

    let channel_b = new_destination
        .accept_route_open_for_resume(
            &mut manager_b,
            &preflight_b,
            &mut session_b,
            &route_open,
            105,
        )
        .expect("manager B capability remains valid");
    session_b
        .confirm_route_accept(&route_accept)
        .expect("manager B correlated ROUTE_ACCEPT");
    new_destination
        .bind_channel(&mut session_b, channel_b.channel_id)
        .expect("manager B fresh binding");
    assert!(
        new_destination
            .consume_same_edge_resume(
                &mut manager_b,
                &preflight_b,
                &mut session_b,
                channel_b.channel_id,
                105,
                NOW + 5,
            )
            .is_ok()
    );
    assert_eq!(manager_a.retained_records(), 1);
    assert_eq!(manager_b.retained_records(), 0);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn retention_is_terminal_after_31_seconds_and_never_exceeds_authority_deadlines() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut manager = SameEdgeResumeManager::new();

    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let at_30 = ResumeHandle::new([0xf0; 32]).expect("30 second handle");
    let at_31 = ResumeHandle::new([0xf1; 32]).expect("31 second handle");
    for handle in [at_30.clone(), at_31.clone()] {
        manager
            .issue(&mut old.session, old.channel.channel_id, handle, 100, NOW)
            .expect("30 second record");
    }

    let grant_spec = SessionSpec {
        grant_expires_at: NOW + 5,
        ..SessionSpec::new(0x11, 0x41, 0x21, 0x81)
    };
    let mut grant_limited =
        established_bound_session(&old_destination, grant_spec, "regional-prod.1");
    let close = route_close(&grant_limited, 0x52);
    old_destination
        .accept_route_close(
            &mut grant_limited.session,
            grant_limited.channel.channel_id,
            &close,
        )
        .expect("grant-limited normal close");
    let grant_handle = ResumeHandle::new([0xf2; 32]).expect("grant handle");
    manager
        .issue(
            &mut grant_limited.session,
            grant_limited.channel.channel_id,
            grant_handle.clone(),
            100,
            NOW,
        )
        .expect("grant-limited record");

    let session_spec = SessionSpec::new(0x12, 0x42, 0x22, 0x82);
    let mut session_limited = established_session_with_deadline(
        &old_destination,
        session_spec,
        "regional-prod.1",
        DrainDeadline::new(100, 7).expect("session authority deadline"),
    );
    let close = route_close(&session_limited, 0x53);
    old_destination
        .accept_route_close(
            &mut session_limited.session,
            session_limited.channel.channel_id,
            &close,
        )
        .expect("session-limited normal close");
    let session_handle = ResumeHandle::new([0xf3; 32]).expect("session handle");
    manager
        .issue(
            &mut session_limited.session,
            session_limited.channel.channel_id,
            session_handle.clone(),
            100,
            NOW,
        )
        .expect("session-limited record");

    let expired_spec = SessionSpec {
        grant_expires_at: NOW + 1,
        ..SessionSpec::new(0x13, 0x43, 0x23, 0x83)
    };
    let mut expired = established_bound_session(&old_destination, expired_spec, "regional-prod.1");
    let close = route_close(&expired, 0x54);
    old_destination
        .accept_route_close(&mut expired.session, expired.channel.channel_id, &close)
        .expect("expired-record normal close");
    assert_eq!(
        manager.issue(
            &mut expired.session,
            expired.channel.channel_id,
            ResumeHandle::new([0xf4; 32]).expect("expired handle"),
            102,
            NOW + 2,
        ),
        Err(ResumeReject::Expired)
    );
    assert_eq!(
        expired
            .session
            .audit_events()
            .last()
            .map(|event| event.action),
        Some(AuditAction::ResumeRejected)
    );

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let (mut fresh, at_30_preflight) = established_resume_session(
        &new_destination,
        &mut manager,
        &at_30,
        SessionSpec::new(0x60, 0x70, 0x30, 0x90),
        "regional-prod.1",
        true,
        130,
    );
    new_destination
        .preflight_same_edge_resume(&mut manager, &grant_handle, &mut fresh.session, 105)
        .expect("grant expiry remains valid at exact equality");
    assert!(
        new_destination
            .consume_same_edge_resume(
                &mut manager,
                &at_30_preflight,
                &mut fresh.session,
                fresh.channel.channel_id,
                130,
                NOW + 30,
            )
            .is_ok()
    );
    assert_eq!(
        new_destination.preflight_same_edge_resume(&mut manager, &at_31, &mut fresh.session, 131),
        Err(ResumeReject::Expired)
    );
    assert_eq!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &grant_handle,
            &mut fresh.session,
            106,
        ),
        Err(ResumeReject::Expired)
    );
    assert_eq!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &session_handle,
            &mut fresh.session,
            108,
        ),
        Err(ResumeReject::Expired)
    );
    assert_eq!(manager.retained_records(), 0);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn expired_or_draining_new_session_is_rejected_before_resume_preflight() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let expired_handle = ResumeHandle::new([0xe2; 32]).expect("expired-session handle");
    let draining_handle = ResumeHandle::new([0xe3; 32]).expect("draining-session handle");
    let mut manager = SameEdgeResumeManager::new();
    for handle in [expired_handle.clone(), draining_handle.clone()] {
        manager
            .issue(&mut old.session, old.channel.channel_id, handle, 100, NOW)
            .expect("eligible old correlation");
    }

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let mut expired = established_session_with_deadline(
        &new_destination,
        SessionSpec::new(0x60, 0x70, 0x30, 0x90),
        "regional-prod.1",
        DrainDeadline::new(100, 5).expect("exact session authority deadline"),
    );
    assert_eq!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &expired_handle,
            &mut expired.session,
            105,
        ),
        Err(ResumeReject::Expired)
    );
    assert_eq!(
        expired
            .session
            .audit_events()
            .last()
            .expect("expired session rejection audit")
            .reason,
        AuditReason::Expired
    );

    let mut draining = established_bound_session(
        &new_destination,
        SessionSpec::new(0x61, 0x71, 0x31, 0x91),
        "regional-prod.1",
    );
    draining
        .session
        .begin_session_drain(100, NOW, 30)
        .expect("session enters draining state");
    assert_eq!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &draining_handle,
            &mut draining.session,
            105,
        ),
        Err(ResumeReject::Ineligible)
    );
    assert_eq!(manager.retained_records(), 2);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn locally_or_peer_closed_quinn_connection_is_not_live_for_resume_preflight() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let peer_handle = ResumeHandle::new([0xe4; 32]).expect("peer-close handle");
    let local_handle = ResumeHandle::new([0xe5; 32]).expect("local-close handle");
    let mut manager = SameEdgeResumeManager::new();
    for handle in [peer_handle.clone(), local_handle.clone()] {
        manager
            .issue(&mut old.session, old.channel.channel_id, handle, 100, NOW)
            .expect("eligible old correlation");
    }

    let (peer_listener, peer_source, peer_destination) = connection_pair_with_pki(&pki).await;
    let (mut peer_session, peer_preflight) = established_resume_session(
        &peer_destination,
        &mut manager,
        &peer_handle,
        SessionSpec::new(0x60, 0x70, 0x30, 0x90),
        "regional-prod.1",
        true,
        105,
    );
    peer_source.close().await.expect("peer closes connection");
    assert_eq!(
        peer_destination.consume_same_edge_resume(
            &mut manager,
            &peer_preflight,
            &mut peer_session.session,
            peer_session.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::Ineligible)
    );

    let (local_listener, local_source, local_destination) = connection_pair_with_pki(&pki).await;
    let mut closing_session = established_control_session(
        &local_destination,
        SessionSpec::new(0x61, 0x71, 0x31, 0x91),
        "regional-prod.1",
    );
    let mut still_active_session = established_control_session(
        &local_destination,
        SessionSpec::new(0x62, 0x72, 0x32, 0x92),
        "regional-prod.1",
    );
    closing_session
        .begin_session_drain(105, NOW + 5, 0)
        .expect("zero-second local drain");
    local_destination
        .enforce_session_drain(&mut closing_session, 105)
        .await
        .expect("adapter closes exact Quinn connection");
    assert_eq!(
        local_destination.preflight_same_edge_resume(
            &mut manager,
            &local_handle,
            &mut still_active_session,
            105,
        ),
        Err(ResumeReject::Ineligible)
    );
    assert_eq!(manager.retained_records(), 2);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    peer_destination
        .close()
        .await
        .expect("peer-closed destination cleanup");
    peer_listener.close().await.expect("peer listener close");
    local_source
        .close()
        .await
        .expect("locally closed source cleanup");
    local_destination
        .close()
        .await
        .expect("locally closed destination cleanup");
    local_listener.close().await.expect("local listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn reused_transport_authority_is_rejected_by_preflight_before_channel_allocation() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let old_spec = SessionSpec::new(0x10, 0x40, 0x20, 0x80);
    let mut old = established_bound_session(&old_destination, old_spec, "regional-prod.1");
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let handles = [
        ResumeHandle::new([0xe8; 32]).expect("same-connection handle"),
        ResumeHandle::new([0xe9; 32]).expect("same-session handle"),
        ResumeHandle::new([0xea; 32]).expect("wrong-role handle"),
    ];
    let mut manager = SameEdgeResumeManager::new();
    for handle in handles.iter().cloned() {
        manager
            .issue(&mut old.session, old.channel.channel_id, handle, 100, NOW)
            .expect("independent eligible correlation");
    }

    let mut same_connection = established_control_session(
        &old_destination,
        SessionSpec::new(0x60, 0x70, 0x30, 0x90),
        "regional-prod.1",
    );
    assert_eq!(same_connection.candidate_channels(), 0);
    assert_eq!(same_connection.active_channels(), 0);
    assert!(matches!(
        old_destination.preflight_same_edge_resume(
            &mut manager,
            &handles[0],
            &mut same_connection,
            105,
        ),
        Err(ResumeReject::FreshAuthorizationRequired)
    ));
    assert_eq!(same_connection.candidate_channels(), 0);
    assert_eq!(same_connection.active_channels(), 0);

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let mut same_session = established_control_session(
        &new_destination,
        SessionSpec {
            session_id: old_spec.session_id,
            ..SessionSpec::new(0x61, 0x71, 0x31, 0x91)
        },
        "regional-prod.1",
    );
    assert_eq!(same_session.candidate_channels(), 0);
    assert_eq!(same_session.active_channels(), 0);
    assert!(matches!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &handles[1],
            &mut same_session,
            105,
        ),
        Err(ResumeReject::FreshAuthorizationRequired)
    ));
    assert_eq!(same_session.candidate_channels(), 0);
    assert_eq!(same_session.active_channels(), 0);

    let mut wrong_role_and_peer = established_control_session(
        &new_source,
        SessionSpec::new(0x62, 0x72, 0x32, 0x92),
        "regional-prod.1",
    );
    assert_eq!(wrong_role_and_peer.candidate_channels(), 0);
    assert_eq!(wrong_role_and_peer.active_channels(), 0);
    assert!(matches!(
        new_source.preflight_same_edge_resume(
            &mut manager,
            &handles[2],
            &mut wrong_role_and_peer,
            105,
        ),
        Err(ResumeReject::FreshAuthorizationRequired)
    ));
    assert_eq!(wrong_role_and_peer.candidate_channels(), 0);
    assert_eq!(wrong_role_and_peer.active_channels(), 0);
    assert_eq!(manager.retained_records(), 3);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn store_retains_4096_unique_handles_and_rejects_4097_without_eviction() {
    let (listener, source, destination) = connection_pair().await;
    let mut old = established_bound_session(
        &destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    while old.session.pop_audit_event().is_some() {}

    let mut manager = SameEdgeResumeManager::new();
    for index in 1..=4_096_u64 {
        manager
            .issue(
                &mut old.session,
                old.channel.channel_id,
                indexed_handle(index),
                100,
                NOW,
            )
            .expect("first 4096 records");
        let event = old.session.pop_audit_event().expect("one issue audit");
        assert_eq!(event.action, AuditAction::ResumeIssued);
    }
    assert_eq!(manager.retained_records(), 4_096);

    assert_eq!(
        manager.issue(
            &mut old.session,
            old.channel.channel_id,
            indexed_handle(4_097),
            100,
            NOW,
        ),
        Err(ResumeReject::Capacity)
    );
    assert_eq!(manager.retained_records(), 4_096);
    let rejected = old.session.audit_events().last().expect("capacity audit");
    assert_eq!(rejected.action, AuditAction::ResumeRejected);
    assert_eq!(rejected.outcome, AuditOutcome::Denied);
    assert_eq!(rejected.reason, AuditReason::Capacity);

    while old.session.audit_events().len() < 1_024 {
        assert_eq!(
            manager.issue(
                &mut old.session,
                old.channel.channel_id,
                indexed_handle(1),
                100,
                NOW,
            ),
            Err(ResumeReject::Replay)
        );
    }
    assert_eq!(
        manager.issue(
            &mut old.session,
            old.channel.channel_id,
            indexed_handle(4_097),
            131,
            NOW + 31,
        ),
        Err(ResumeReject::AuditUnavailable)
    );
    assert_eq!(manager.retained_records(), 4_096);

    while old.session.pop_audit_event().is_some() {}
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            indexed_handle(1),
            131,
            NOW + 31,
        )
        .expect("all expired records are purged before replay and capacity decisions");
    assert_eq!(manager.retained_records(), 1);
    let purge = old
        .session
        .pop_audit_event()
        .expect("one bounded purge audit");
    assert_eq!(purge.action, AuditAction::ResumePurged);
    assert_eq!(purge.reason, AuditReason::Expired);
    let issued = old.session.pop_audit_event().expect("new issue audit");
    assert_eq!(issued.action, AuditAction::ResumeIssued);
    assert!(old.session.pop_audit_event().is_none());

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn exclusive_authority_deadline_blocks_consume_and_unlocks_capacity_at_equality() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut authority_limited = established_session_with_deadline(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
        DrainDeadline::new(100, 30).expect("exclusive authority deadline"),
    );
    let close = route_close(&authority_limited, 0x51);
    old_destination
        .accept_route_close(
            &mut authority_limited.session,
            authority_limited.channel.channel_id,
            &close,
        )
        .expect("normal bound close");
    while authority_limited.session.pop_audit_event().is_some() {}

    let mut manager = SameEdgeResumeManager::new();
    for index in 30_001..=34_096_u64 {
        manager
            .issue(
                &mut authority_limited.session,
                authority_limited.channel.channel_id,
                indexed_handle(index),
                100,
                NOW,
            )
            .expect("4096 authority-capped records");
        authority_limited
            .session
            .pop_audit_event()
            .expect("one issue audit");
    }
    assert_eq!(manager.retained_records(), 4_096);

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let handle = indexed_handle(30_001);
    let (mut fresh, preflight) = established_resume_session(
        &new_destination,
        &mut manager,
        &handle,
        SessionSpec::new(0x60, 0x70, 0x30, 0x90),
        "regional-prod.1",
        true,
        129,
    );
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut fresh.session,
            fresh.channel.channel_id,
            130,
            NOW + 30,
        ),
        Err(ResumeReject::Expired)
    );
    assert_eq!(manager.retained_records(), 4_095);

    let mut replacement = established_bound_session(
        &old_destination,
        SessionSpec::new(0x11, 0x41, 0x21, 0x81),
        "regional-prod.1",
    );
    let close = route_close(&replacement, 0x52);
    old_destination
        .accept_route_close(
            &mut replacement.session,
            replacement.channel.channel_id,
            &close,
        )
        .expect("replacement normal close");
    let audit_before = replacement.session.audit_events().len();
    manager
        .issue(
            &mut replacement.session,
            replacement.channel.channel_id,
            indexed_handle(40_000),
            130,
            NOW + 30,
        )
        .expect("exclusive-deadline purge unlocks capacity at equality");
    assert_eq!(manager.retained_records(), 1);
    let issue_events: Vec<_> = replacement
        .session
        .audit_events()
        .skip(audit_before)
        .map(|event| event.action)
        .collect();
    assert_eq!(
        issue_events,
        vec![AuditAction::ResumePurged, AuditAction::ResumeIssued]
    );

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn expired_fresh_grant_is_audited_then_consumes_the_resume_handle() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let handle = ResumeHandle::new([0xe6; 32]).expect("terminal-expiry handle");
    let mut manager = SameEdgeResumeManager::new();
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle.clone(),
            100,
            NOW,
        )
        .expect("eligible old correlation");

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let expired_spec = SessionSpec {
        grant_expires_at: NOW + 4,
        ..SessionSpec::new(0x60, 0x70, 0x30, 0x90)
    };
    let (mut expired, preflight) = established_resume_session(
        &new_destination,
        &mut manager,
        &handle,
        expired_spec,
        "regional-prod.1",
        true,
        105,
    );
    let missing = ResumeHandle::new([0xe7; 32]).expect("missing handle");
    while expired.session.audit_events().len() < 1_024 {
        assert_eq!(
            new_destination.preflight_same_edge_resume(
                &mut manager,
                &missing,
                &mut expired.session,
                105,
            ),
            Err(ResumeReject::Replay)
        );
    }
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut expired.session,
            expired.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::AuditUnavailable)
    );
    assert_eq!(manager.retained_records(), 1);

    expired
        .session
        .pop_audit_event()
        .expect("make one audit slot available");
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut expired.session,
            expired.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::Expired)
    );
    assert_eq!(manager.retained_records(), 0);
    let expiry = expired
        .session
        .audit_events()
        .last()
        .expect("terminal expiry audit");
    assert_eq!(expiry.action, AuditAction::ResumeRejected);
    assert_eq!(expiry.reason, AuditReason::Expired);

    let mut later = established_bound_session(
        &new_destination,
        SessionSpec::new(0x61, 0x71, 0x31, 0x91),
        "regional-prod.1",
    );
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut later.session,
            later.channel.channel_id,
            106,
            NOW + 6,
        ),
        Err(ResumeReject::Replay)
    );

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn audited_post_admission_mismatch_retires_only_preflight_and_allows_fresh_retry() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let handle = ResumeHandle::new([0xed; 32]).expect("mismatch retry handle");
    let mut manager = SameEdgeResumeManager::new();
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle.clone(),
            100,
            NOW,
        )
        .expect("eligible old correlation");

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let mismatch_spec = SessionSpec {
        policy_hash: [0x92; 32],
        ..SessionSpec::new(0x60, 0x70, 0x30, 0x90)
    };
    let (mut mismatch, stale_preflight) = established_resume_session(
        &new_destination,
        &mut manager,
        &handle,
        mismatch_spec,
        "regional-prod.1",
        true,
        105,
    );
    let missing = ResumeHandle::new([0xee; 32]).expect("missing audit filler");
    while mismatch.session.audit_events().len() < 1_024 {
        assert_eq!(
            new_destination.preflight_same_edge_resume(
                &mut manager,
                &missing,
                &mut mismatch.session,
                105,
            ),
            Err(ResumeReject::Replay)
        );
    }
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &stale_preflight,
            &mut mismatch.session,
            mismatch.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::AuditUnavailable)
    );
    assert_eq!(manager.retained_records(), 1);

    mismatch
        .session
        .pop_audit_event()
        .expect("make mismatch audit slot available");
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &stale_preflight,
            &mut mismatch.session,
            mismatch.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::Mismatch)
    );
    assert_eq!(manager.retained_records(), 1);

    mismatch
        .session
        .pop_audit_event()
        .expect("make replay audit slot available");
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &stale_preflight,
            &mut mismatch.session,
            mismatch.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::Replay)
    );

    let (mut fresh, fresh_preflight) = established_resume_session(
        &new_destination,
        &mut manager,
        &handle,
        SessionSpec::new(0x61, 0x71, 0x31, 0x91),
        "regional-prod.1",
        true,
        106,
    );
    assert!(
        new_destination
            .consume_same_edge_resume(
                &mut manager,
                &fresh_preflight,
                &mut fresh.session,
                fresh.channel.channel_id,
                106,
                NOW + 6,
            )
            .is_ok()
    );
    assert_eq!(manager.retained_records(), 0);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn audit_exhaustion_rejects_issue_and_consume_before_store_mutation() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    while old.session.pop_audit_event().is_some() {}
    let valid_handle = ResumeHandle::new([0xa1; 32]).expect("valid handle");
    let mut manager = SameEdgeResumeManager::new();
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            valid_handle.clone(),
            100,
            NOW,
        )
        .expect("one retained record");
    while old.session.audit_events().len() < 1_024 {
        assert_eq!(
            manager.issue(
                &mut old.session,
                old.channel.channel_id,
                valid_handle.clone(),
                100,
                NOW,
            ),
            Err(ResumeReject::Replay)
        );
    }
    assert_eq!(
        manager.issue(
            &mut old.session,
            old.channel.channel_id,
            ResumeHandle::new([0xa2; 32]).expect("new handle"),
            100,
            NOW,
        ),
        Err(ResumeReject::AuditUnavailable)
    );
    assert_eq!(manager.retained_records(), 1);

    let mut wrong_profile_old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x11, 0x41, 0x21, 0x81),
        "regional-prod.2",
    );
    let close = route_close(&wrong_profile_old, 0x52);
    old_destination
        .accept_route_close(
            &mut wrong_profile_old.session,
            wrong_profile_old.channel.channel_id,
            &close,
        )
        .expect("wrong-profile normal close");
    let mismatch_handle = ResumeHandle::new([0xa3; 32]).expect("mismatch handle");
    manager
        .issue(
            &mut wrong_profile_old.session,
            wrong_profile_old.channel.channel_id,
            mismatch_handle.clone(),
            100,
            NOW,
        )
        .expect("mismatch record");

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let fresh_spec = SessionSpec::new(0x60, 0x70, 0x30, 0x90);
    let mut fresh_session =
        established_control_session(&new_destination, fresh_spec, "regional-prod.1");
    let missing_handle = ResumeHandle::new([0xa4; 32]).expect("missing preflight handle");
    while fresh_session.audit_events().len() < 1_024 {
        assert_eq!(
            new_destination.preflight_same_edge_resume(
                &mut manager,
                &missing_handle,
                &mut fresh_session,
                105,
            ),
            Err(ResumeReject::Replay)
        );
    }
    assert_eq!(
        new_destination.preflight_same_edge_resume(
            &mut manager,
            &valid_handle,
            &mut fresh_session,
            105,
        ),
        Err(ResumeReject::AuditUnavailable)
    );
    fresh_session
        .pop_audit_event()
        .expect("make one preflight audit slot available");
    let valid_preflight = new_destination
        .preflight_same_edge_resume(&mut manager, &valid_handle, &mut fresh_session, 105)
        .expect("audit failure did not retain a preflight capability");
    while fresh_session.pop_audit_event().is_some() {}
    let (route_open, route_accept) = signed_route(fresh_spec);
    let fresh_channel = new_destination
        .accept_route_open_for_resume(
            &mut manager,
            &valid_preflight,
            &mut fresh_session,
            &route_open,
            105,
        )
        .expect("resume-specific fresh admission");
    fresh_session
        .confirm_route_accept(&route_accept)
        .expect("fresh correlated ROUTE_ACCEPT");
    new_destination
        .bind_channel(&mut fresh_session, fresh_channel.channel_id)
        .expect("fresh live exporter binding");
    let mut fresh = EstablishedSession {
        session: fresh_session,
        channel: fresh_channel,
        spec: fresh_spec,
    };
    while fresh.session.audit_events().len() < 1_024 {
        assert_eq!(
            new_destination.preflight_same_edge_resume(
                &mut manager,
                &mismatch_handle,
                &mut fresh.session,
                105,
            ),
            Err(ResumeReject::Mismatch)
        );
    }
    assert_eq!(
        new_destination.consume_same_edge_resume(
            &mut manager,
            &valid_preflight,
            &mut fresh.session,
            fresh.channel.channel_id,
            105,
            NOW + 5,
        ),
        Err(ResumeReject::AuditUnavailable)
    );
    assert_eq!(manager.retained_records(), 2);

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn only_normally_closed_previously_active_bound_channels_are_issue_eligible() {
    let (listener, source, destination) = connection_pair().await;
    let mut manager = SameEdgeResumeManager::new();

    let active = established_bound_session(
        &destination,
        SessionSpec::new(0x20, 0x50, 0x30, 0x90),
        "regional-prod.1",
    );
    assert_issue_ineligible(&mut manager, active, indexed_handle(10_001));

    let candidate_spec = SessionSpec::new(0x21, 0x51, 0x31, 0x91);
    let mut candidate =
        established_control_session(&destination, candidate_spec, "regional-prod.1");
    let (route_open, _) = signed_route(candidate_spec);
    let candidate_channel = candidate
        .accept_route_open(&route_open)
        .expect("candidate route");
    assert_eq!(
        manager.issue(
            &mut candidate,
            candidate_channel.channel_id,
            indexed_handle(10_002),
            100,
            NOW,
        ),
        Err(ResumeReject::Ineligible)
    );

    let mut unbound = established_session(
        &destination,
        SessionSpec::new(0x22, 0x52, 0x32, 0x92),
        "regional-prod.1",
        false,
    );
    let close = route_close(&unbound, 0x62);
    destination
        .accept_route_close(&mut unbound.session, unbound.channel.channel_id, &close)
        .expect("normal unbound close remains legal lifecycle control");
    assert_issue_ineligible(&mut manager, unbound, indexed_handle(10_003));

    let mut revoked = established_bound_session(
        &destination,
        SessionSpec::new(0x23, 0x53, 0x33, 0x93),
        "regional-prod.1",
    );
    let revoke = route_lifecycle(&revoked, 13, 0x63, None);
    destination
        .accept_route_revoke(&mut revoked.session, revoked.channel.channel_id, &revoke)
        .expect("revoke bound channel");
    assert_eq!(
        revoked.session.channel_state(revoked.channel.channel_id),
        Some(ChannelState::Revoked)
    );
    assert_issue_ineligible(&mut manager, revoked, indexed_handle(10_004));

    let mut drained = established_bound_session(
        &destination,
        SessionSpec::new(0x24, 0x54, 0x34, 0x94),
        "regional-prod.1",
    );
    let drain = route_lifecycle(&drained, 12, 0x64, Some(0));
    drained
        .session
        .accept_route_drain(drained.channel.channel_id, &drain, 100, NOW)
        .expect("start zero-second drain");
    assert_eq!(
        manager.issue(
            &mut drained.session,
            drained.channel.channel_id,
            indexed_handle(10_005),
            100,
            NOW,
        ),
        Err(ResumeReject::Ineligible)
    );
    assert_eq!(
        destination
            .enforce_channel_drain(&mut drained.session, drained.channel.channel_id, 100)
            .await
            .expect("force drain close"),
        DrainEnforcement::Enforced {
            audit_integrity: nbsr_transport::AuditIntegrity::Recorded,
        }
    );
    assert_issue_ineligible(&mut manager, drained, indexed_handle(10_006));

    let mut wrong_profile_old = established_bound_session(
        &destination,
        SessionSpec::new(0x25, 0x55, 0x35, 0x95),
        "regional-prod.2",
    );
    let close = route_close(&wrong_profile_old, 0x65);
    destination
        .accept_route_close(
            &mut wrong_profile_old.session,
            wrong_profile_old.channel.channel_id,
            &close,
        )
        .expect("wrong-profile normal close");
    let filler = indexed_handle(10_007);
    manager
        .issue(
            &mut wrong_profile_old.session,
            wrong_profile_old.channel.channel_id,
            filler.clone(),
            100,
            NOW,
        )
        .expect("audit filler record");
    let mut audit_failed = established_bound_session(
        &destination,
        SessionSpec::new(0x26, 0x56, 0x36, 0x96),
        "regional-prod.1",
    );
    while audit_failed.session.audit_events().len() < 1_024 {
        assert_eq!(
            destination.preflight_same_edge_resume(
                &mut manager,
                &filler,
                &mut audit_failed.session,
                105,
            ),
            Err(ResumeReject::Mismatch)
        );
    }
    let close = route_close(&audit_failed, 0x66);
    assert_eq!(
        destination.accept_route_close(
            &mut audit_failed.session,
            audit_failed.channel.channel_id,
            &close,
        ),
        Err(SessionReject::AuditUnavailable)
    );
    assert_eq!(
        audit_failed
            .session
            .channel_state(audit_failed.channel.channel_id),
        Some(ChannelState::Active)
    );
    assert_eq!(
        manager.issue(
            &mut audit_failed.session,
            audit_failed.channel.channel_id,
            indexed_handle(10_008),
            100,
            NOW,
        ),
        Err(ResumeReject::AuditUnavailable)
    );

    assert_eq!(manager.retained_records(), 1);
    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

fn assert_issue_ineligible(
    manager: &mut SameEdgeResumeManager,
    mut session: EstablishedSession,
    handle: ResumeHandle,
) {
    assert_eq!(
        manager.issue(
            &mut session.session,
            session.channel.channel_id,
            handle,
            100,
            NOW,
        ),
        Err(ResumeReject::Ineligible)
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn consume_does_not_copy_old_state_or_disturb_a_fresh_sibling() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (old_listener, old_source, old_destination) = connection_pair_with_pki(&pki).await;
    let mut old = established_bound_session(
        &old_destination,
        SessionSpec::new(0x10, 0x40, 0x20, 0x80),
        "regional-prod.1",
    );
    let close = route_close(&old, 0x51);
    old_destination
        .accept_route_close(&mut old.session, old.channel.channel_id, &close)
        .expect("normal bound close");
    let old_audit_count = old.session.audit_events().len();
    let handle = ResumeHandle::new([0xc1; 32]).expect("caller handle");
    let mut manager = SameEdgeResumeManager::new();
    manager
        .issue(
            &mut old.session,
            old.channel.channel_id,
            handle.clone(),
            100,
            NOW,
        )
        .expect("eligible record");
    let old_audit_after_issue = old.session.audit_events().len();
    assert_eq!(old_audit_after_issue, old_audit_count + 1);

    let (new_listener, new_source, new_destination) = connection_pair_with_pki(&pki).await;
    let fresh_spec = SessionSpec::new(0x60, 0x70, 0x30, 0x90);
    let (mut fresh, preflight) = established_resume_session(
        &new_destination,
        &mut manager,
        &handle,
        fresh_spec,
        "regional-prod.1",
        true,
        105,
    );
    let sibling_spec = SessionSpec {
        channel_id: [0x71; 16],
        route_id: [0x31; 16],
        grant_nonce: [0x91; 16],
        request_id: [0x72; 16],
        ..fresh_spec
    };
    let (sibling_open, sibling_accept) = signed_route_at(sibling_spec, 3);
    let sibling = fresh
        .session
        .accept_route_open(&sibling_open)
        .expect("independent sibling authorization");
    fresh
        .session
        .confirm_route_accept(&sibling_accept)
        .expect("independent sibling accept");
    new_destination
        .bind_channel(&mut fresh.session, sibling.channel_id)
        .expect("independent sibling exporter binding");
    let new_audit_before = fresh
        .session
        .audit_events()
        .last()
        .expect("new session audit")
        .sequence;

    let correlation = new_destination
        .consume_same_edge_resume(
            &mut manager,
            &preflight,
            &mut fresh.session,
            fresh.channel.channel_id,
            105,
            NOW + 5,
        )
        .expect("correlation only");
    assert_eq!(
        correlation,
        nbsr_transport::ResumeCorrelation {
            old_channel_id: old.channel.channel_id,
            new_channel_id: fresh.channel.channel_id,
        }
    );
    assert_eq!(fresh.session.active_channels(), 2);
    assert_eq!(
        fresh.session.channel_state(fresh.channel.channel_id),
        Some(ChannelState::Active)
    );
    assert_eq!(
        fresh.session.channel_state(sibling.channel_id),
        Some(ChannelState::Active)
    );
    assert_eq!(
        fresh
            .session
            .audit_events()
            .last()
            .expect("consume audit")
            .sequence,
        new_audit_before + 1
    );
    assert_eq!(old.session.audit_events().len(), old_audit_after_issue);
    assert_eq!(
        fresh.session.tombstone_expires_at(old.channel.channel_id),
        None
    );
    assert_eq!(
        fresh.session.session_drain_state(),
        nbsr_transport::SessionDrainState::Active
    );
    new_destination
        .bind_channel(&mut fresh.session, sibling.channel_id)
        .expect("sibling binding remains usable");

    old_source.close().await.expect("old source close");
    old_destination
        .close()
        .await
        .expect("old destination close");
    old_listener.close().await.expect("old listener close");
    new_source.close().await.expect("new source close");
    new_destination
        .close()
        .await
        .expect("new destination close");
    new_listener.close().await.expect("new listener close");
}

fn indexed_handle(index: u64) -> ResumeHandle {
    let mut bytes = [0_u8; 32];
    bytes[24..].copy_from_slice(&index.to_be_bytes());
    ResumeHandle::new(bytes).expect("nonzero unique handle")
}

struct EstablishedSession {
    session: ControlSession,
    channel: ActiveChannel,
    spec: SessionSpec,
}

impl EstablishedSession {
    fn context(&self) -> ServiceChannelContext<'static> {
        ServiceChannelContext {
            session_id: self.spec.session_id,
            source_edge_id: self.spec.source_edge_id,
            destination_edge_id: self.spec.destination_edge_id,
            channel_id: self.channel.channel_id,
            route_id: self.channel.route_id,
            route_grant_digest: self.channel.route_grant_digest,
            service_id: self.spec.service_id,
            transport: "tcp",
            port: 8443,
            policy_hash: self.spec.policy_hash,
            client_nonce: self.spec.client_nonce,
            edge_nonce: self.spec.edge_nonce,
        }
    }
}

#[derive(Clone, Copy)]
struct SessionSpec {
    session_id: [u8; 16],
    client_nonce: [u8; 32],
    edge_nonce: [u8; 32],
    channel_id: [u8; 16],
    route_id: [u8; 16],
    grant_nonce: [u8; 16],
    grant_expires_at: u64,
    policy_hash: [u8; 32],
    request_id: [u8; 16],
    service_id: &'static str,
    session_seed: [u8; 32],
    source_edge_id: &'static str,
    destination_edge_id: &'static str,
}

impl SessionSpec {
    fn new(session: u8, channel: u8, route: u8, nonce: u8) -> Self {
        Self {
            session_id: [session; 16],
            client_nonce: [session.wrapping_add(1); 32],
            edge_nonce: [session.wrapping_add(2); 32],
            channel_id: [channel; 16],
            route_id: [route; 16],
            grant_nonce: [nonce; 16],
            grant_expires_at: NOW + 300,
            policy_hash: POLICY_HASH,
            request_id: [channel.wrapping_add(1); 16],
            service_id: "service.example",
            session_seed: SESSION_SEED,
            source_edge_id: "source.edge",
            destination_edge_id: "destination.edge",
        }
    }
}

fn established_bound_session(
    connection: &nbsr_transport::AuthenticatedConnection,
    spec: SessionSpec,
    trust_profile: &str,
) -> EstablishedSession {
    established_session(connection, spec, trust_profile, true)
}

fn established_session_with_deadline(
    connection: &nbsr_transport::AuthenticatedConnection,
    spec: SessionSpec,
    trust_profile: &str,
    deadline: DrainDeadline,
) -> EstablishedSession {
    let mut session = ControlSession::new_with_monotonic_deadline(
        connection,
        DestinationAdmission::new(runtime_policy(spec)).expect("admission policy"),
        vec![route_grant_issuer()],
        TrustProfileId::new(trust_profile).expect("trust profile"),
        deadline,
    );
    let client_hello = client_hello(spec);
    let edge_hello = edge_hello(spec);
    session
        .accept_client_hello(&client_hello)
        .expect("fresh CLIENT_HELLO");
    session
        .confirm_edge_hello(&edge_hello)
        .expect("fresh EDGE_HELLO");
    let (route_open, route_accept) = signed_route(spec);
    let channel = session
        .accept_route_open(&route_open)
        .expect("fresh signed RouteGrant and proof");
    session
        .confirm_route_accept(&route_accept)
        .expect("correlated ROUTE_ACCEPT");
    connection
        .bind_channel(&mut session, channel.channel_id)
        .expect("fresh live exporter binding");
    EstablishedSession {
        session,
        channel,
        spec,
    }
}

fn established_session(
    connection: &nbsr_transport::AuthenticatedConnection,
    spec: SessionSpec,
    trust_profile: &str,
    bind: bool,
) -> EstablishedSession {
    let mut session = established_control_session(connection, spec, trust_profile);
    let (route_open, route_accept) = signed_route(spec);
    let channel = session
        .accept_route_open(&route_open)
        .expect("fresh signed RouteGrant and proof");
    session
        .confirm_route_accept(&route_accept)
        .expect("correlated ROUTE_ACCEPT");
    if bind {
        connection
            .bind_channel(&mut session, channel.channel_id)
            .expect("fresh live exporter binding");
    }
    EstablishedSession {
        session,
        channel,
        spec,
    }
}

fn established_resume_session(
    connection: &nbsr_transport::AuthenticatedConnection,
    manager: &mut SameEdgeResumeManager,
    handle: &ResumeHandle,
    spec: SessionSpec,
    trust_profile: &str,
    bind: bool,
    monotonic_now: u64,
) -> (EstablishedSession, ResumePreflight) {
    let mut session = established_control_session(connection, spec, trust_profile);
    let preflight = connection
        .preflight_same_edge_resume(manager, handle, &mut session, monotonic_now)
        .expect("same-edge resume preflight");
    let (route_open, route_accept) = signed_route(spec);
    let channel = connection
        .accept_route_open_for_resume(
            manager,
            &preflight,
            &mut session,
            &route_open,
            monotonic_now,
        )
        .expect("preflight-gated fresh route admission");
    session
        .confirm_route_accept(&route_accept)
        .expect("correlated ROUTE_ACCEPT");
    if bind {
        connection
            .bind_channel(&mut session, channel.channel_id)
            .expect("fresh live exporter binding");
    }
    (
        EstablishedSession {
            session,
            channel,
            spec,
        },
        preflight,
    )
}

fn established_control_session(
    connection: &nbsr_transport::AuthenticatedConnection,
    spec: SessionSpec,
    trust_profile: &str,
) -> ControlSession {
    let mut session = ControlSession::new(
        connection,
        DestinationAdmission::new(runtime_policy(spec)).expect("admission policy"),
        vec![route_grant_issuer()],
        TrustProfileId::new(trust_profile).expect("trust profile"),
    );
    let client_hello = client_hello(spec);
    let edge_hello = edge_hello(spec);
    session
        .accept_client_hello(&client_hello)
        .expect("fresh CLIENT_HELLO");
    session
        .confirm_edge_hello(&edge_hello)
        .expect("fresh EDGE_HELLO");
    session
}

fn runtime_policy(spec: SessionSpec) -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: spec.source_edge_id.into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: spec.destination_edge_id.into(),
        authorized_services: BTreeMap::from([(
            spec.service_id.into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: spec.policy_hash,
            },
        )]),
        now: NOW,
        client_session_public_key: SigningKey::from_bytes(&spec.session_seed)
            .verifying_key()
            .to_bytes(),
        edge_nonce: spec.edge_nonce,
    }
}

fn route_grant_issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: KID.to_vec(),
        public_key: SigningKey::from_bytes(&ROUTE_GRANT_SEED)
            .verifying_key()
            .to_bytes(),
    }
}

fn client_hello(spec: SessionSpec) -> CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 8);
    field_uint(&mut body, 0, 1);
    field_text(&mut body, 1, "source.operator");
    field_text(&mut body, 2, spec.source_edge_id);
    field_text(&mut body, 3, "destination.operator");
    field_text(&mut body, 4, spec.destination_edge_id);
    field_bytes(&mut body, 5, &spec.client_nonce);
    field_bytes(
        &mut body,
        6,
        &SigningKey::from_bytes(&spec.session_seed)
            .verifying_key()
            .to_bytes(),
    );
    field_uint(&mut body, 7, NOW);
    envelope(1, [0x01; 16], spec.session_id, 1, body)
}

fn edge_hello(spec: SessionSpec) -> CoreV02Envelope {
    let public_key = SigningKey::from_bytes(&spec.session_seed)
        .verifying_key()
        .to_bytes();
    let thumbprint: [u8; 32] = Sha256::digest(public_key).into();
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_text(&mut body, 1, spec.source_edge_id);
    field_text(&mut body, 2, spec.destination_edge_id);
    field_bytes(&mut body, 3, &spec.client_nonce);
    field_bytes(&mut body, 4, &spec.edge_nonce);
    field_bytes(&mut body, 5, &thumbprint);
    field_uint(&mut body, 6, NOW);
    envelope(2, [0x01; 16], spec.session_id, 1, body)
}

fn signed_route(spec: SessionSpec) -> (CoreV02Envelope, CoreV02Envelope) {
    signed_route_at(spec, 2)
}

fn signed_route_at(spec: SessionSpec, sequence: u64) -> (CoreV02Envelope, CoreV02Envelope) {
    let grant = signed_grant(spec);
    let grant_digest: [u8; 32] = Sha256::digest(&grant).into();
    let proof =
        SigningKey::from_bytes(&spec.session_seed).sign(&route_open_transcript(spec, grant_digest));
    let mut open = Vec::new();
    map(&mut open, 8);
    field_uint(&mut open, 0, 1);
    field_bytes(&mut open, 1, &spec.channel_id);
    field_bytes(&mut open, 2, &grant);
    field_bytes(&mut open, 3, &spec.edge_nonce);
    field_text(&mut open, 4, "tcp");
    field_uint(&mut open, 5, 8443);
    field_uint(&mut open, 6, NOW);
    field_bytes(&mut open, 7, &proof.to_bytes());

    let mut accept = Vec::new();
    map(&mut accept, 5);
    field_uint(&mut accept, 0, 1);
    field_bytes(&mut accept, 1, &spec.channel_id);
    field_bytes(&mut accept, 2, &spec.route_id);
    field_bytes(&mut accept, 3, &grant_digest);
    field_uint(&mut accept, 4, NOW);
    (
        envelope(3, spec.request_id, spec.session_id, sequence, open),
        envelope(4, spec.request_id, spec.session_id, sequence, accept),
    )
}

fn signed_grant(spec: SessionSpec) -> Vec<u8> {
    let public_key = SigningKey::from_bytes(&spec.session_seed)
        .verifying_key()
        .to_bytes();
    let thumbprint: [u8; 32] = Sha256::digest(public_key).into();
    let mut payload = Vec::new();
    map(&mut payload, 17);
    field_uint(&mut payload, 0, 1);
    field_bytes(&mut payload, 1, &spec.route_id);
    field_bytes(&mut payload, 2, &[0x11; 32]);
    field_text(&mut payload, 3, spec.service_id);
    field_text(&mut payload, 4, "source.operator");
    field_text(&mut payload, 5, spec.source_edge_id);
    field_text(&mut payload, 6, "destination.operator");
    uint(&mut payload, 7);
    array(&mut payload, 1);
    text(&mut payload, spec.destination_edge_id);
    uint(&mut payload, 8);
    array(&mut payload, 1);
    text(&mut payload, "tcp");
    uint(&mut payload, 9);
    array(&mut payload, 1);
    uint(&mut payload, 8443);
    field_bytes(&mut payload, 10, &thumbprint);
    field_uint(&mut payload, 11, NOW - 60);
    field_uint(&mut payload, 12, spec.grant_expires_at);
    field_bytes(&mut payload, 13, &[0x33; 16]);
    field_uint(&mut payload, 14, 42);
    field_bytes(&mut payload, 15, &spec.policy_hash);
    field_bytes(&mut payload, 16, &spec.grant_nonce);

    let mut protected = Vec::new();
    map(&mut protected, 2);
    uint(&mut protected, 1);
    nint(&mut protected, -8);
    field_bytes(&mut protected, 4, KID);
    let mut signature_structure = Vec::new();
    array(&mut signature_structure, 4);
    text(&mut signature_structure, "Signature1");
    bytes(&mut signature_structure, &protected);
    bytes(&mut signature_structure, &[]);
    bytes(&mut signature_structure, &payload);
    let signature = SigningKey::from_bytes(&ROUTE_GRANT_SEED).sign(&signature_structure);
    let mut wire = vec![0xd2];
    array(&mut wire, 4);
    bytes(&mut wire, &protected);
    map(&mut wire, 0);
    bytes(&mut wire, &payload);
    bytes(&mut wire, &signature.to_bytes());
    wire
}

fn route_open_transcript(spec: SessionSpec, grant_digest: [u8; 32]) -> Vec<u8> {
    let mut wire = Vec::new();
    array(&mut wire, 13);
    text(&mut wire, "NBSR-ROUTE-OPEN-v2");
    uint(&mut wire, 2);
    bytes(&mut wire, &spec.session_id);
    bytes(&mut wire, &spec.request_id);
    bytes(&mut wire, &spec.channel_id);
    bytes(&mut wire, &spec.route_id);
    text(&mut wire, spec.service_id);
    text(&mut wire, spec.destination_edge_id);
    bytes(&mut wire, &spec.edge_nonce);
    text(&mut wire, "tcp");
    uint(&mut wire, 8443);
    bytes(&mut wire, &grant_digest);
    uint(&mut wire, NOW);
    wire
}

fn route_close(session: &EstablishedSession, request: u8) -> CoreV02Envelope {
    route_lifecycle(session, 14, request, None)
}

fn route_lifecycle(
    session: &EstablishedSession,
    message_type: u64,
    request: u8,
    drain_seconds: Option<u64>,
) -> CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, if drain_seconds.is_some() { 6 } else { 5 });
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &session.channel.channel_id);
    field_bytes(&mut body, 2, &session.channel.route_id);
    field_bytes(&mut body, 3, &session.channel.route_grant_digest);
    field_uint(&mut body, 4, NOW);
    if let Some(seconds) = drain_seconds {
        field_uint(&mut body, 5, seconds);
    }
    envelope(
        message_type,
        [request; 16],
        session.spec.session_id,
        3,
        body,
    )
}

fn envelope(
    message_type: u64,
    request_id: [u8; 16],
    session_id: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> CoreV02Envelope {
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message_type);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &session_id);
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid generated envelope")
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

async fn connection_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    connection_pair_with_pki(&pki).await
}

async fn connection_pair_with_pki(
    pki: &support::TestPki,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    connection_pair_with_pki_for(pki, "source.edge", "destination.edge").await
}

async fn connection_pair_with_pki_for(
    pki: &support::TestPki,
    source_edge_id: &str,
    destination_edge_id: &str,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity(source_edge_id),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity(destination_edge_id),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy");
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("listener");
    let remote = listener.local_addr().expect("listener address");
    let (destination, source) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy, pki.source_material()).expect("client config"),
            remote,
        )
    );
    (
        listener,
        source.expect("source connection"),
        destination.expect("destination connection"),
    )
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
    text(target, value);
}

fn uint(target: &mut Vec<u8>, value: u64) {
    argument(target, 0, value);
}

fn nint(target: &mut Vec<u8>, value: i64) {
    argument(target, 1, (-1 - value) as u64);
}

fn bytes(target: &mut Vec<u8>, value: &[u8]) {
    argument(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn text(target: &mut Vec<u8>, value: &str) {
    argument(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}

fn array(target: &mut Vec<u8>, length: u64) {
    argument(target, 4, length);
}

fn map(target: &mut Vec<u8>, length: u64) {
    argument(target, 5, length);
}

fn argument(target: &mut Vec<u8>, major: u8, value: u64) {
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
