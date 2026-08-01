//! Bounded, safe-field-only audit history for one control session.

use std::collections::VecDeque;
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_AUDIT_EVENTS: usize = 1_024;

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
    QuotaDenied,
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
    Replay,
    InvalidState,
    UnknownChannel,
    BindingMismatch,
    ChannelNotBound,
    StreamRejected,
    QuotaExceeded,
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
    last_sequence: u64,
    session_id: [u8; 16],
}

impl AuditLog {
    pub(crate) fn new() -> Self {
        Self {
            events: VecDeque::with_capacity(MAX_AUDIT_EVENTS),
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
        self.last_sequence = sequence;
        Ok(())
    }

    pub(crate) fn events(&self) -> &VecDeque<AuditEvent> {
        &self.events
    }

    pub(crate) fn pop(&mut self) -> Option<AuditEvent> {
        self.events.pop_front()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
