//! Bounded in-memory Service Channel state for one authenticated session.

use std::collections::HashMap;

use crate::channel_lifecycle::{ChannelState, DrainDeadline, ReplayPreflightError, ReplayStore};
use crate::{ActiveChannel, AdmissionReject, ChannelBinding};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ChannelLimits {
    pub max_channels_per_session: usize,
    pub max_channels_per_service: usize,
}

impl Default for ChannelLimits {
    fn default() -> Self {
        Self {
            max_channels_per_session: 32,
            max_channels_per_service: 8,
        }
    }
}

struct PendingChannel {
    channel: ActiveChannel,
    client_session_key_thumbprint: [u8; 32],
    grant_expires_at: u64,
    grant_nonce: [u8; 16],
    policy_hash: [u8; 32],
}

pub(crate) struct ChannelRegistry {
    limits: ChannelLimits,
    pending: HashMap<[u8; 16], PendingChannel>,
    active: HashMap<[u8; 16], ActiveChannelEntry>,
    terminal: HashMap<[u8; 16], TerminalChannelEntry>,
    replay: ReplayStore,
}

struct ActiveChannelEntry {
    channel: ActiveChannel,
    binding: Option<ChannelBinding>,
    client_session_key_thumbprint: [u8; 32],
    drain_deadline: Option<DrainDeadline>,
    grant_expires_at: u64,
    grant_nonce: [u8; 16],
    policy_hash: [u8; 32],
}

struct TerminalChannelEntry {
    resume: Option<ResumeChannelContext>,
    state: ChannelState,
}

#[derive(Clone)]
pub(crate) struct ResumeChannelContext {
    pub(crate) channel: ActiveChannel,
    pub(crate) client_session_key_thumbprint: [u8; 32],
    pub(crate) grant_expires_at: u64,
    pub(crate) grant_nonce: [u8; 16],
    pub(crate) policy_hash: [u8; 32],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ChannelBindingInstallError {
    AuditUnavailable,
    InvalidState,
    UnknownChannel,
    Mismatch,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ChannelLifecycleError {
    AuditUnavailable,
    UnknownChannel,
    InvalidState,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum PendingAdmissionError {
    Replay,
    ReplayCapacity,
    ChannelCapacity,
}

impl ChannelRegistry {
    pub(crate) fn new(limits: ChannelLimits) -> Self {
        Self {
            limits,
            pending: HashMap::new(),
            active: HashMap::new(),
            terminal: HashMap::new(),
            replay: ReplayStore::new(),
        }
    }

    pub(crate) fn preflight_pending(
        &self,
        channel: &ActiveChannel,
        grant_nonce: &[u8; 16],
    ) -> Result<(), PendingAdmissionError> {
        match self.replay.preflight(&channel.channel_id, grant_nonce) {
            Ok(()) => {}
            Err(ReplayPreflightError::Replay) => return Err(PendingAdmissionError::Replay),
            Err(ReplayPreflightError::Capacity) => {
                return Err(PendingAdmissionError::ReplayCapacity);
            }
        }
        if self.pending.len() + self.active.len() >= self.limits.max_channels_per_session
            || self.pending_for_service(&channel.service_id)
                + self.active_for_service(&channel.service_id)
                >= self.limits.max_channels_per_service
        {
            return Err(PendingAdmissionError::ChannelCapacity);
        }
        Ok(())
    }

    #[cfg(test)]
    pub(crate) fn admit_pending(
        &mut self,
        channel: ActiveChannel,
        grant_nonce: [u8; 16],
        grant_expires_at: u64,
    ) {
        self.admit_pending_with_resume(channel, grant_nonce, grant_expires_at, [0; 32], [0; 32]);
    }

    pub(crate) fn admit_pending_with_resume(
        &mut self,
        channel: ActiveChannel,
        grant_nonce: [u8; 16],
        grant_expires_at: u64,
        client_session_key_thumbprint: [u8; 32],
        policy_hash: [u8; 32],
    ) {
        self.replay.insert(channel.channel_id, grant_nonce);
        self.pending.insert(
            channel.channel_id,
            PendingChannel {
                channel,
                client_session_key_thumbprint,
                grant_expires_at,
                grant_nonce,
                policy_hash,
            },
        );
    }

    pub(crate) fn channel_state(&self, channel_id: &[u8; 16]) -> Option<ChannelState> {
        if self.pending.contains_key(channel_id) {
            Some(ChannelState::Candidate)
        } else if let Some(entry) = self.active.get(channel_id) {
            Some(if entry.drain_deadline.is_some() {
                ChannelState::Draining
            } else {
                ChannelState::Active
            })
        } else {
            self.terminal.get(channel_id).map(|entry| entry.state)
        }
    }

    pub(crate) fn candidate(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.pending.get(channel_id).map(|entry| &entry.channel)
    }

    pub(crate) fn confirm_active(&mut self, channel_id: &[u8; 16]) -> Result<(), AdmissionReject> {
        let pending = self
            .pending
            .remove(channel_id)
            .ok_or(AdmissionReject::RouteDenied)?;
        self.active.insert(
            *channel_id,
            ActiveChannelEntry {
                channel: pending.channel,
                binding: None,
                client_session_key_thumbprint: pending.client_session_key_thumbprint,
                drain_deadline: None,
                grant_expires_at: pending.grant_expires_at,
                grant_nonce: pending.grant_nonce,
                policy_hash: pending.policy_hash,
            },
        );
        Ok(())
    }

    pub(crate) fn channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active
            .get(channel_id)
            .filter(|entry| entry.drain_deadline.is_none())
            .map(|entry| &entry.channel)
    }

    pub(crate) fn bound_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active
            .get(channel_id)
            .filter(|entry| entry.binding.is_some() && entry.drain_deadline.is_none())
            .map(|entry| &entry.channel)
    }

    pub(crate) fn bound_udp_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.bound_channel(channel_id)
            .filter(|channel| channel.transport == "udp")
    }

    pub(crate) fn bound_existing_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active
            .get(channel_id)
            .filter(|entry| entry.binding.is_some())
            .map(|entry| &entry.channel)
    }

    pub(crate) fn lifecycle_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active.get(channel_id).map(|entry| &entry.channel)
    }

    pub(crate) fn prepare_drain(
        &self,
        channel_id: &[u8; 16],
        requested: DrainDeadline,
        monotonic_now: u64,
        unix_now: u64,
        session_deadline: Option<DrainDeadline>,
    ) -> Result<DrainDeadline, ChannelLifecycleError> {
        let entry = self.active.get(channel_id).ok_or_else(|| {
            if self.channel_state(channel_id).is_some() {
                ChannelLifecycleError::InvalidState
            } else {
                ChannelLifecycleError::UnknownChannel
            }
        })?;
        if entry.drain_deadline.is_some() {
            return Err(ChannelLifecycleError::InvalidState);
        }
        let grant_remaining = entry.grant_expires_at.saturating_sub(unix_now);
        let grant_deadline = DrainDeadline::new(monotonic_now, grant_remaining.min(30))
            .map_err(|_| ChannelLifecycleError::InvalidState)?;
        let mut effective = requested.no_later_than(grant_deadline);
        if let Some(session_deadline) = session_deadline {
            effective = effective.no_later_than(session_deadline);
        }
        Ok(effective)
    }

    pub(crate) fn commit_drain(
        &mut self,
        channel_id: &[u8; 16],
        deadline: DrainDeadline,
    ) -> Result<(), ChannelLifecycleError> {
        let entry = self
            .active
            .get_mut(channel_id)
            .ok_or(ChannelLifecycleError::UnknownChannel)?;
        if entry.drain_deadline.is_some() {
            return Err(ChannelLifecycleError::InvalidState);
        }
        entry.drain_deadline = Some(deadline);
        Ok(())
    }

    pub(crate) fn drain_deadline(&self, channel_id: &[u8; 16]) -> Option<DrainDeadline> {
        self.active.get(channel_id)?.drain_deadline
    }

    pub(crate) fn prepare_session_drain(
        &self,
        monotonic_now: u64,
        unix_now: u64,
        session_deadline: DrainDeadline,
    ) -> Result<Vec<([u8; 16], DrainDeadline)>, ChannelLifecycleError> {
        self.active
            .iter()
            .map(|(channel_id, entry)| -> Result<_, ChannelLifecycleError> {
                let grant_remaining = entry.grant_expires_at.saturating_sub(unix_now);
                let grant_deadline = DrainDeadline::new(monotonic_now, grant_remaining.min(30))
                    .map_err(|_| ChannelLifecycleError::InvalidState)?;
                let mut effective = session_deadline.no_later_than(grant_deadline);
                if let Some(channel_deadline) = entry.drain_deadline {
                    effective = effective.no_later_than(channel_deadline);
                }
                Ok((*channel_id, effective))
            })
            .collect()
    }

    pub(crate) fn commit_session_drain(&mut self, channel_deadlines: &[([u8; 16], DrainDeadline)]) {
        for (channel_id, deadline) in channel_deadlines {
            if let Some(entry) = self.active.get_mut(channel_id) {
                entry.drain_deadline = Some(*deadline);
            }
        }
    }

    pub(crate) fn due_draining_channels(&self, monotonic_now: u64) -> Vec<[u8; 16]> {
        let mut due = self
            .active
            .iter()
            .filter_map(|(channel_id, entry)| {
                entry
                    .drain_deadline
                    .filter(|deadline| deadline.is_due(monotonic_now))
                    .map(|_| *channel_id)
            })
            .collect::<Vec<_>>();
        due.sort_unstable();
        due
    }

    pub(crate) fn finish_drain(
        &mut self,
        channel_id: &[u8; 16],
    ) -> Result<(), ChannelLifecycleError> {
        let entry = self.active.remove(channel_id).ok_or_else(|| {
            if self.channel_state(channel_id).is_some() {
                ChannelLifecycleError::InvalidState
            } else {
                ChannelLifecycleError::UnknownChannel
            }
        })?;
        if entry.drain_deadline.is_none() {
            self.active.insert(*channel_id, entry);
            return Err(ChannelLifecycleError::InvalidState);
        }
        self.replay
            .mark_tombstone(channel_id, entry.grant_expires_at.saturating_add(30));
        self.terminal.insert(
            *channel_id,
            TerminalChannelEntry {
                resume: None,
                state: ChannelState::Closed,
            },
        );
        Ok(())
    }

    pub(crate) fn close_live(
        &mut self,
        channel_id: &[u8; 16],
        closed_at: u64,
    ) -> Result<(), ChannelLifecycleError> {
        let entry = self.active.remove(channel_id).ok_or_else(|| {
            if self.channel_state(channel_id).is_some() {
                ChannelLifecycleError::InvalidState
            } else {
                ChannelLifecycleError::UnknownChannel
            }
        })?;
        let resume = (entry.binding.is_some() && entry.drain_deadline.is_none()).then(|| {
            ResumeChannelContext {
                channel: entry.channel.clone(),
                client_session_key_thumbprint: entry.client_session_key_thumbprint,
                grant_expires_at: entry.grant_expires_at,
                grant_nonce: entry.grant_nonce,
                policy_hash: entry.policy_hash,
            }
        });
        let tombstone_expires_at = entry
            .grant_expires_at
            .saturating_add(30)
            .max(closed_at.saturating_add(30));
        self.replay.mark_tombstone(channel_id, tombstone_expires_at);
        self.terminal.insert(
            *channel_id,
            TerminalChannelEntry {
                resume,
                state: ChannelState::Closed,
            },
        );
        Ok(())
    }

    pub(crate) fn install_binding(
        &mut self,
        channel_id: &[u8; 16],
        binding: ChannelBinding,
    ) -> Result<(), ChannelBindingInstallError> {
        let known_channel = self.channel_state(channel_id).is_some();
        let Some(entry) = self.active.get_mut(channel_id) else {
            return Err(if known_channel {
                ChannelBindingInstallError::InvalidState
            } else {
                ChannelBindingInstallError::UnknownChannel
            });
        };
        if !binding.is_for_channel(channel_id) {
            return Err(ChannelBindingInstallError::Mismatch);
        }
        match entry.binding.as_ref() {
            Some(existing) if existing == &binding => Ok(()),
            Some(_) => Err(ChannelBindingInstallError::Mismatch),
            None => {
                entry.binding = Some(binding);
                Ok(())
            }
        }
    }

    pub(crate) fn binding_needs_install(
        &self,
        channel_id: &[u8; 16],
        binding: &ChannelBinding,
    ) -> Result<bool, ChannelBindingInstallError> {
        let entry = self.active.get(channel_id).ok_or_else(|| {
            if self.channel_state(channel_id).is_some() {
                ChannelBindingInstallError::InvalidState
            } else {
                ChannelBindingInstallError::UnknownChannel
            }
        })?;
        if !binding.is_for_channel(channel_id) {
            return Err(ChannelBindingInstallError::Mismatch);
        }
        match entry.binding.as_ref() {
            Some(existing) if existing == binding => Ok(false),
            Some(_) => Err(ChannelBindingInstallError::Mismatch),
            None => Ok(true),
        }
    }

    pub(crate) fn revocable_channel(
        &self,
        channel_id: &[u8; 16],
    ) -> Result<&ActiveChannel, ChannelLifecycleError> {
        if let Some(entry) = self.active.get(channel_id) {
            return Ok(&entry.channel);
        }
        Err(if self.channel_state(channel_id).is_some() {
            ChannelLifecycleError::InvalidState
        } else {
            ChannelLifecycleError::UnknownChannel
        })
    }

    pub(crate) fn revoke(
        &mut self,
        channel_id: &[u8; 16],
        revoked_at: u64,
    ) -> Result<(), ChannelLifecycleError> {
        let entry = self.active.remove(channel_id).ok_or_else(|| {
            if self.channel_state(channel_id).is_some() {
                ChannelLifecycleError::InvalidState
            } else {
                ChannelLifecycleError::UnknownChannel
            }
        })?;
        let tombstone_expires_at = entry
            .grant_expires_at
            .saturating_add(30)
            .max(revoked_at.saturating_add(30));
        self.replay.mark_tombstone(channel_id, tombstone_expires_at);
        self.terminal.insert(
            *channel_id,
            TerminalChannelEntry {
                resume: None,
                state: ChannelState::Revoked,
            },
        );
        Ok(())
    }

    #[cfg(test)]
    pub(crate) fn close_revoked(
        &mut self,
        channel_id: &[u8; 16],
    ) -> Result<(), ChannelLifecycleError> {
        let entry = self
            .terminal
            .get_mut(channel_id)
            .ok_or(ChannelLifecycleError::UnknownChannel)?;
        if entry.state != ChannelState::Revoked {
            return Err(ChannelLifecycleError::InvalidState);
        }
        entry.state = ChannelState::Closed;
        Ok(())
    }

    pub(crate) fn tombstone_expires_at(&self, channel_id: &[u8; 16]) -> Option<u64> {
        self.replay.tombstone_expires_at(channel_id)
    }

    pub(crate) fn closed_resume_context(
        &self,
        channel_id: &[u8; 16],
    ) -> Option<ResumeChannelContext> {
        self.terminal
            .get(channel_id)
            .and_then(|entry| entry.resume.clone())
    }

    pub(crate) fn bound_resume_context(
        &self,
        channel_id: &[u8; 16],
    ) -> Option<ResumeChannelContext> {
        let entry = self.active.get(channel_id)?;
        (entry.binding.is_some() && entry.drain_deadline.is_none()).then(|| ResumeChannelContext {
            channel: entry.channel.clone(),
            client_session_key_thumbprint: entry.client_session_key_thumbprint,
            grant_expires_at: entry.grant_expires_at,
            grant_nonce: entry.grant_nonce,
            policy_hash: entry.policy_hash,
        })
    }

    pub(crate) fn rollback_admission(&mut self, channel_id: &[u8; 16]) -> Option<ActiveChannel> {
        let removed = self
            .active
            .remove(channel_id)
            .map(|entry| (entry.channel, entry.grant_expires_at))
            .or_else(|| {
                self.pending
                    .remove(channel_id)
                    .map(|pending| (pending.channel, pending.grant_expires_at))
            });
        removed.map(|(channel, grant_expires_at)| {
            self.replay
                .mark_tombstone(channel_id, grant_expires_at.saturating_add(30));
            channel
        })
    }

    #[cfg(test)]
    pub(crate) fn remove(&mut self, channel_id: &[u8; 16]) -> Option<ActiveChannel> {
        self.active
            .remove(channel_id)
            .map(|entry| entry.channel)
            .or_else(|| {
                self.pending
                    .remove(channel_id)
                    .map(|pending| pending.channel)
            })
    }

    pub(crate) fn active_len(&self) -> usize {
        self.active.len()
    }

    pub(crate) fn candidate_len(&self) -> usize {
        self.pending.len()
    }

    pub(crate) fn active_for_service(&self, service_id: &str) -> usize {
        self.active
            .values()
            .filter(|entry| entry.channel.service_id == service_id)
            .count()
    }

    fn pending_for_service(&self, service_id: &str) -> usize {
        self.pending
            .values()
            .filter(|pending| pending.channel.service_id == service_id)
            .count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn channel(id: u8, service_id: &str) -> ActiveChannel {
        ActiveChannel {
            channel_id: [id; 16],
            route_id: [id.wrapping_add(0x40); 16],
            service_id: service_id.into(),
            route_grant_digest: [id.wrapping_add(0x80); 32],
            transport: "tcp".into(),
            port: 8443,
        }
    }

    #[test]
    fn enforces_lab_session_and_per_service_bounds() {
        let limits = ChannelLimits::default();
        assert_eq!(limits.max_channels_per_session, 32);
        assert_eq!(limits.max_channels_per_service, 8);

        let mut per_service = ChannelRegistry::new(limits);
        for id in 1..=8 {
            let active = channel(id, "service-a");
            per_service
                .preflight_pending(&active, &[id; 16])
                .expect("first eight channels for one service");
            per_service.admit_pending(active, [id; 16], 1_000);
            per_service
                .confirm_active(&[id; 16])
                .expect("pending channel activates");
        }
        assert_eq!(per_service.active_for_service("service-a"), 8);
        assert_eq!(
            per_service.preflight_pending(&channel(9, "service-a"), &[9; 16]),
            Err(PendingAdmissionError::ChannelCapacity)
        );

        let mut per_session = ChannelRegistry::new(limits);
        for id in 1..=32 {
            let service_id = format!("service-{id}");
            let active = channel(id, &service_id);
            per_session
                .preflight_pending(&active, &[id; 16])
                .expect("first 32 session channels");
            per_session.admit_pending(active, [id; 16], 1_000);
            per_session
                .confirm_active(&[id; 16])
                .expect("pending channel activates");
        }
        assert_eq!(per_session.active_len(), 32);
        assert_eq!(
            per_session.preflight_pending(&channel(33, "service-33"), &[33; 16]),
            Err(PendingAdmissionError::ChannelCapacity)
        );
    }

    #[test]
    fn retains_channel_and_nonce_replay_history_after_removal() {
        let mut registry = ChannelRegistry::new(ChannelLimits::default());
        registry
            .preflight_pending(&channel(1, "service-a"), &[0xa1; 16])
            .expect("fresh channel");
        registry.admit_pending(channel(1, "service-a"), [0xa1; 16], 1_000);
        registry
            .confirm_active(&[1; 16])
            .expect("activate fresh channel");
        assert!(registry.remove(&[1; 16]).is_some());
        assert_eq!(registry.active_len(), 0);

        assert_eq!(
            registry.preflight_pending(&channel(1, "service-b"), &[0xa2; 16]),
            Err(PendingAdmissionError::Replay)
        );
        assert_eq!(
            registry.preflight_pending(&channel(2, "service-b"), &[0xa1; 16]),
            Err(PendingAdmissionError::Replay)
        );
    }

    #[test]
    fn revocation_is_terminal_and_retains_saturating_tombstone_and_replay_keys() {
        let mut registry = ChannelRegistry::new(ChannelLimits::default());
        for id in 1..=2 {
            let active = channel(id, &format!("service-{id}"));
            registry
                .preflight_pending(&active, &[id; 16])
                .expect("fresh sibling channel");
            registry.admit_pending(active, [id; 16], u64::MAX - 10);
            registry
                .confirm_active(&[id; 16])
                .expect("activate sibling channel");
        }

        registry
            .revoke(&[1; 16], u64::MAX - 20)
            .expect("active channel revokes");
        assert_eq!(
            registry.channel_state(&[1; 16]),
            Some(ChannelState::Revoked)
        );
        assert_eq!(registry.channel_state(&[2; 16]), Some(ChannelState::Active));
        assert_eq!(registry.tombstone_expires_at(&[1; 16]), Some(u64::MAX));
        assert_eq!(
            registry.revoke(&[1; 16], u64::MAX),
            Err(ChannelLifecycleError::InvalidState)
        );
        assert_eq!(
            registry.revoke(&[9; 16], u64::MAX),
            Err(ChannelLifecycleError::UnknownChannel)
        );

        registry
            .close_revoked(&[1; 16])
            .expect("revoked channel closes");
        assert_eq!(registry.channel_state(&[1; 16]), Some(ChannelState::Closed));
        assert_eq!(registry.tombstone_expires_at(&[1; 16]), Some(u64::MAX));
        assert_eq!(
            registry.preflight_pending(&channel(1, "service-new"), &[9; 16]),
            Err(PendingAdmissionError::Replay)
        );
        assert_eq!(
            registry.preflight_pending(&channel(9, "service-new"), &[1; 16]),
            Err(PendingAdmissionError::Replay)
        );
        assert_eq!(
            registry.revoke(&[1; 16], u64::MAX),
            Err(ChannelLifecycleError::InvalidState)
        );
        assert_eq!(
            registry.close_revoked(&[2; 16]),
            Err(ChannelLifecycleError::UnknownChannel)
        );
        assert_eq!(registry.channel_state(&[2; 16]), Some(ChannelState::Active));
    }

    #[test]
    fn a_binding_derived_for_one_channel_cannot_bind_a_sibling() {
        let mut registry = ChannelRegistry::new(ChannelLimits::default());
        for id in 1..=2 {
            let active = channel(id, &format!("service-{id}"));
            registry
                .preflight_pending(&active, &[id; 16])
                .expect("fresh sibling channel");
            registry.admit_pending(active, [id; 16], 1_000);
            registry
                .confirm_active(&[id; 16])
                .expect("activate sibling channel");
        }

        let first_binding = ChannelBinding::from_exporter([1; 16], [0xa5; 32]);
        assert_eq!(
            registry.install_binding(&[2; 16], first_binding),
            Err(ChannelBindingInstallError::Mismatch)
        );
        assert!(registry.bound_channel(&[2; 16]).is_none());
    }

    #[test]
    fn draining_and_closing_one_channel_preserves_its_active_sibling() {
        let mut registry = ChannelRegistry::new(ChannelLimits::default());
        for id in 1..=2 {
            let active = channel(id, &format!("service-{id}"));
            registry
                .preflight_pending(&active, &[id; 16])
                .expect("fresh sibling channel");
            registry.admit_pending(active, [id; 16], 1_000);
            registry
                .confirm_active(&[id; 16])
                .expect("activate sibling channel");
        }

        let requested = DrainDeadline::new(100, 30).expect("bounded drain");
        let deadline = registry
            .prepare_drain(&[1; 16], requested, 100, 990, None)
            .expect("prepare target drain");
        registry
            .commit_drain(&[1; 16], deadline)
            .expect("commit target drain");
        assert_eq!(
            registry.channel_state(&[1; 16]),
            Some(ChannelState::Draining)
        );
        assert_eq!(registry.channel_state(&[2; 16]), Some(ChannelState::Active));

        registry.finish_drain(&[1; 16]).expect("close target only");
        assert_eq!(registry.channel_state(&[1; 16]), Some(ChannelState::Closed));
        assert_eq!(registry.channel_state(&[2; 16]), Some(ChannelState::Active));
        assert!(registry.channel(&[2; 16]).is_some());
    }
}
