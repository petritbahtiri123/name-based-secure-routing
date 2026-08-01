//! Explicit channel lifecycle and bounded replay/tombstone state.

use std::collections::HashMap;

const MAX_REPLAY_ENTRIES: usize = 4_096;
pub const MAX_DRAIN_SECONDS: u64 = 30;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ChannelState {
    Candidate,
    Active,
    Draining,
    Revoked,
    Closed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionDrainState {
    Active,
    Draining,
    Closed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DrainReject {
    TooLong,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuditIntegrity {
    Recorded,
    Failed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DrainEnforcement {
    Pending,
    Enforced { audit_integrity: AuditIntegrity },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionDrainEnforcement {
    Pending { audit_integrity: AuditIntegrity },
    Enforced { audit_integrity: AuditIntegrity },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DrainDeadline {
    monotonic_seconds: u64,
}

impl DrainDeadline {
    pub fn new(monotonic_now: u64, requested_seconds: u64) -> Result<Self, DrainReject> {
        if requested_seconds > MAX_DRAIN_SECONDS {
            return Err(DrainReject::TooLong);
        }
        Ok(Self {
            monotonic_seconds: monotonic_now.saturating_add(requested_seconds),
        })
    }

    pub fn monotonic_seconds(self) -> u64 {
        self.monotonic_seconds
    }

    pub fn is_due(self, monotonic_now: u64) -> bool {
        monotonic_now >= self.monotonic_seconds
    }

    pub(crate) fn no_later_than(self, other: Self) -> Self {
        Self {
            monotonic_seconds: self.monotonic_seconds.min(other.monotonic_seconds),
        }
    }
}

pub(crate) struct ReplayStore {
    by_channel: HashMap<[u8; 16], Option<u64>>,
    by_nonce: HashMap<[u8; 16], [u8; 16]>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ReplayPreflightError {
    Replay,
    Capacity,
}

impl ReplayStore {
    pub(crate) fn new() -> Self {
        Self {
            by_channel: HashMap::new(),
            by_nonce: HashMap::new(),
        }
    }

    pub(crate) fn preflight(
        &self,
        channel_id: &[u8; 16],
        grant_nonce: &[u8; 16],
    ) -> Result<(), ReplayPreflightError> {
        if self.by_channel.contains_key(channel_id) || self.by_nonce.contains_key(grant_nonce) {
            return Err(ReplayPreflightError::Replay);
        }
        if self.by_channel.len() >= MAX_REPLAY_ENTRIES {
            return Err(ReplayPreflightError::Capacity);
        }
        Ok(())
    }

    pub(crate) fn insert(&mut self, channel_id: [u8; 16], grant_nonce: [u8; 16]) {
        self.by_nonce.insert(grant_nonce, channel_id);
        self.by_channel.insert(channel_id, None);
    }

    pub(crate) fn mark_tombstone(&mut self, channel_id: &[u8; 16], expires_at: u64) {
        if let Some(entry) = self.by_channel.get_mut(channel_id) {
            *entry = Some(expires_at);
        }
    }

    pub(crate) fn rollback_live(&mut self, channel_id: &[u8; 16]) {
        if self.by_channel.get(channel_id) == Some(&None) {
            self.by_channel.remove(channel_id);
            self.by_nonce.retain(|_, owner| owner != channel_id);
        }
    }

    pub(crate) fn tombstone_expires_at(&self, channel_id: &[u8; 16]) -> Option<u64> {
        self.by_channel.get(channel_id).copied().flatten()
    }
}
