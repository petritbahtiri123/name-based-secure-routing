//! Destination-edge admission for bounded independently authorized service channels.
//!
//! Validation completes before a channel is reserved.  This deliberately keeps
//! RouteGrant semantics separate from the authenticated transport session.

use std::collections::BTreeMap;

use ed25519_dalek::{Signature, VerifyingKey};
use sha2::{Digest, Sha256};

use crate::audit::{AuditAction, AuditEvent, AuditLog, AuditOutcome, AuditReason, SafeServiceId};
use crate::channel_lifecycle::ChannelState;
use crate::channel_registry::{
    ChannelBindingInstallError, ChannelLifecycleError, ChannelRegistry, PendingAdmissionError,
    ResumeChannelContext,
};
use crate::{ChannelBinding, ChannelLimits, CoreV02Envelope, CoreV02Reject, RouteGrantIssuer};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthorizedServicePolicy {
    pub accepted_record_sequence: u64,
    pub policy_hash: [u8; 32],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmissionPolicy {
    pub source_operator_id: String,
    pub source_edge_id: String,
    pub destination_operator_id: String,
    pub destination_edge_id: String,
    pub authorized_services: BTreeMap<String, AuthorizedServicePolicy>,
    pub now: u64,
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
    pub transport: String,
    pub port: u16,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AdmissionReject {
    AuditUnavailable,
    GrantInvalid,
    GrantExpired,
    Replay,
    RouteDenied,
    OverCapacity,
}

pub struct DestinationAdmission {
    audit: AuditLog,
    policy: AdmissionPolicy,
    channels: ChannelRegistry,
}

impl DestinationAdmission {
    pub fn new(policy: AdmissionPolicy) -> Result<Self, AdmissionReject> {
        Self::with_limits(policy, ChannelLimits::default())
    }

    pub fn with_limits(
        policy: AdmissionPolicy,
        limits: ChannelLimits,
    ) -> Result<Self, AdmissionReject> {
        if policy.authorized_services.len() > 32
            || policy
                .authorized_services
                .keys()
                .any(|service_id| !SafeServiceId::is_valid(service_id))
        {
            return Err(AdmissionReject::OverCapacity);
        }
        Ok(Self {
            audit: AuditLog::new(),
            policy,
            channels: ChannelRegistry::new(limits),
        })
    }

    pub fn active_channels(&self) -> usize {
        self.channels.active_len()
    }

    pub fn candidate_channels(&self) -> usize {
        self.channels.candidate_len()
    }

    pub fn channel_state(&self, channel_id: [u8; 16]) -> Option<ChannelState> {
        self.channels.channel_state(&channel_id)
    }

    pub fn audit_events(&self) -> impl ExactSizeIterator<Item = &AuditEvent> {
        self.audit.events().iter()
    }

    pub fn pop_audit_event(&mut self) -> Option<AuditEvent> {
        self.audit.pop()
    }

    pub(crate) fn set_session_id(&mut self, session_id: [u8; 16]) {
        self.audit.set_session_id(session_id);
    }

    pub(crate) fn confirm_channel(&mut self, channel_id: &[u8; 16]) -> Result<(), AdmissionReject> {
        let channel = self
            .channels
            .candidate(channel_id)
            .ok_or(AdmissionReject::RouteDenied)?;
        self.audit
            .record(
                Some(channel.channel_id),
                &channel.service_id,
                AuditAction::RouteActivated,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| AdmissionReject::AuditUnavailable)?;
        self.channels.confirm_active(channel_id)
    }

    pub(crate) fn channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.channels.channel(channel_id)
    }

    pub(crate) fn bound_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.channels.bound_channel(channel_id)
    }

    pub(crate) fn bound_existing_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.channels.bound_existing_channel(channel_id)
    }

    pub(crate) fn lifecycle_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.channels.lifecycle_channel(channel_id)
    }

    pub(crate) fn start_channel_drain(
        &mut self,
        channel_id: &[u8; 16],
        requested: crate::DrainDeadline,
        monotonic_now: u64,
        unix_now: u64,
        session_deadline: Option<crate::DrainDeadline>,
    ) -> Result<crate::DrainDeadline, ChannelLifecycleError> {
        let deadline = self.channels.prepare_drain(
            channel_id,
            requested,
            monotonic_now,
            unix_now,
            session_deadline,
        )?;
        let service_id = self
            .channels
            .lifecycle_channel(channel_id)
            .ok_or(ChannelLifecycleError::InvalidState)?
            .service_id
            .clone();
        self.audit
            .record(
                Some(*channel_id),
                &service_id,
                AuditAction::ChannelDrainStarted,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelLifecycleError::AuditUnavailable)?;
        self.channels.commit_drain(channel_id, deadline)?;
        Ok(deadline)
    }

    pub(crate) fn channel_drain_deadline(
        &self,
        channel_id: &[u8; 16],
    ) -> Option<crate::DrainDeadline> {
        self.channels.drain_deadline(channel_id)
    }

    pub(crate) fn finish_channel_drain(
        &mut self,
        channel_id: &[u8; 16],
    ) -> Result<(), ChannelLifecycleError> {
        let service_id = self
            .channels
            .lifecycle_channel(channel_id)
            .ok_or(ChannelLifecycleError::InvalidState)?
            .service_id
            .clone();
        self.audit
            .record(
                Some(*channel_id),
                &service_id,
                AuditAction::ChannelDrainForced,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelLifecycleError::AuditUnavailable)?;
        self.channels.finish_drain(channel_id)
    }

    pub(crate) fn start_session_drain(
        &mut self,
        monotonic_now: u64,
        unix_now: u64,
        session_deadline: crate::DrainDeadline,
    ) -> Result<(), ChannelLifecycleError> {
        let channel_deadlines =
            self.channels
                .prepare_session_drain(monotonic_now, unix_now, session_deadline)?;
        self.audit
            .record(
                None,
                "transport-session",
                AuditAction::SessionDrainStarted,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelLifecycleError::AuditUnavailable)?;
        self.channels.commit_session_drain(&channel_deadlines);
        Ok(())
    }

    pub(crate) fn due_draining_channels(&self, monotonic_now: u64) -> Vec<[u8; 16]> {
        self.channels.due_draining_channels(monotonic_now)
    }

    pub(crate) fn audit_session_drain_forced(&mut self) -> Result<(), ChannelLifecycleError> {
        self.audit
            .record(
                None,
                "transport-session",
                AuditAction::SessionDrainForced,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelLifecycleError::AuditUnavailable)
    }

    pub(crate) fn close_live_channel(
        &mut self,
        channel_id: &[u8; 16],
        closed_at: u64,
    ) -> Result<(), ChannelLifecycleError> {
        let service_id = self
            .channels
            .lifecycle_channel(channel_id)
            .ok_or(ChannelLifecycleError::InvalidState)?
            .service_id
            .clone();
        self.audit
            .record(
                Some(*channel_id),
                &service_id,
                AuditAction::ChannelClosed,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelLifecycleError::AuditUnavailable)?;
        self.channels.close_live(channel_id, closed_at)
    }

    pub(crate) fn install_binding(
        &mut self,
        channel_id: &[u8; 16],
        binding: ChannelBinding,
    ) -> Result<(), ChannelBindingInstallError> {
        let needs_install = self.channels.binding_needs_install(channel_id, &binding)?;
        if !needs_install {
            return Ok(());
        }
        let service_id = self
            .channels
            .channel(channel_id)
            .ok_or(ChannelBindingInstallError::InvalidState)?
            .service_id
            .clone();
        self.audit
            .record(
                Some(*channel_id),
                &service_id,
                AuditAction::BindingInstalled,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelBindingInstallError::AuditUnavailable)?;
        self.channels.install_binding(channel_id, binding)
    }

    pub(crate) fn revoke_channel(
        &mut self,
        channel_id: &[u8; 16],
        revoked_at: u64,
    ) -> Result<(), ChannelLifecycleError> {
        let service_id = self
            .channels
            .revocable_channel(channel_id)?
            .service_id
            .clone();
        self.audit
            .record(
                Some(*channel_id),
                &service_id,
                AuditAction::ChannelRevoked,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ChannelLifecycleError::AuditUnavailable)?;
        self.channels.revoke(channel_id, revoked_at)
    }

    pub(crate) fn audit_stream_authorized(
        &mut self,
        channel_id: &[u8; 16],
    ) -> Result<(), AdmissionReject> {
        let channel = self
            .channels
            .bound_channel(channel_id)
            .ok_or(AdmissionReject::RouteDenied)?;
        self.audit
            .record(
                Some(*channel_id),
                &channel.service_id,
                AuditAction::StreamAuthorized,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| AdmissionReject::AuditUnavailable)
    }

    pub(crate) fn audit_quota_denial(
        &mut self,
        channel_id: &[u8; 16],
    ) -> Result<(), AdmissionReject> {
        let channel = self
            .channels
            .bound_channel(channel_id)
            .ok_or(AdmissionReject::RouteDenied)?;
        self.audit
            .record(
                Some(*channel_id),
                &channel.service_id,
                AuditAction::QuotaDenied,
                AuditOutcome::Denied,
                AuditReason::QuotaExceeded,
            )
            .map_err(|_| AdmissionReject::AuditUnavailable)
    }

    pub(crate) fn tombstone_expires_at(&self, channel_id: &[u8; 16]) -> Option<u64> {
        self.channels.tombstone_expires_at(channel_id)
    }

    pub(crate) fn policy_hash(&self, service_id: &str) -> Option<[u8; 32]> {
        self.policy
            .authorized_services
            .get(service_id)
            .map(|policy| policy.policy_hash)
    }

    pub(crate) fn matches_client_hello(
        &self,
        source_operator_id: &str,
        source_edge_id: &str,
        destination_operator_id: &str,
        destination_edge_id: &str,
        client_session_public_key: &[u8; 32],
    ) -> bool {
        source_operator_id == self.policy.source_operator_id
            && source_edge_id == self.policy.source_edge_id
            && destination_operator_id == self.policy.destination_operator_id
            && destination_edge_id == self.policy.destination_edge_id
            && client_session_public_key == &self.policy.client_session_public_key
    }

    pub(crate) fn expected_edge_nonce(&self) -> [u8; 32] {
        self.policy.edge_nonce
    }

    pub fn admit(&mut self, request: RouteOpenRequest) -> Result<ActiveChannel, AdmissionReject> {
        validate_request(&self.policy, &request)?;

        let channel = ActiveChannel {
            channel_id: request.channel_id,
            route_id: request.grant.route_id,
            service_id: request.grant.service_id.clone(),
            route_grant_digest: request.route_grant_digest,
            transport: request.requested_transport.clone(),
            port: request.requested_port,
        };
        match self
            .channels
            .preflight_pending(&channel, &request.grant.unique_nonce)
        {
            Ok(()) => {}
            Err(PendingAdmissionError::Replay) => return Err(AdmissionReject::Replay),
            Err(PendingAdmissionError::ReplayCapacity) => {
                return Err(AdmissionReject::OverCapacity);
            }
            Err(PendingAdmissionError::ChannelCapacity) => {
                self.audit
                    .record(
                        Some(channel.channel_id),
                        &channel.service_id,
                        AuditAction::QuotaDenied,
                        AuditOutcome::Denied,
                        AuditReason::Capacity,
                    )
                    .map_err(|_| AdmissionReject::AuditUnavailable)?;
                return Err(AdmissionReject::OverCapacity);
            }
        }
        self.audit
            .record(
                Some(channel.channel_id),
                &channel.service_id,
                AuditAction::RouteCandidateReserved,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| AdmissionReject::AuditUnavailable)?;
        self.channels.admit_pending_with_resume(
            channel.clone(),
            request.grant.unique_nonce,
            request.grant.expires_at,
            request.grant.client_session_key_thumbprint,
            request.grant.policy_hash,
        );
        Ok(channel)
    }

    pub(crate) fn closed_resume_context(
        &self,
        channel_id: &[u8; 16],
    ) -> Option<ResumeChannelContext> {
        self.channels.closed_resume_context(channel_id)
    }

    pub(crate) fn bound_resume_context(
        &self,
        channel_id: &[u8; 16],
    ) -> Option<ResumeChannelContext> {
        self.channels.bound_resume_context(channel_id)
    }

    pub(crate) fn audit_resume(
        &mut self,
        channel_id: Option<[u8; 16]>,
        service_id: &str,
        action: AuditAction,
        outcome: AuditOutcome,
        reason: AuditReason,
    ) -> Result<(), AdmissionReject> {
        self.audit
            .record(channel_id, service_id, action, outcome, reason)
            .map_err(|_| AdmissionReject::AuditUnavailable)
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
    let service_policy = policy
        .authorized_services
        .get(&grant.service_id)
        .ok_or(AdmissionReject::RouteDenied)?;
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
        || grant.record_sequence != service_policy.accepted_record_sequence
        || grant.policy_hash != service_policy.policy_hash
    {
        return Err(AdmissionReject::GrantInvalid);
    }
    if !grant.allowed_ports.contains(&request.requested_port) {
        return Err(AdmissionReject::RouteDenied);
    }
    Ok(())
}
