//! Bounded in-memory Service Channel state for one authenticated session.

use std::collections::{HashMap, HashSet};

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
}

pub(crate) struct ChannelRegistry {
    limits: ChannelLimits,
    pending: HashMap<[u8; 16], PendingChannel>,
    active: HashMap<[u8; 16], ActiveChannelEntry>,
    used_channel_ids: HashSet<[u8; 16]>,
    used_grant_nonces: HashSet<[u8; 16]>,
}

struct ActiveChannelEntry {
    channel: ActiveChannel,
    binding: Option<ChannelBinding>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ChannelBindingInstallError {
    UnknownChannel,
    Mismatch,
}

impl ChannelRegistry {
    pub(crate) fn new(limits: ChannelLimits) -> Self {
        Self {
            limits,
            pending: HashMap::new(),
            active: HashMap::new(),
            used_channel_ids: HashSet::new(),
            used_grant_nonces: HashSet::new(),
        }
    }

    pub(crate) fn admit_pending(
        &mut self,
        channel: ActiveChannel,
        grant_nonce: [u8; 16],
    ) -> Result<(), AdmissionReject> {
        if self.used_channel_ids.contains(&channel.channel_id)
            || self.used_grant_nonces.contains(&grant_nonce)
        {
            return Err(AdmissionReject::Replay);
        }
        if self.pending.len() + self.active.len() >= self.limits.max_channels_per_session
            || self.pending_for_service(&channel.service_id)
                + self.active_for_service(&channel.service_id)
                >= self.limits.max_channels_per_service
        {
            return Err(AdmissionReject::OverCapacity);
        }

        self.used_channel_ids.insert(channel.channel_id);
        self.used_grant_nonces.insert(grant_nonce);
        self.pending
            .insert(channel.channel_id, PendingChannel { channel });
        Ok(())
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
            },
        );
        Ok(())
    }

    pub(crate) fn channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active.get(channel_id).map(|entry| &entry.channel)
    }

    pub(crate) fn bound_channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active
            .get(channel_id)
            .filter(|entry| entry.binding.is_some())
            .map(|entry| &entry.channel)
    }

    pub(crate) fn install_binding(
        &mut self,
        channel_id: &[u8; 16],
        binding: ChannelBinding,
    ) -> Result<(), ChannelBindingInstallError> {
        let entry = self
            .active
            .get_mut(channel_id)
            .ok_or(ChannelBindingInstallError::UnknownChannel)?;
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

    #[allow(dead_code)] // Reserved for the later bounded channel-lifecycle task.
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
            per_service
                .admit_pending(channel(id, "service-a"), [id; 16])
                .expect("first eight channels for one service");
            per_service
                .confirm_active(&[id; 16])
                .expect("pending channel activates");
        }
        assert_eq!(per_service.active_for_service("service-a"), 8);
        assert_eq!(
            per_service.admit_pending(channel(9, "service-a"), [9; 16]),
            Err(AdmissionReject::OverCapacity)
        );

        let mut per_session = ChannelRegistry::new(limits);
        for id in 1..=32 {
            let service_id = format!("service-{id}");
            per_session
                .admit_pending(channel(id, &service_id), [id; 16])
                .expect("first 32 session channels");
            per_session
                .confirm_active(&[id; 16])
                .expect("pending channel activates");
        }
        assert_eq!(per_session.active_len(), 32);
        assert_eq!(
            per_session.admit_pending(channel(33, "service-33"), [33; 16]),
            Err(AdmissionReject::OverCapacity)
        );
    }

    #[test]
    fn retains_channel_and_nonce_replay_history_after_removal() {
        let mut registry = ChannelRegistry::new(ChannelLimits::default());
        registry
            .admit_pending(channel(1, "service-a"), [0xa1; 16])
            .expect("fresh channel");
        registry
            .confirm_active(&[1; 16])
            .expect("activate fresh channel");
        assert!(registry.remove(&[1; 16]).is_some());
        assert_eq!(registry.active_len(), 0);

        assert_eq!(
            registry.admit_pending(channel(1, "service-b"), [0xa2; 16]),
            Err(AdmissionReject::Replay)
        );
        assert_eq!(
            registry.admit_pending(channel(2, "service-b"), [0xa1; 16]),
            Err(AdmissionReject::Replay)
        );
    }

    #[test]
    fn a_binding_derived_for_one_channel_cannot_bind_a_sibling() {
        let mut registry = ChannelRegistry::new(ChannelLimits::default());
        for id in 1..=2 {
            registry
                .admit_pending(channel(id, &format!("service-{id}")), [id; 16])
                .expect("fresh sibling channel");
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
}
