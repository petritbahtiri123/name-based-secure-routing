//! Destination-edge admission for one independently authorized service channel.
//!
//! Validation completes before a channel is reserved.  This deliberately keeps
//! RouteGrant semantics separate from the authenticated transport session.

use std::collections::HashSet;

use ed25519_dalek::{Signature, VerifyingKey};
use sha2::{Digest, Sha256};

use crate::{CoreV02Envelope, CoreV02Reject, RouteGrantIssuer};

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
    pub client_session_public_key: [u8; 32],
    pub edge_nonce: [u8; 32],
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

    pub fn admit_route_open(
        &mut self,
        envelope: &CoreV02Envelope,
        trusted_issuers: &[RouteGrantIssuer],
    ) -> Result<ActiveChannel, AdmissionReject> {
        let route_open = envelope
            .validated_route_open(trusted_issuers)
            .map_err(map_core_reject)?;
        if route_open.edge_nonce != self.policy.edge_nonce
            || Sha256::digest(self.policy.client_session_public_key).as_slice()
                != route_open.grant.client_session_key_thumbprint
        {
            return Err(AdmissionReject::GrantInvalid);
        }
        let route_grant_digest: [u8; 32] = Sha256::digest(&route_open.grant_wire).into();
        let transcript = route_open_transcript(
            route_open.session_id,
            route_open.request_id,
            route_open.channel_id,
            route_open.grant.route_id,
            &route_open.grant.service_id,
            &self.policy.destination_edge_id,
            route_open.edge_nonce,
            &route_open.requested_transport,
            route_open.requested_port,
            route_grant_digest,
            route_open.opened_at,
        )?;
        let key = VerifyingKey::from_bytes(&self.policy.client_session_public_key)
            .map_err(|_| AdmissionReject::GrantInvalid)?;
        key.verify_strict(
            &transcript,
            &Signature::from_bytes(&route_open.proof_signature),
        )
        .map_err(|_| AdmissionReject::GrantInvalid)?;
        self.admit(RouteOpenRequest {
            channel_id: route_open.channel_id,
            grant: route_open.grant,
            requested_transport: route_open.requested_transport,
            requested_port: route_open.requested_port,
            opened_at: route_open.opened_at,
            route_grant_digest,
        })
    }
}

fn map_core_reject(error: CoreV02Reject) -> AdmissionReject {
    match error {
        CoreV02Reject::OverCapacity => AdmissionReject::OverCapacity,
        CoreV02Reject::ProfileUnsupported
        | CoreV02Reject::Downgrade
        | CoreV02Reject::GrantInvalid => AdmissionReject::GrantInvalid,
    }
}

#[allow(clippy::too_many_arguments)]
fn route_open_transcript(
    session_id: [u8; 16],
    request_id: [u8; 16],
    channel_id: [u8; 16],
    route_id: [u8; 16],
    service_id: &str,
    destination_edge_id: &str,
    edge_nonce: [u8; 32],
    transport: &str,
    port: u16,
    route_grant_digest: [u8; 32],
    opened_at: u64,
) -> Result<Vec<u8>, AdmissionReject> {
    let mut wire = Vec::with_capacity(256);
    wire.push(0x8d);
    encode_text(&mut wire, "NBSR-ROUTE-OPEN-v2")?;
    encode_uint(&mut wire, 2)?;
    for value in [&session_id[..], &request_id, &channel_id, &route_id] {
        encode_bytes(&mut wire, value)?;
    }
    encode_text(&mut wire, service_id)?;
    encode_text(&mut wire, destination_edge_id)?;
    encode_bytes(&mut wire, &edge_nonce)?;
    encode_text(&mut wire, transport)?;
    encode_uint(&mut wire, u64::from(port))?;
    encode_bytes(&mut wire, &route_grant_digest)?;
    encode_uint(&mut wire, opened_at)?;
    Ok(wire)
}

fn encode_text(target: &mut Vec<u8>, value: &str) -> Result<(), AdmissionReject> {
    encode_argument(target, 3, value.len() as u64)?;
    target.extend_from_slice(value.as_bytes());
    Ok(())
}

fn encode_bytes(target: &mut Vec<u8>, value: &[u8]) -> Result<(), AdmissionReject> {
    encode_argument(target, 2, value.len() as u64)?;
    target.extend_from_slice(value);
    Ok(())
}

fn encode_uint(target: &mut Vec<u8>, value: u64) -> Result<(), AdmissionReject> {
    encode_argument(target, 0, value)
}

fn encode_argument(target: &mut Vec<u8>, major: u8, value: u64) -> Result<(), AdmissionReject> {
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
    Ok(())
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
