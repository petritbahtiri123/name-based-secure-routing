use nbsr_transport::{
    AdmissionPolicy, AdmissionReject, AuditAction, AuditOutcome, AuditReason,
    AuthorizedServicePolicy, ChannelLimits, ChannelState, DestinationAdmission, RouteGrantClaims,
    RouteOpenRequest,
};

const NOW: u64 = 1_893_456_000;
const POLICY_HASH: [u8; 32] = [0x50; 32];

fn policy(service_count: usize) -> AdmissionPolicy {
    let authorized_services = (0..service_count)
        .map(|index| {
            (
                format!("service-{index}"),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: POLICY_HASH,
                },
            )
        })
        .collect();
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services,
        now: NOW,
        client_session_public_key: [0x30; 32],
        edge_nonce: [0x80; 32],
    }
}

fn id(value: u64) -> [u8; 16] {
    let mut id = [0_u8; 16];
    id[8..].copy_from_slice(&value.to_be_bytes());
    id
}

fn request(value: u64) -> RouteOpenRequest {
    RouteOpenRequest {
        channel_id: id(value),
        grant: RouteGrantClaims {
            route_id: id(value + 10_000),
            service_id: "service-0".into(),
            source_operator_id: "source.operator".into(),
            source_edge_id: "source.edge".into(),
            destination_operator_id: "destination.operator".into(),
            destination_edge_ids: vec!["destination.edge".into()],
            allowed_transports: vec!["tcp".into()],
            allowed_ports: vec![8443],
            client_session_key_thumbprint: [0x30; 32],
            not_before: NOW - 60,
            expires_at: NOW + 300,
            record_sequence: 42,
            policy_hash: POLICY_HASH,
            unique_nonce: id(value + 20_000),
        },
        requested_transport: "tcp".into(),
        requested_port: 8443,
        opened_at: NOW,
        route_grant_digest: [0x60; 32],
    }
}

#[test]
fn authorized_service_policy_accepts_32_entries_and_rejects_33_before_state_exists() {
    assert!(DestinationAdmission::new(policy(32)).is_ok());
    assert!(matches!(
        DestinationAdmission::new(policy(33)),
        Err(AdmissionReject::OverCapacity)
    ));
}

#[test]
fn replay_history_accepts_4096_entries_then_rejects_new_keys_without_audit_mutation() {
    let mut admission = DestinationAdmission::with_limits(
        policy(1),
        ChannelLimits {
            max_channels_per_session: 5_000,
            max_channels_per_service: 5_000,
        },
    )
    .expect("bounded service policy");

    for value in 1..=4_096 {
        admission
            .admit(request(value))
            .expect("first 4096 replay entries");
        assert!(admission.pop_audit_event().is_some());
    }
    assert_eq!(admission.audit_events().len(), 0);

    assert_eq!(
        admission.admit(request(4_097)),
        Err(AdmissionReject::OverCapacity)
    );
    assert_eq!(admission.audit_events().len(), 0);

    assert_eq!(admission.admit(request(1)), Err(AdmissionReject::Replay));
    assert_eq!(admission.audit_events().len(), 0);
}

#[test]
fn audit_queue_retains_sequences_1_through_1024_and_rejects_the_next_mutation() {
    let mut admission = DestinationAdmission::with_limits(
        policy(1),
        ChannelLimits {
            max_channels_per_session: 1,
            max_channels_per_service: 1,
        },
    )
    .expect("bounded service policy");
    admission.admit(request(1)).expect("one candidate");
    assert_eq!(
        admission.channel_state(id(1)),
        Some(ChannelState::Candidate)
    );

    for value in 2..=1_024 {
        assert_eq!(
            admission.admit(request(value)),
            Err(AdmissionReject::OverCapacity)
        );
    }
    let events = admission.audit_events().collect::<Vec<_>>();
    assert_eq!(events.len(), 1_024);
    for (index, event) in events.iter().enumerate() {
        assert_eq!(event.sequence, index as u64 + 1);
        assert!(event.unix_timestamp > 0);
    }
    assert_eq!(events[0].action, AuditAction::RouteCandidateReserved);
    assert_eq!(events[0].outcome, AuditOutcome::Allowed);
    assert_eq!(events[0].reason, AuditReason::None);
    assert_eq!(events[1].action, AuditAction::QuotaDenied);
    assert_eq!(events[1].outcome, AuditOutcome::Denied);
    assert_eq!(events[1].reason, AuditReason::Capacity);

    let before = format!("{:?}", events[0]);
    assert!(!before.contains("route_grant_digest"));
    assert!(!before.contains("unique_nonce"));
    assert!(!before.contains("proof_signature"));
    assert!(!before.contains("hostname"));
    assert!(!before.contains("certificate"));

    assert_eq!(
        admission.admit(request(1_025)),
        Err(AdmissionReject::AuditUnavailable)
    );
    assert_eq!(admission.audit_events().len(), 1_024);
    assert_eq!(
        admission.channel_state(id(1)),
        Some(ChannelState::Candidate)
    );
    assert_eq!(admission.channel_state(id(1_025)), None);
}
