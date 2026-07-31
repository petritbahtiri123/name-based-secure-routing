//! Bounded in-memory Service Channel state for one authenticated session.

use std::collections::{HashMap, HashSet};

use crate::{ActiveChannel, AdmissionReject};

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

pub struct ChannelRegistry {
    limits: ChannelLimits,
    pending: HashMap<[u8; 16], PendingChannel>,
    active: HashMap<[u8; 16], ActiveChannel>,
    used_channel_ids: HashSet<[u8; 16]>,
    used_grant_nonces: HashSet<[u8; 16]>,
}

impl ChannelRegistry {
    pub fn new(limits: ChannelLimits) -> Self {
        Self {
            limits,
            pending: HashMap::new(),
            active: HashMap::new(),
            used_channel_ids: HashSet::new(),
            used_grant_nonces: HashSet::new(),
        }
    }

    pub fn admit_pending(
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

    pub fn confirm_active(&mut self, channel_id: &[u8; 16]) -> Result<(), AdmissionReject> {
        let pending = self
            .pending
            .remove(channel_id)
            .ok_or(AdmissionReject::RouteDenied)?;
        self.active.insert(*channel_id, pending.channel);
        Ok(())
    }

    pub fn channel(&self, channel_id: &[u8; 16]) -> Option<&ActiveChannel> {
        self.active.get(channel_id)
    }

    pub fn channel_mut(&mut self, channel_id: &[u8; 16]) -> Option<&mut ActiveChannel> {
        self.active.get_mut(channel_id)
    }

    pub fn remove(&mut self, channel_id: &[u8; 16]) -> Option<ActiveChannel> {
        self.active.remove(channel_id).or_else(|| {
            self.pending
                .remove(channel_id)
                .map(|pending| pending.channel)
        })
    }

    pub fn active_len(&self) -> usize {
        self.active.len()
    }

    pub fn active_for_service(&self, service_id: &str) -> usize {
        self.active
            .values()
            .filter(|channel| channel.service_id == service_id)
            .count()
    }

    fn pending_for_service(&self, service_id: &str) -> usize {
        self.pending
            .values()
            .filter(|pending| pending.channel.service_id == service_id)
            .count()
    }
}
