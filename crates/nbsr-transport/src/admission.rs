//! Destination-edge admission for one independently authorized service channel.
//!
//! Validation completes before a channel is reserved.  This deliberately keeps
//! RouteGrant semantics separate from the authenticated transport session.

use std::collections::HashSet;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmissionPolicy {
    pub source_operator_id: String,
    pub source_edge_id: String,
    pub destination_operator_id: String,
    pub destination_edge_id: String,
    pub accepted_record_sequence: u64,
    pub policy_hash: [u8; 32],
    pub now: u64,
    pub max_channels: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RouteGrantClaims {
    pub route_id: [u8; 16],
    pub service_id: String,
    pub source_operator_id: String,
    pub source_edge_id: String,
    pub destination_operator_id: String,
    pub destination_edge_ids: Vec<String>,
    pub allowed_ports: Vec<u16>,
    pub client_session_key_thumbprint: [u8; 32],
    pub not_before: u64,
    pub expires_at: u64,
    pub record_sequence: u64,
    pub policy_hash: [u8; 32],
    pub unique_nonce: [u8; 16],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RouteOpenRequest {
    pub channel_id: [u8; 16],
    pub grant: RouteGrantClaims,
    pub requested_transport: String,
    pub requested_port: u16,
    pub opened_at: u64,
    pub route_grant_digest: [u8; 32],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ActiveChannel {
    pub channel_id: [u8; 16],
    pub route_id: [u8; 16],
    pub service_id: String,
    pub route_grant_digest: [u8; 32],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AdmissionReject {
    GrantInvalid,
    GrantExpired,
    Replay,
    RouteDenied,
    OverCapacity,
}

pub struct DestinationAdmission {
    policy: AdmissionPolicy,
    used_channel_ids: HashSet<[u8; 16]>,
    used_grant_nonces: HashSet<[u8; 16]>,
    active: Vec<ActiveChannel>,
}

impl DestinationAdmission {
    pub fn new(policy: AdmissionPolicy) -> Self {
        Self {
            policy,
            used_channel_ids: HashSet::new(),
            used_grant_nonces: HashSet::new(),
            active: Vec::new(),
        }
    }

    pub fn active_channels(&self) -> usize {
        self.active.len()
    }

    pub fn admit(&mut self, request: RouteOpenRequest) -> Result<ActiveChannel, AdmissionReject> {
        validate_request(&self.policy, &request)?;
        if self.used_channel_ids.contains(&request.channel_id)
            || self.used_grant_nonces.contains(&request.grant.unique_nonce)
        {
            return Err(AdmissionReject::Replay);
        }
        if self.active.len() >= self.policy.max_channels {
            return Err(AdmissionReject::OverCapacity);
        }

        let channel = ActiveChannel {
            channel_id: request.channel_id,
            route_id: request.grant.route_id,
            service_id: request.grant.service_id.clone(),
            route_grant_digest: request.route_grant_digest,
        };
        self.used_channel_ids.insert(request.channel_id);
        self.used_grant_nonces.insert(request.grant.unique_nonce);
        self.active.push(channel.clone());
        Ok(channel)
    }
}

fn validate_request(
    policy: &AdmissionPolicy,
    request: &RouteOpenRequest,
) -> Result<(), AdmissionReject> {
    let grant = &request.grant;
    if request.channel_id == [0; 16]
        || grant.route_id == [0; 16]
        || grant.unique_nonce == [0; 16]
        || request.requested_transport != "tcp"
        || request.requested_port == 0
    {
        return Err(AdmissionReject::GrantInvalid);
    }
    if grant.not_before > grant.expires_at
        || grant.expires_at.saturating_sub(grant.not_before) > 600
        || policy.now < grant.not_before
        || policy.now > grant.expires_at
        || request.opened_at < grant.not_before
        || request.opened_at > grant.expires_at
    {
        return Err(AdmissionReject::GrantExpired);
    }
    if grant.source_operator_id != policy.source_operator_id
        || grant.source_edge_id != policy.source_edge_id
        || grant.destination_operator_id != policy.destination_operator_id
        || !grant
            .destination_edge_ids
            .iter()
            .any(|edge| edge == &policy.destination_edge_id)
        || grant.record_sequence != policy.accepted_record_sequence
        || grant.policy_hash != policy.policy_hash
    {
        return Err(AdmissionReject::GrantInvalid);
    }
    if !grant.allowed_ports.contains(&request.requested_port) {
        return Err(AdmissionReject::RouteDenied);
    }
    Ok(())
}
