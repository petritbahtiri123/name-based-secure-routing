//! Bounded, safe-field-only audit history for one control session.

use std::collections::{BTreeMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_AUDIT_EVENTS: usize = 1_024;
const MAX_CHANNEL_AUDIT_EVENTS: usize = 24;
const MIN_UNSCOPED_AUDIT_EVENTS: usize = 256;
const MAX_CHANNEL_SCOPED_AUDIT_EVENTS: usize = MAX_AUDIT_EVENTS - MIN_UNSCOPED_AUDIT_EVENTS;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SafeServiceId(String);

impl SafeServiceId {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub(crate) fn from_validated(value: &str) -> Self {
        Self(value.to_owned())
    }

    pub(crate) fn is_valid(value: &str) -> bool {
        !value.is_empty() && value.len() <= 255 && value.is_ascii()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuditAction {
    RouteCandidateReserved,
    RouteActivated,
    RouteRejected,
    BindingInstalled,
    ChannelRevoked,
    ChannelClosed,
    ChannelDrainStarted,
    ChannelDrainForced,
    SessionDrainStarted,
    SessionDrainForced,
    StreamAuthorized,
    DatagramSendReserved,
    DatagramReceived,
    DatagramPopped,
    DatagramDropped,
    QuotaDenied,
    ResumeConsumed,
    ResumeIssued,
    ResumePreflightIssued,
    ResumePurged,
    ResumeRejected,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuditOutcome {
    Allowed,
    Denied,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuditReason {
    None,
    Capacity,
    CrossEdge,
    Expired,
    FreshAuthorizationRequired,
    Replay,
    InvalidState,
    UnknownChannel,
    BindingMismatch,
    ChannelNotBound,
    StreamRejected,
    QuotaExceeded,
    DatagramMalformed,
    DatagramOversize,
    DatagramQueueFull,
    DatagramRateLimited,
    DatagramWrongChannel,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuditEvent {
    pub unix_timestamp: u64,
    pub sequence: u64,
    pub session_id: [u8; 16],
    pub channel_id: Option<[u8; 16]>,
    pub service_id: SafeServiceId,
    pub action: AuditAction,
    pub outcome: AuditOutcome,
    pub reason: AuditReason,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum AuditError {
    Unavailable,
}

pub(crate) struct AuditLog {
    events: VecDeque<AuditEvent>,
    queued_by_channel: BTreeMap<[u8; 16], usize>,
    queued_channel_events: usize,
    last_sequence: u64,
    session_id: [u8; 16],
}

impl AuditLog {
    pub(crate) fn new() -> Self {
        Self {
            events: VecDeque::with_capacity(MAX_AUDIT_EVENTS),
            queued_by_channel: BTreeMap::new(),
            queued_channel_events: 0,
            last_sequence: 0,
            session_id: [0; 16],
        }
    }

    pub(crate) fn set_session_id(&mut self, session_id: [u8; 16]) {
        self.session_id = session_id;
    }

    pub(crate) fn record(
        &mut self,
        channel_id: Option<[u8; 16]>,
        service_id: &str,
        action: AuditAction,
        outcome: AuditOutcome,
        reason: AuditReason,
    ) -> Result<(), AuditError> {
        if channel_id.is_some_and(|channel_id| {
            self.queued_channel_events >= MAX_CHANNEL_SCOPED_AUDIT_EVENTS
                || self
                    .queued_by_channel
                    .get(&channel_id)
                    .copied()
                    .unwrap_or(0)
                    >= MAX_CHANNEL_AUDIT_EVENTS
        }) {
            return Err(AuditError::Unavailable);
        }
        if self.events.len() >= MAX_AUDIT_EVENTS {
            return Err(AuditError::Unavailable);
        }
        let sequence = self
            .last_sequence
            .checked_add(1)
            .ok_or(AuditError::Unavailable)?;
        let unix_timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| AuditError::Unavailable)?
            .as_secs();
        self.events.push_back(AuditEvent {
            unix_timestamp,
            sequence,
            session_id: self.session_id,
            channel_id,
            service_id: SafeServiceId::from_validated(service_id),
            action,
            outcome,
            reason,
        });
        if let Some(channel_id) = channel_id {
            *self.queued_by_channel.entry(channel_id).or_default() += 1;
            self.queued_channel_events += 1;
        }
        self.last_sequence = sequence;
        Ok(())
    }

    pub(crate) fn events(&self) -> &VecDeque<AuditEvent> {
        &self.events
    }

    pub(crate) fn pop(&mut self) -> Option<AuditEvent> {
        let event = self.events.pop_front()?;
        if let Some(channel_id) = event.channel_id {
            self.queued_channel_events -= 1;
            let remaining = self
                .queued_by_channel
                .get_mut(&channel_id)
                .expect("queued channel audit count exists");
            *remaining -= 1;
            if *remaining == 0 {
                self.queued_by_channel.remove(&channel_id);
            }
        }
        Some(event)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn queued_channel_events_are_capped_without_consuming_sibling_or_session_reserve() {
        let mut audit = AuditLog::new();
        let channel_a = [0xa1; 16];
        let channel_b = [0xb2; 16];

        for _ in 0..24 {
            audit
                .record(
                    Some(channel_a),
                    "service-a",
                    AuditAction::StreamAuthorized,
                    AuditOutcome::Allowed,
                    AuditReason::None,
                )
                .expect("the exact per-channel budget");
        }
        assert_eq!(
            audit.record(
                Some(channel_a),
                "service-a",
                AuditAction::StreamAuthorized,
                AuditOutcome::Allowed,
                AuditReason::None,
            ),
            Err(AuditError::Unavailable)
        );
        assert_eq!(audit.events().len(), 24);

        audit
            .record(
                Some(channel_b),
                "service-b",
                AuditAction::DatagramReceived,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .expect("a sibling has an independent budget");
        audit
            .record(
                None,
                "transport-session",
                AuditAction::SessionDrainStarted,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .expect("session reserve remains available");
        assert_eq!(audit.events().len(), 26);
        assert_eq!(audit.events()[24].sequence, 25);
        assert_eq!(audit.events()[25].sequence, 26);

        assert_eq!(audit.pop().unwrap().channel_id, Some(channel_a));
        audit
            .record(
                Some(channel_a),
                "service-a",
                AuditAction::StreamAuthorized,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .expect("popping a queued event returns one channel slot");
        assert_eq!(audit.events().len(), 26);
    }

    #[test]
    fn thirty_two_channel_partitions_leave_exactly_256_global_slots() {
        let mut audit = AuditLog::new();
        for channel in 1..=32_u8 {
            for _ in 0..24 {
                audit
                    .record(
                        Some([channel; 16]),
                        "bounded-service",
                        AuditAction::StreamAuthorized,
                        AuditOutcome::Allowed,
                        AuditReason::None,
                    )
                    .unwrap();
            }
        }
        assert_eq!(audit.events().len(), 768);
        assert_eq!(
            audit.record(
                Some([33; 16]),
                "rejected-service",
                AuditAction::QuotaDenied,
                AuditOutcome::Denied,
                AuditReason::Capacity,
            ),
            Err(AuditError::Unavailable)
        );
        assert_eq!(audit.events().len(), 768);
        for _ in 0..256 {
            audit
                .record(
                    None,
                    "transport-session",
                    AuditAction::SessionDrainForced,
                    AuditOutcome::Allowed,
                    AuditReason::None,
                )
                .expect("the exact non-channel reserve");
        }
        assert_eq!(audit.events().len(), 1_024);
        assert_eq!(
            audit.record(
                None,
                "transport-session",
                AuditAction::SessionDrainForced,
                AuditOutcome::Allowed,
                AuditReason::None,
            ),
            Err(AuditError::Unavailable)
        );
        assert_eq!(audit.events().len(), 1_024);
    }

    #[test]
    fn sequence_can_reach_u64_max_once_and_then_fails_without_wrapping() {
        let mut audit = AuditLog::new();
        audit.last_sequence = u64::MAX - 1;
        audit
            .record(
                Some([1; 16]),
                "service-a",
                AuditAction::ChannelRevoked,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .expect("last representable sequence");
        assert_eq!(
            audit.events().front().map(|event| event.sequence),
            Some(u64::MAX)
        );
        assert!(audit.pop().is_some());

        assert_eq!(
            audit.record(
                Some([2; 16]),
                "service-b",
                AuditAction::ChannelRevoked,
                AuditOutcome::Allowed,
                AuditReason::None,
            ),
            Err(AuditError::Unavailable)
        );
        assert!(audit.events().is_empty());
        assert_eq!(audit.last_sequence, u64::MAX);
    }
}
