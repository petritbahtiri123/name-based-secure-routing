use nbsr_transport::{
    AdmissionPolicy, AdmissionReject, DestinationAdmission, RouteGrantClaims, RouteOpenRequest,
};

const CHANNEL_ID: [u8; 16] = [0x40; 16];
const ROUTE_ID: [u8; 16] = [0x20; 16];
const THUMBPRINT: [u8; 32] = [0x30; 32];
const POLICY_HASH: [u8; 32] = [0x50; 32];

fn policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        accepted_record_sequence: 42,
        policy_hash: POLICY_HASH,
        now: 1_893_456_000,
        max_channels: 1,
    }
}

fn grant() -> RouteGrantClaims {
    RouteGrantClaims {
        route_id: ROUTE_ID,
        service_id: "service.example".into(),
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_ids: vec!["destination.edge".into()],
        allowed_ports: vec![8443],
        client_session_key_thumbprint: THUMBPRINT,
        not_before: 1_893_455_940,
        expires_at: 1_893_456_300,
        record_sequence: 42,
        policy_hash: POLICY_HASH,
        unique_nonce: [0x50; 16],
    }
}

fn request() -> RouteOpenRequest {
    RouteOpenRequest {
        channel_id: CHANNEL_ID,
        grant: grant(),
        requested_transport: "tcp".into(),
        requested_port: 8443,
        opened_at: 1_893_456_000,
        route_grant_digest: [0x60; 32],
    }
}

#[test]
fn valid_request_allocates_exactly_one_service_bound_channel() {
    let mut admission = DestinationAdmission::new(policy());
    let accepted = admission.admit(request()).expect("valid route admission");

    assert_eq!(accepted.channel_id, CHANNEL_ID);
    assert_eq!(accepted.route_id, ROUTE_ID);
    assert_eq!(accepted.service_id, "service.example");
    assert_eq!(admission.active_channels(), 1);
}

#[test]
fn invalid_or_replayed_requests_leave_no_channel_state() {
    let mut admission = DestinationAdmission::new(policy());
    let mut denied = request();
    denied.requested_port = 443;
    assert_eq!(admission.admit(denied), Err(AdmissionReject::RouteDenied));
    assert_eq!(admission.active_channels(), 0);

    admission.admit(request()).expect("first use accepted");
    assert_eq!(admission.admit(request()), Err(AdmissionReject::Replay));
    assert_eq!(admission.active_channels(), 1);
}

#[test]
fn grant_binding_expiry_and_capacity_are_independent_fail_closed_checks() {
    let mut admission = DestinationAdmission::new(policy());
    let mut wrong_edge = request();
    wrong_edge.grant.destination_edge_ids = vec!["other.edge".into()];
    assert_eq!(
        admission.admit(wrong_edge),
        Err(AdmissionReject::GrantInvalid)
    );

    let mut expired = request();
    expired.grant.expires_at = 1_893_455_999;
    assert_eq!(admission.admit(expired), Err(AdmissionReject::GrantExpired));

    admission.admit(request()).expect("capacity first channel");
    let mut second = request();
    second.channel_id = [0x41; 16];
    second.grant.unique_nonce = [0x51; 16];
    assert_eq!(admission.admit(second), Err(AdmissionReject::OverCapacity));
}
