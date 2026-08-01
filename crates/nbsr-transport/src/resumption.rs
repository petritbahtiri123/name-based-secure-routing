//! Bounded same-edge correlation after independent fresh authorization.

use std::collections::HashMap;
use std::fmt;

use crate::channel_registry::ResumeChannelContext;
use crate::quinn_adapter::ConnectionBindingCapability;
use crate::{AuditReason, ControlSession, EdgeRole};

const MAX_RESUME_RECORDS: usize = 4_096;
const MAX_RESUME_SECONDS: u64 = 30;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResumeReject {
    AuditUnavailable,
    Capacity,
    CrossEdgeDenied,
    Expired,
    FreshAuthorizationRequired,
    Ineligible,
    InvalidHandle,
    InvalidTrustProfileId,
    Mismatch,
    Replay,
}

#[derive(Clone, Eq, Hash, PartialEq)]
pub struct TrustProfileId(String);

impl TrustProfileId {
    pub fn new(value: &str) -> Result<Self, ResumeReject> {
        if value.is_empty()
            || value.len() > 64
            || !value.bytes().all(|byte| {
                byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'-')
            })
        {
            return Err(ResumeReject::InvalidTrustProfileId);
        }
        Ok(Self(value.to_owned()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for TrustProfileId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_tuple("TrustProfileId")
            .field(&self.0)
            .finish()
    }
}

#[derive(Clone, Eq, Hash, PartialEq)]
pub struct ResumeHandle([u8; 32]);

impl ResumeHandle {
    pub fn new(bytes: [u8; 32]) -> Result<Self, ResumeReject> {
        if bytes == [0; 32] {
            return Err(ResumeReject::InvalidHandle);
        }
        Ok(Self(bytes))
    }
}

impl fmt::Debug for ResumeHandle {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ResumeHandle([REDACTED])")
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResumeCorrelation {
    pub old_channel_id: [u8; 16],
    pub new_channel_id: [u8; 16],
}

#[derive(Clone, Eq, PartialEq)]
pub(crate) struct ResumeReuseKey {
    pub(crate) source_edge_id: String,
    pub(crate) destination_edge_id: String,
    pub(crate) trust_profile_id: TrustProfileId,
    pub(crate) alpn: Vec<u8>,
    pub(crate) protocol_version: u64,
}

#[derive(Clone)]
pub(crate) struct ResumeSessionContext {
    pub(crate) reuse_key: ResumeReuseKey,
    pub(crate) authenticated_peer: String,
    pub(crate) channel: ResumeChannelContext,
    pub(crate) client_nonce: [u8; 32],
    pub(crate) connection_capability: ConnectionBindingCapability,
    pub(crate) edge_nonce: [u8; 32],
    pub(crate) local_role: EdgeRole,
    pub(crate) session_deadline: Option<u64>,
    pub(crate) session_id: [u8; 16],
}

pub(crate) struct ResumeSessionScope {
    pub(crate) reuse_key: ResumeReuseKey,
}

#[derive(Clone)]
struct ResumeRecord {
    old: ResumeSessionContext,
    expires_at: u64,
}

pub struct SameEdgeResumeManager {
    records: HashMap<ResumeHandle, ResumeRecord>,
}

impl Default for SameEdgeResumeManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SameEdgeResumeManager {
    pub fn new() -> Self {
        Self {
            records: HashMap::new(),
        }
    }

    pub fn retained_records(&self) -> usize {
        self.records.len()
    }

    pub fn issue(
        &mut self,
        old_session: &mut ControlSession,
        old_channel_id: [u8; 16],
        handle: ResumeHandle,
        monotonic_now: u64,
        unix_now: u64,
    ) -> Result<(), ResumeReject> {
        let old = match old_session.closed_resume_context(old_channel_id) {
            Ok(context) => context,
            Err(error) => {
                old_session.audit_resume_reject(
                    old_channel_id,
                    "transport-resume",
                    AuditReason::InvalidState,
                )?;
                return Err(error);
            }
        };
        if self.records.contains_key(&handle) {
            old_session.audit_resume_reject(
                old_channel_id,
                &old.channel.channel.service_id,
                AuditReason::Replay,
            )?;
            return Err(ResumeReject::Replay);
        }
        if self.records.len() >= MAX_RESUME_RECORDS {
            old_session.audit_resume_reject(
                old_channel_id,
                &old.channel.channel.service_id,
                AuditReason::Capacity,
            )?;
            return Err(ResumeReject::Capacity);
        }
        if unix_now > old.channel.grant_expires_at {
            old_session.audit_resume_reject(
                old_channel_id,
                &old.channel.channel.service_id,
                AuditReason::Expired,
            )?;
            return Err(ResumeReject::Expired);
        }
        let grant_remaining = old.channel.grant_expires_at.saturating_sub(unix_now);
        let mut expires_at = monotonic_now.saturating_add(MAX_RESUME_SECONDS.min(grant_remaining));
        if let Some(session_deadline) = old.session_deadline {
            expires_at = expires_at.min(session_deadline);
        }
        old_session.audit_resume_issue(&old)?;
        self.records
            .insert(handle, ResumeRecord { old, expires_at });
        Ok(())
    }

    pub(crate) fn preflight_same_edge(
        &mut self,
        handle: &ResumeHandle,
        new_session: &mut ControlSession,
        monotonic_now: u64,
    ) -> Result<(), ResumeReject> {
        let Some(record) = self.records.get(handle).cloned() else {
            new_session.audit_resume_session_reject(None, AuditReason::Replay)?;
            return Err(ResumeReject::Replay);
        };
        if monotonic_now > record.expires_at {
            new_session.audit_resume_reject(
                record.old.channel.channel.channel_id,
                &record.old.channel.channel.service_id,
                AuditReason::Expired,
            )?;
            self.records.remove(handle);
            return Err(ResumeReject::Expired);
        }
        let scope = match new_session.resume_scope() {
            Ok(scope) => scope,
            Err(error) => {
                new_session.audit_resume_session_reject(None, AuditReason::InvalidState)?;
                return Err(error);
            }
        };
        if record.old.reuse_key.source_edge_id != scope.reuse_key.source_edge_id
            || record.old.reuse_key.destination_edge_id != scope.reuse_key.destination_edge_id
        {
            new_session.audit_resume_reject(
                record.old.channel.channel.channel_id,
                &record.old.channel.channel.service_id,
                AuditReason::CrossEdge,
            )?;
            return Err(ResumeReject::CrossEdgeDenied);
        }
        if record.old.reuse_key != scope.reuse_key {
            new_session.audit_resume_reject(
                record.old.channel.channel.channel_id,
                &record.old.channel.channel.service_id,
                AuditReason::BindingMismatch,
            )?;
            return Err(ResumeReject::Mismatch);
        }
        Ok(())
    }

    pub(crate) fn consume(
        &mut self,
        handle: &ResumeHandle,
        new_session: &mut ControlSession,
        new_channel_id: [u8; 16],
        monotonic_now: u64,
        unix_now: u64,
    ) -> Result<ResumeCorrelation, ResumeReject> {
        self.preflight_same_edge(handle, new_session, monotonic_now)?;
        let record = self
            .records
            .get(handle)
            .ok_or(ResumeReject::Replay)?
            .clone();
        let new = match new_session.bound_resume_context(new_channel_id) {
            Ok(context) => context,
            Err(error) => {
                new_session
                    .audit_resume_session_reject(Some(new_channel_id), AuditReason::InvalidState)?;
                return Err(error);
            }
        };
        if unix_now > new.channel.grant_expires_at {
            new_session.audit_resume_reject(
                new_channel_id,
                &new.channel.channel.service_id,
                AuditReason::Expired,
            )?;
            return Err(ResumeReject::Expired);
        }
        if record.old.local_role != new.local_role
            || record.old.authenticated_peer != new.authenticated_peer
            || record
                .old
                .connection_capability
                .matches(&new.connection_capability)
            || record.old.session_id == new.session_id
            || record.old.channel.channel.channel_id == new.channel.channel.channel_id
            || record.old.channel.channel.route_grant_digest
                == new.channel.channel.route_grant_digest
            || record.old.channel.channel.route_id == new.channel.channel.route_id
            || record.old.channel.grant_nonce == new.channel.grant_nonce
            || record.old.client_nonce == new.client_nonce
            || record.old.edge_nonce == new.edge_nonce
        {
            new_session.audit_resume_reject(
                new_channel_id,
                &new.channel.channel.service_id,
                AuditReason::FreshAuthorizationRequired,
            )?;
            return Err(ResumeReject::FreshAuthorizationRequired);
        }
        if record.old.channel.channel.service_id != new.channel.channel.service_id
            || record.old.channel.policy_hash != new.channel.policy_hash
            || record.old.channel.client_session_key_thumbprint
                != new.channel.client_session_key_thumbprint
        {
            new_session.audit_resume_reject(
                new_channel_id,
                &new.channel.channel.service_id,
                AuditReason::BindingMismatch,
            )?;
            return Err(ResumeReject::Mismatch);
        }
        new_session.audit_resume_consume(&new)?;
        self.records.remove(handle).ok_or(ResumeReject::Replay)?;
        Ok(ResumeCorrelation {
            old_channel_id: record.old.channel.channel.channel_id,
            new_channel_id,
        })
    }
}
