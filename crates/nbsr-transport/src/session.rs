//! Origin-free control-session sequencing and reusable route admission.

use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Instant;

use sha2::{Digest, Sha256};

use crate::channel_binding::ChannelBindingRequest;
use crate::channel_registry::{
    ChannelBindingInstallError, ChannelLifecycleError, ResumeChannelContext,
};
use crate::channel_streams::{
    ChannelStreams, CreditedStreamReject, PreparedStreamOpen, ReplayHistoryLimit,
};
use crate::federation::LocalFederationAdmissionAttestations;
use crate::quinn_adapter::ConnectionBindingCapability;
use crate::resumption::{ResumeReuseKey, ResumeSessionContext, ResumeSessionScope};
use crate::stream_credit::{
    StreamCreditBinding, StreamCreditContext, StreamCreditPreface, StreamCreditReject,
    StreamCreditWindows,
};
use crate::{
    ActiveChannel, AdmissionReject, AuditAction, AuditEvent, AuditIntegrity, AuditOutcome,
    AuditReason, AuthenticatedConnection, ChannelBinding, ChannelState, CoreV02Envelope,
    CoreV02MessageType, DestinationAdmission, DrainDeadline, DrainEnforcement, EdgeIdentity,
    EdgeRole, ResumeReject, RouteGrantIssuer, SessionDrainState, StreamReject, TrustProfileId,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionReject {
    Admission(AdmissionReject),
    ChannelBindingFailed,
    ChannelBindingRequired,
    AuditUnavailable,
    ConnectionMismatch,
    ControlRejected,
    InvalidChannelState,
    Replay,
    Stream(StreamReject),
    StreamCredit(StreamCreditReject),
    UnexpectedMessage,
}

pub const MAX_SESSION_SECONDS: u64 = 3_600;

pub(crate) trait SessionClock: Send + Sync {
    fn unix_seconds(&self) -> u64;
    fn monotonic_seconds(&self) -> u64;
}

struct AnchoredClock {
    unix_anchor: u64,
    started: Instant,
}

fn process_monotonic_seconds() -> u64 {
    static PROCESS_MONOTONIC_ORIGIN: OnceLock<Instant> = OnceLock::new();
    PROCESS_MONOTONIC_ORIGIN
        .get_or_init(Instant::now)
        .elapsed()
        .as_secs()
}

impl SessionClock for AnchoredClock {
    fn unix_seconds(&self) -> u64 {
        self.unix_anchor
            .saturating_add(self.started.elapsed().as_secs())
    }
    fn monotonic_seconds(&self) -> u64 {
        process_monotonic_seconds()
    }
}

#[derive(Clone, Copy)]
pub(crate) struct ResumeTimeAuthority {
    pub(crate) monotonic_seconds: u64,
    pub(crate) unix_seconds: u64,
}

pub struct ControlSession {
    admission: DestinationAdmission,
    authenticated_peer: EdgeIdentity,
    connection_capability: ConnectionBindingCapability,
    local_role: EdgeRole,
    negotiated_alpn: Vec<u8>,
    trusted_issuers: Vec<RouteGrantIssuer>,
    state: SessionState,
    request_ids: HashSet<[u8; 16]>,
    datagrams: HashMap<[u8; 16], crate::DatagramGate>,
    streams: ChannelStreams,
    stream_credits: StreamCreditWindows,
    stream_credit_profiles: HashMap<[u8; 16], crate::StreamCreditProfile>,
    session_deadline: Option<DrainDeadline>,
    created_at_monotonic: u64,
    hard_session_deadline: u64,
    session_drain_state: SessionDrainState,
    session_drain_deadline: Option<DrainDeadline>,
    trust_profile_id: TrustProfileId,
    clock: Arc<dyn SessionClock>,
}

/// Cloneable owner for short, synchronous control-session state transitions.
///
/// The closure APIs deliberately prevent a `ControlSession` borrow from
/// escaping. Credited stream transport I/O can therefore run concurrently
/// without holding the session lock across an async wait.
#[derive(Clone)]
pub struct SharedControlSession {
    inner: Arc<Mutex<ControlSession>>,
}

impl SharedControlSession {
    #[must_use]
    pub fn new(session: ControlSession) -> Self {
        Self {
            inner: Arc::new(Mutex::new(session)),
        }
    }

    pub fn inspect<T>(&self, operation: impl FnOnce(&ControlSession) -> T) -> T {
        let session = self
            .inner
            .lock()
            .expect("shared control session state is poisoned");
        operation(&session)
    }

    pub fn update<T>(&self, operation: impl FnOnce(&mut ControlSession) -> T) -> T {
        let mut session = self
            .inner
            .lock()
            .expect("shared control session state is poisoned");
        operation(&mut session)
    }

    pub(crate) fn release_credited_stream_terminal(&self, channel_id: [u8; 16], stream_id: u64) {
        let mut session = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        session.release_credited_stream_terminal(channel_id, stream_id);
    }
}

enum SessionState {
    AwaitingClientHello,
    AwaitingEdgeHello {
        client_nonce: [u8; 32],
        client_session_public_key: [u8; 32],
        destination_edge_id: String,
        request_id: [u8; 16],
        session_id: [u8; 16],
        source_edge_id: String,
        source_sequence: u64,
    },
    Established {
        client_nonce: [u8; 32],
        destination_sequence: u64,
        destination_edge_id: String,
        edge_nonce: [u8; 32],
        pending: Option<PendingRoute>,
        session_id: [u8; 16],
        source_edge_id: String,
        source_sequence: u64,
    },
}

#[derive(Clone, Copy)]
struct PendingRoute {
    channel_id: [u8; 16],
    grant_digest: [u8; 32],
    request_id: [u8; 16],
    route_id: [u8; 16],
}

impl ControlSession {
    pub fn new(
        connection: &AuthenticatedConnection,
        admission: DestinationAdmission,
        trusted_issuers: Vec<RouteGrantIssuer>,
        trust_profile_id: TrustProfileId,
    ) -> Self {
        Self::new_with_replay_history_limit(
            connection,
            admission,
            trusted_issuers,
            trust_profile_id,
            ReplayHistoryLimit::MAX,
        )
    }

    pub fn new_with_replay_history_limit(
        connection: &AuthenticatedConnection,
        admission: DestinationAdmission,
        trusted_issuers: Vec<RouteGrantIssuer>,
        trust_profile_id: TrustProfileId,
        replay_history_limit: ReplayHistoryLimit,
    ) -> Self {
        let clock = Arc::new(AnchoredClock {
            unix_anchor: admission.trusted_unix_anchor(),
            started: Instant::now(),
        });
        Self::new_inner(
            connection,
            admission,
            trusted_issuers,
            trust_profile_id,
            clock,
            None,
            replay_history_limit,
        )
    }

    #[cfg(test)]
    pub(crate) fn new_with_clock(
        connection: &AuthenticatedConnection,
        admission: DestinationAdmission,
        trusted_issuers: Vec<RouteGrantIssuer>,
        trust_profile_id: TrustProfileId,
        clock: Arc<dyn SessionClock>,
    ) -> Self {
        Self::new_inner(
            connection,
            admission,
            trusted_issuers,
            trust_profile_id,
            clock,
            None,
            ReplayHistoryLimit::MAX,
        )
    }

    #[cfg(test)]
    pub(crate) fn new_with_clock_and_replay_history_limit(
        connection: &AuthenticatedConnection,
        admission: DestinationAdmission,
        trusted_issuers: Vec<RouteGrantIssuer>,
        trust_profile_id: TrustProfileId,
        clock: Arc<dyn SessionClock>,
        replay_history_limit: ReplayHistoryLimit,
    ) -> Self {
        Self::new_inner(
            connection,
            admission,
            trusted_issuers,
            trust_profile_id,
            clock,
            None,
            replay_history_limit,
        )
    }

    fn new_inner(
        connection: &AuthenticatedConnection,
        admission: DestinationAdmission,
        trusted_issuers: Vec<RouteGrantIssuer>,
        trust_profile_id: TrustProfileId,
        clock: Arc<dyn SessionClock>,
        session_deadline: Option<DrainDeadline>,
        replay_history_limit: ReplayHistoryLimit,
    ) -> Self {
        let created_at_monotonic = clock.monotonic_seconds();
        crate::diagnostics::global().created(crate::diagnostics::DiagnosticOwner::TransportSession);
        Self {
            admission,
            authenticated_peer: connection.authenticated_peer().clone(),
            connection_capability: connection.binding_capability(),
            local_role: connection.local_role(),
            negotiated_alpn: connection.negotiated_alpn().to_vec(),
            trusted_issuers,
            state: SessionState::AwaitingClientHello,
            request_ids: HashSet::new(),
            datagrams: HashMap::new(),
            streams: ChannelStreams::new(replay_history_limit),
            stream_credits: StreamCreditWindows::new(),
            stream_credit_profiles: HashMap::new(),
            session_deadline,
            created_at_monotonic,
            hard_session_deadline: created_at_monotonic.saturating_add(MAX_SESSION_SECONDS),
            session_drain_state: SessionDrainState::Active,
            session_drain_deadline: None,
            trust_profile_id,
            clock,
        }
    }

    pub fn active_channels(&self) -> usize {
        self.admission.active_channels()
    }

    pub fn candidate_channels(&self) -> usize {
        self.admission.candidate_channels()
    }

    pub(crate) fn resume_time_authority(&self) -> ResumeTimeAuthority {
        ResumeTimeAuthority {
            monotonic_seconds: self.clock.monotonic_seconds(),
            unix_seconds: self.clock.unix_seconds(),
        }
    }

    #[cfg(test)]
    pub(crate) fn monotonic_created_at(&self) -> u64 {
        self.created_at_monotonic
    }

    #[cfg(test)]
    pub(crate) fn monotonic_hard_deadline(&self) -> u64 {
        self.hard_session_deadline
    }

    #[cfg(test)]
    pub(crate) fn monotonic_age(&self) -> u64 {
        self.clock
            .monotonic_seconds()
            .saturating_sub(self.created_at_monotonic)
    }

    pub fn has_active_channel(&self, channel_id: [u8; 16]) -> bool {
        self.admission.channel(&channel_id).is_some()
    }

    pub fn channel_state(&self, channel_id: [u8; 16]) -> Option<ChannelState> {
        self.admission.channel_state(channel_id)
    }

    pub fn tombstone_expires_at(&self, channel_id: [u8; 16]) -> Option<u64> {
        self.admission.tombstone_expires_at(&channel_id)
    }

    pub fn channel_drain_deadline(&self, channel_id: [u8; 16]) -> Option<u64> {
        self.admission
            .channel_drain_deadline(&channel_id)
            .map(DrainDeadline::monotonic_seconds)
    }

    pub fn session_drain_state(&self) -> SessionDrainState {
        self.session_drain_state
    }

    pub fn session_drain_deadline(&self) -> Option<u64> {
        self.session_drain_deadline
            .map(DrainDeadline::monotonic_seconds)
    }

    pub fn begin_session_drain(
        &mut self,
        monotonic_now: u64,
        unix_now: u64,
        requested_seconds: u64,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        self.established_session_id()?;
        if self.session_drain_state != SessionDrainState::Active {
            return Err(SessionReject::InvalidChannelState);
        }
        let mut deadline = DrainDeadline::new(monotonic_now, requested_seconds)
            .map_err(|_| SessionReject::ControlRejected)?;
        if let Some(session_deadline) = self.session_deadline {
            deadline = deadline.no_later_than(session_deadline);
        }
        self.admission
            .start_session_drain(monotonic_now, unix_now, deadline)
            .map_err(map_lifecycle)?;
        for gate in self.datagrams.values_mut() {
            gate.deactivate();
        }
        self.session_drain_state = SessionDrainState::Draining;
        self.session_drain_deadline = Some(deadline);
        Ok(())
    }

    pub(crate) fn enforce_session_drain(
        &mut self,
        monotonic_now: u64,
    ) -> Result<DrainEnforcement, SessionReject> {
        if self.session_drain_state != SessionDrainState::Draining {
            return Err(SessionReject::InvalidChannelState);
        }
        let deadline = self
            .session_drain_deadline
            .ok_or(SessionReject::InvalidChannelState)?;
        if !deadline.is_due(monotonic_now) {
            return Ok(DrainEnforcement::Pending);
        }
        match self.admission.audit_session_drain_forced() {
            Ok(()) => {
                self.streams.revoke_all();
                if let Ok(session_id) = self.established_session_id() {
                    self.stream_credits.remove_session(session_id);
                }
                self.stream_credit_profiles.clear();
                for gate in self.datagrams.values_mut() {
                    gate.deactivate();
                }
                self.session_drain_state = SessionDrainState::Closed;
                Ok(DrainEnforcement::Enforced {
                    audit_integrity: AuditIntegrity::Recorded,
                })
            }
            Err(ChannelLifecycleError::AuditUnavailable) => {
                for gate in self.datagrams.values_mut() {
                    gate.deactivate();
                }
                Ok(DrainEnforcement::Enforced {
                    audit_integrity: AuditIntegrity::Failed,
                })
            }
            Err(error) => Err(map_lifecycle(error)),
        }
    }

    pub(crate) fn due_draining_channels(&self, monotonic_now: u64) -> Vec<[u8; 16]> {
        self.admission.due_draining_channels(monotonic_now)
    }

    pub fn audit_events(&self) -> impl ExactSizeIterator<Item = &AuditEvent> {
        self.admission.audit_events()
    }

    pub fn pop_audit_event(&mut self) -> Option<AuditEvent> {
        self.admission.pop_audit_event()
    }

    #[cfg(test)]
    pub(crate) fn fill_audit_for_test(&mut self, channel_id: [u8; 16]) {
        while self.audit_events().len() < 1_024 {
            self.admission
                .audit_stream_authorized(&channel_id)
                .expect("test audit capacity");
        }
    }

    #[cfg(test)]
    pub(crate) fn stream_credit_test_state(
        &self,
        channel_id: [u8; 16],
        epoch: u64,
    ) -> (bool, bool, Option<u64>, bool) {
        let session_id = self.established_session_id().ok();
        let binding = session_id.and_then(|session_id| {
            let channel = self.admission.channel(&channel_id)?;
            let (channel_generation, revocation_generation) =
                self.admission.credit_generations(&channel_id)?;
            Some(StreamCreditBinding {
                profile: crate::StreamCreditProfile::V1,
                session_id,
                route_id: channel.route_id,
                route_grant_digest: channel.route_grant_digest,
                channel_id,
                channel_generation,
                revocation_generation,
            })
        });
        let bitmap = binding
            .as_ref()
            .and_then(|binding| self.stream_credits.used_bitmap(binding, epoch));
        let pending = matches!(
            &self.state,
            SessionState::Established {
                pending: Some(candidate),
                ..
            } if candidate.channel_id == channel_id
        );
        (
            self.stream_credit_profiles.contains_key(&channel_id),
            session_id
                .is_some_and(|session_id| self.stream_credits.has_channel(session_id, channel_id)),
            bitmap,
            pending,
        )
    }

    pub fn accept_client_hello(&mut self, envelope: &CoreV02Envelope) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        if !matches!(self.state, SessionState::AwaitingClientHello)
            || envelope.message_type() != CoreV02MessageType::ClientHello
        {
            return Err(SessionReject::UnexpectedMessage);
        }
        let hello = envelope
            .client_hello_context()
            .map_err(|_| SessionReject::ControlRejected)?;
        if request_id == [0; 16]
            || session_id == [0; 16]
            || hello.client_nonce == [0; 32]
            || !self.authenticated_peer_matches(&hello.source_edge_id, &hello.destination_edge_id)
            || !self.admission.matches_client_hello(
                &hello.source_operator_id,
                &hello.source_edge_id,
                &hello.destination_operator_id,
                &hello.destination_edge_id,
                &hello.client_session_public_key,
            )
        {
            return Err(SessionReject::ControlRejected);
        }
        self.admission.set_session_id(session_id);
        self.request_ids.insert(request_id);
        self.state = SessionState::AwaitingEdgeHello {
            client_nonce: hello.client_nonce,
            client_session_public_key: hello.client_session_public_key,
            destination_edge_id: hello.destination_edge_id,
            request_id,
            session_id,
            source_edge_id: hello.source_edge_id,
            source_sequence: sequence,
        };
        Ok(())
    }

    pub fn confirm_edge_hello(&mut self, envelope: &CoreV02Envelope) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        let SessionState::AwaitingEdgeHello {
            client_nonce,
            client_session_public_key,
            destination_edge_id,
            request_id: hello_request_id,
            session_id: hello_session_id,
            source_edge_id,
            source_sequence,
        } = &self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        if envelope.message_type() != CoreV02MessageType::EdgeHello {
            return Err(SessionReject::UnexpectedMessage);
        }
        if request_id != *hello_request_id || session_id != *hello_session_id || sequence == 0 {
            return Err(SessionReject::Replay);
        }
        let hello = envelope
            .edge_hello_context()
            .map_err(|_| SessionReject::ControlRejected)?;
        let thumbprint: [u8; 32] = Sha256::digest(client_session_public_key).into();
        if hello.source_edge_id != *source_edge_id
            || hello.destination_edge_id != *destination_edge_id
            || !self.authenticated_peer_matches(&hello.source_edge_id, &hello.destination_edge_id)
            || hello.client_nonce != *client_nonce
            || hello.edge_nonce != self.admission.expected_edge_nonce()
            || hello.client_session_key_thumbprint != thumbprint
        {
            return Err(SessionReject::ControlRejected);
        }
        self.state = SessionState::Established {
            client_nonce: *client_nonce,
            destination_sequence: sequence,
            destination_edge_id: destination_edge_id.clone(),
            edge_nonce: hello.edge_nonce,
            pending: None,
            session_id,
            source_edge_id: source_edge_id.clone(),
            source_sequence: *source_sequence,
        };
        Ok(())
    }

    pub fn accept_route_open(
        &mut self,
        envelope: &CoreV02Envelope,
    ) -> Result<ActiveChannel, SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        let SessionState::Established {
            destination_sequence: _,
            pending,
            session_id: expected_session_id,
            source_sequence,
            ..
        } = &self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        if pending.is_some() {
            return Err(SessionReject::UnexpectedMessage);
        }
        if envelope.message_type() != CoreV02MessageType::RouteOpen {
            return Err(SessionReject::UnexpectedMessage);
        }
        if session_id != *expected_session_id || sequence <= *source_sequence {
            return Err(SessionReject::Replay);
        }
        let channel = self
            .admission
            .admit_route_open(envelope, &self.trusted_issuers, self.clock.unix_seconds())
            .map_err(SessionReject::Admission)?;
        self.request_ids.insert(request_id);
        let SessionState::Established {
            pending,
            source_sequence,
            ..
        } = &mut self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        *source_sequence = sequence;
        *pending = Some(PendingRoute {
            channel_id: channel.channel_id,
            grant_digest: channel.route_grant_digest,
            request_id,
            route_id: channel.route_id,
        });
        Ok(channel)
    }

    pub fn accept_federated_route_open(
        &mut self,
        envelope: &CoreV02Envelope,
        attestations: &LocalFederationAdmissionAttestations,
    ) -> Result<ActiveChannel, SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        let SessionState::Established {
            pending,
            session_id: expected_session_id,
            source_sequence,
            ..
        } = &self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        if pending.is_some() || envelope.message_type() != CoreV02MessageType::RouteOpen {
            return Err(SessionReject::UnexpectedMessage);
        }
        if session_id != *expected_session_id || sequence <= *source_sequence {
            return Err(SessionReject::Replay);
        }
        let channel = self
            .admission
            .admit_federated_route_open(
                envelope,
                &self.trusted_issuers,
                self.clock.unix_seconds(),
                attestations,
            )
            .map_err(SessionReject::Admission)?;
        self.request_ids.insert(request_id);
        let SessionState::Established {
            pending,
            source_sequence,
            ..
        } = &mut self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        *source_sequence = sequence;
        *pending = Some(PendingRoute {
            channel_id: channel.channel_id,
            grant_digest: channel.route_grant_digest,
            request_id,
            route_id: channel.route_id,
        });
        Ok(channel)
    }

    pub fn confirm_route_accept(
        &mut self,
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        let SessionState::Established {
            destination_sequence,
            pending: Some(pending),
            session_id: route_session_id,
            ..
        } = &self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        if envelope.message_type() != CoreV02MessageType::RouteAccept {
            return Err(SessionReject::UnexpectedMessage);
        }
        if request_id != pending.request_id
            || session_id != *route_session_id
            || sequence <= *destination_sequence
        {
            return Err(SessionReject::Replay);
        }
        let binding = envelope
            .route_accept_binding()
            .map_err(|_| SessionReject::ControlRejected)?;
        if binding.channel_id != pending.channel_id
            || binding.route_id != pending.route_id
            || binding.route_grant_digest != pending.grant_digest
        {
            return Err(SessionReject::ControlRejected);
        }
        self.stream_credit_profiles
            .entry(pending.channel_id)
            .or_insert(crate::StreamCreditProfile::Legacy);
        self.admission
            .confirm_channel(&pending.channel_id)
            .map_err(SessionReject::Admission)?;
        let SessionState::Established {
            destination_sequence,
            pending,
            ..
        } = &mut self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        *destination_sequence = sequence;
        *pending = None;
        Ok(())
    }

    /// Selects the authenticated stream-admission profile while the channel is
    /// pending activation. Selection is explicit and never falls back after a
    /// credited session attempt begins.
    pub fn select_stream_credit_profile(
        &mut self,
        channel_id: [u8; 16],
        credits_required: bool,
        peer_profile: Option<&str>,
        explicit_legacy: bool,
    ) -> Result<crate::StreamCreditProfile, SessionReject> {
        self.require_session_active()?;
        let SessionState::Established {
            pending: Some(pending),
            ..
        } = &self.state
        else {
            return Err(SessionReject::InvalidChannelState);
        };
        if pending.channel_id != channel_id || self.stream_credit_profiles.contains_key(&channel_id)
        {
            return Err(SessionReject::InvalidChannelState);
        }
        let profile =
            crate::StreamCreditProfile::select(credits_required, peer_profile, explicit_legacy)
                .map_err(SessionReject::StreamCredit)?;
        self.stream_credit_profiles.insert(channel_id, profile);
        Ok(profile)
    }

    pub(crate) fn rollback_resume_admission(
        &mut self,
        channel_id: [u8; 16],
    ) -> Result<(), ResumeReject> {
        let session_id = self.established_session_id().ok();
        let result = self
            .admission
            .rollback_resume_admission(&channel_id)
            .map_err(|_| ResumeReject::AuditUnavailable);
        self.stream_credit_profiles.remove(&channel_id);
        if let Some(session_id) = session_id {
            self.stream_credits.remove_channel(session_id, channel_id);
        }
        if let SessionState::Established { pending, .. } = &mut self.state
            && pending
                .as_ref()
                .is_some_and(|candidate| candidate.channel_id == channel_id)
        {
            *pending = None;
        }
        result
    }

    pub fn authorize_stream_open(
        &mut self,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        #[cfg(feature = "benchmark-harness")]
        let profile_binding = std::time::Instant::now();
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        let expected_session_id = self.established_session_id()?;
        if session_id != expected_session_id || self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        self.preflight_source_control(sequence)?;
        let channel = self.bound_channel(&channel_id)?.clone();
        #[cfg(feature = "benchmark-harness")]
        if crate::lifecycle_profile::is_destination_role() {
            crate::lifecycle_profile::global().record_ns(
                crate::lifecycle_profile::LifecyclePhase::DestinationBindingReplaySequenceChannel,
                profile_binding.elapsed().as_nanos() as u64,
                true,
            );
        }
        #[cfg(feature = "benchmark-harness")]
        let profile_prepare = std::time::Instant::now();
        let prepared = match self.streams.prepare_open(&channel, envelope) {
            Ok(prepared) => prepared,
            Err(StreamReject::OverCapacity) => {
                self.admission
                    .audit_quota_denial(&channel_id)
                    .map_err(map_admission_audit)?;
                return Err(SessionReject::Stream(StreamReject::OverCapacity));
            }
            Err(error) => return Err(SessionReject::Stream(error)),
        };
        #[cfg(feature = "benchmark-harness")]
        if crate::lifecycle_profile::is_destination_role() {
            crate::lifecycle_profile::global().record_ns(
                crate::lifecycle_profile::LifecyclePhase::DestinationPrepareOpen,
                profile_prepare.elapsed().as_nanos() as u64,
                true,
            );
        }
        #[cfg(feature = "benchmark-harness")]
        let profile_audit = std::time::Instant::now();
        self.admission
            .audit_stream_authorized(&channel_id)
            .map_err(map_admission_audit)?;
        #[cfg(feature = "benchmark-harness")]
        if crate::lifecycle_profile::is_destination_role() {
            crate::lifecycle_profile::global().record_ns(
                crate::lifecycle_profile::LifecyclePhase::DestinationAudit,
                profile_audit.elapsed().as_nanos() as u64,
                true,
            );
        }
        #[cfg(feature = "benchmark-harness")]
        let profile_commit = std::time::Instant::now();
        self.streams.commit_open(prepared);
        self.commit_source_control(request_id, sequence)?;
        #[cfg(feature = "benchmark-harness")]
        if crate::lifecycle_profile::is_destination_role() {
            crate::lifecycle_profile::global().record_ns(
                crate::lifecycle_profile::LifecyclePhase::DestinationReplayStateCommit,
                profile_commit.elapsed().as_nanos() as u64,
                true,
            );
        }
        Ok(())
    }

    pub fn authorize_credited_stream(
        &mut self,
        preface: StreamCreditPreface,
        actual_stream_id: u64,
    ) -> Result<(), SessionReject> {
        let (channel, binding) =
            self.require_credited_stream_authority(&preface, actual_stream_id)?;
        let prepared_credit = self
            .stream_credits
            .prepare_consume(&binding, preface.credit_epoch, preface.credit_slot)
            .map_err(SessionReject::StreamCredit)?;
        let prepared_stream =
            self.prepare_credited_stream_open(&channel, preface.channel_id, actual_stream_id)?;
        self.admission
            .audit_stream_authorized(&preface.channel_id)
            .map_err(map_admission_audit)?;
        self.require_credited_stream_authority(&preface, actual_stream_id)?;
        self.stream_credits
            .commit_consume(prepared_credit)
            .map_err(SessionReject::StreamCredit)?;
        self.streams.commit_open(prepared_stream);
        Ok(())
    }

    pub(crate) fn allocate_credited_stream(
        &mut self,
        channel_id: [u8; 16],
        actual_stream_id: u64,
    ) -> Result<StreamCreditPreface, SessionReject> {
        let (channel, _) = self.require_credited_channel_authority(channel_id)?;
        let prepared_stream =
            self.prepare_credited_stream_open(&channel, channel_id, actual_stream_id)?;
        self.admission
            .audit_stream_authorized(&channel_id)
            .map_err(map_admission_audit)?;
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        let allocation = self
            .stream_credits
            .allocate(&binding)
            .map_err(SessionReject::StreamCredit)?;
        match self.stream_credits.request_refill(&binding) {
            Ok(_)
            | Err(StreamCreditReject::RefillNotDue)
            | Err(StreamCreditReject::RefillPending)
            | Err(StreamCreditReject::EpochExhausted) => {}
            Err(error) => return Err(SessionReject::StreamCredit(error)),
        }
        self.streams.commit_open(prepared_stream);
        Ok(StreamCreditPreface {
            channel_id,
            channel_generation: binding.channel_generation,
            credit_epoch: allocation.credit_epoch,
            credit_slot: allocation.credit_slot,
            quic_stream_id: actual_stream_id,
        })
    }

    pub fn stream_credit_snapshot(
        &self,
        channel_id: [u8; 16],
    ) -> Result<crate::StreamCreditSnapshot, SessionReject> {
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        let window = self
            .stream_credits
            .snapshot(&binding)
            .map_err(SessionReject::StreamCredit)?;
        Ok(crate::StreamCreditSnapshot {
            current_epoch: window.current_epoch,
            draining_epoch: window.draining_epoch,
            remaining_credits: window.remaining_credits,
            pending_refill: window.pending_refill,
            active_epochs: 1 + u8::from(window.draining_epoch.is_some()),
            replay_entries: self.streams.replay_entries(),
            replay_limit: self.streams.replay_limit(),
        })
    }

    pub fn grant_stream_credit_refill(
        &mut self,
        channel_id: [u8; 16],
        epoch: u64,
    ) -> Result<(), SessionReject> {
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        let expected = self
            .stream_credits
            .request_refill(&binding)
            .map_err(SessionReject::StreamCredit)?;
        if expected != epoch {
            self.stream_credits
                .cancel_refill(&binding)
                .map_err(SessionReject::StreamCredit)?;
            return Err(SessionReject::StreamCredit(
                StreamCreditReject::InvalidState,
            ));
        }
        self.stream_credits
            .activate_refill(&binding, epoch)
            .map_err(SessionReject::StreamCredit)
    }

    pub fn confirm_stream_credit_refill(
        &mut self,
        channel_id: [u8; 16],
        epoch: u64,
    ) -> Result<(), SessionReject> {
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        self.stream_credits
            .activate_refill(&binding, epoch)
            .map_err(SessionReject::StreamCredit)
    }

    pub fn cancel_stream_credit_refill(
        &mut self,
        channel_id: [u8; 16],
    ) -> Result<(), SessionReject> {
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        self.stream_credits
            .cancel_refill(&binding)
            .map_err(SessionReject::StreamCredit)
    }

    pub fn retire_stream_credit_epoch(
        &mut self,
        channel_id: [u8; 16],
        epoch: u64,
    ) -> Result<(), SessionReject> {
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        self.stream_credits
            .retire(&binding, epoch)
            .map_err(SessionReject::StreamCredit)
    }

    pub(crate) fn credited_stream_context(
        &self,
        channel_id: [u8; 16],
        actual_stream_id: u64,
    ) -> Result<StreamCreditContext, SessionReject> {
        let (_, binding) = self.require_credited_channel_authority(channel_id)?;
        Ok(StreamCreditContext {
            session_id: binding.session_id,
            authenticated_session_id: binding.session_id,
            channel_id,
            channel_generation: binding.channel_generation,
            quic_stream_id: actual_stream_id,
        })
    }

    fn prepare_credited_stream_open(
        &mut self,
        channel: &ActiveChannel,
        channel_id: [u8; 16],
        actual_stream_id: u64,
    ) -> Result<PreparedStreamOpen, SessionReject> {
        match self.streams.prepare_credited(channel, actual_stream_id) {
            Ok(prepared) => Ok(prepared),
            Err(CreditedStreamReject::InvalidStream) => {
                Err(SessionReject::StreamCredit(StreamCreditReject::WrongStream))
            }
            Err(CreditedStreamReject::DuplicateStream) => Err(SessionReject::StreamCredit(
                StreamCreditReject::DuplicateStream,
            )),
            Err(CreditedStreamReject::OverCapacity) => {
                self.admission
                    .audit_quota_denial(&channel_id)
                    .map_err(map_admission_audit)?;
                Err(SessionReject::StreamCredit(
                    StreamCreditReject::OverCapacity,
                ))
            }
            Err(CreditedStreamReject::ReplayCapacity) => {
                self.admission
                    .audit_quota_denial(&channel_id)
                    .map_err(map_admission_audit)?;
                Err(SessionReject::StreamCredit(
                    StreamCreditReject::ReplayCapacity,
                ))
            }
        }
    }

    fn require_credited_stream_authority(
        &self,
        preface: &StreamCreditPreface,
        actual_stream_id: u64,
    ) -> Result<(ActiveChannel, StreamCreditBinding), SessionReject> {
        if preface.quic_stream_id != actual_stream_id {
            return Err(SessionReject::StreamCredit(StreamCreditReject::WrongStream));
        }
        let (channel, binding) = self.require_credited_channel_authority(preface.channel_id)?;
        if preface.channel_generation != binding.channel_generation {
            return Err(SessionReject::StreamCredit(
                StreamCreditReject::WrongGeneration,
            ));
        }
        Ok((channel, binding))
    }

    fn require_credited_channel_authority(
        &self,
        channel_id: [u8; 16],
    ) -> Result<(ActiveChannel, StreamCreditBinding), SessionReject> {
        self.require_session_active()?;
        let session_id = self.established_session_id()?;
        let channel = self.bound_channel(&channel_id)?.clone();
        if self.stream_credit_profiles.get(&channel_id) != Some(&crate::StreamCreditProfile::V1) {
            return Err(SessionReject::StreamCredit(
                StreamCreditReject::ProfileUnsupported,
            ));
        }
        if !self
            .admission
            .credit_grant_is_live(&channel_id, self.clock.unix_seconds())
        {
            return Err(SessionReject::StreamCredit(StreamCreditReject::Expired));
        }
        let (channel_generation, revocation_generation) = self
            .admission
            .credit_generations(&channel_id)
            .ok_or(SessionReject::StreamCredit(
                StreamCreditReject::WrongChannel,
            ))?;
        let binding = StreamCreditBinding {
            profile: crate::StreamCreditProfile::V1,
            session_id,
            route_id: channel.route_id,
            route_grant_digest: channel.route_grant_digest,
            channel_id: channel.channel_id,
            channel_generation,
            revocation_generation,
        };
        Ok((channel, binding))
    }

    pub fn confirm_stream_accept(
        &mut self,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if request_id == [0; 16] || session_id != self.established_session_id()? {
            return Err(SessionReject::Replay);
        }
        self.preflight_destination_control(sequence)?;
        self.bound_channel(&channel_id)?;
        let prepared = self
            .streams
            .prepare_accept(&channel_id, envelope)
            .map_err(SessionReject::Stream)?;
        self.admission
            .audit_stream_authorized(&channel_id)
            .map_err(map_admission_audit)?;
        self.streams.commit_transition(prepared);
        self.commit_destination_control(sequence)?;
        Ok(())
    }

    pub fn reserve_stream_bytes(
        &mut self,
        channel_id: [u8; 16],
        stream_id: u64,
        bytes: usize,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        self.require_bound_channel(&channel_id)?;
        match self.streams.reserve_bytes(&channel_id, stream_id, bytes) {
            Err(StreamReject::OverCapacity) => {
                self.admission
                    .audit_quota_denial(&channel_id)
                    .map_err(map_admission_audit)?;
                Err(SessionReject::Stream(StreamReject::OverCapacity))
            }
            result => result.map_err(SessionReject::Stream),
        }
    }

    pub fn release_stream_bytes(
        &mut self,
        channel_id: [u8; 16],
        stream_id: u64,
        bytes: usize,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        self.require_existing_bound_channel(&channel_id)?;
        self.streams
            .release_bytes(&channel_id, stream_id, bytes)
            .map_err(SessionReject::Stream)
    }

    pub fn release_stream(
        &mut self,
        channel_id: [u8; 16],
        stream_id: u64,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        self.require_existing_bound_channel(&channel_id)?;
        self.streams
            .release_stream(&channel_id, stream_id)
            .map_err(SessionReject::Stream)
    }

    /// Removes only an ordinary live-stream entry during terminal transport
    /// cleanup. Credit consumption and P1F replay history remain unchanged.
    /// This intentionally bypasses active-session/channel checks so an aborted
    /// admission can clean up after expiry, drain, close, or revoke.
    pub(crate) fn release_credited_stream_terminal(
        &mut self,
        channel_id: [u8; 16],
        stream_id: u64,
    ) -> bool {
        self.streams.release_stream(&channel_id, stream_id).is_ok()
    }

    pub(crate) fn authorize_application_stream(
        &mut self,
        channel_id: [u8; 16],
        actual_stream_id: u64,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        self.require_bound_channel(&channel_id)?;
        let prepared = self
            .streams
            .prepare_application_stream(&channel_id, actual_stream_id)
            .map_err(SessionReject::Stream)?;
        self.admission
            .audit_stream_authorized(&channel_id)
            .map_err(map_admission_audit)?;
        self.streams.commit_transition(prepared);
        Ok(())
    }

    pub fn application_stream_permit(
        &self,
        channel_id: [u8; 16],
        stream_id: u64,
    ) -> Result<crate::ApplicationStreamPermit, SessionReject> {
        self.require_session_active()?;
        self.require_bound_channel(&channel_id)?;
        self.streams
            .validate_application_stream(&channel_id, stream_id)
            .map_err(SessionReject::Stream)?;
        Ok(crate::ApplicationStreamPermit::new(
            self.connection_capability.clone(),
            channel_id,
            stream_id,
        ))
    }

    pub(crate) fn revoke_channel(
        &mut self,
        channel_id: [u8; 16],
        revoked_at: u64,
    ) -> Result<(), SessionReject> {
        self.admission
            .revoke_channel(&channel_id, revoked_at)
            .map_err(map_lifecycle)?;
        self.streams.revoke_channel(&channel_id);
        if let Ok(session_id) = self.established_session_id() {
            self.stream_credits.remove_channel(session_id, channel_id);
        }
        self.stream_credit_profiles.remove(&channel_id);
        if let Some(gate) = self.datagrams.get_mut(&channel_id) {
            gate.deactivate();
        }
        Ok(())
    }

    pub fn accept_route_drain(
        &mut self,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
        monotonic_now: u64,
        unix_now: u64,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        let expected_session_id = self.established_session_id()?;
        let source_sequence = match &self.state {
            SessionState::Established {
                source_sequence, ..
            } => *source_sequence,
            _ => return Err(SessionReject::UnexpectedMessage),
        };
        if request_id == [0; 16]
            || session_id != expected_session_id
            || sequence <= source_sequence
            || envelope.message_type() != CoreV02MessageType::RouteDrain
        {
            return Err(SessionReject::Replay);
        }
        let body = envelope
            .route_drain_body()
            .map_err(|_| SessionReject::ControlRejected)?;
        self.require_lifecycle_binding(
            channel_id,
            body.channel_id,
            body.route_id,
            body.route_grant_digest,
        )?;
        let requested = DrainDeadline::new(monotonic_now, body.drain_seconds)
            .map_err(|_| SessionReject::ControlRejected)?;
        self.admission
            .start_channel_drain(
                &channel_id,
                requested,
                monotonic_now,
                unix_now,
                self.session_deadline,
            )
            .map_err(map_lifecycle)?;
        if let Some(gate) = self.datagrams.get_mut(&channel_id) {
            gate.deactivate();
        }
        self.commit_source_control(request_id, sequence)?;
        Ok(())
    }

    pub(crate) fn accept_route_revoke(
        &mut self,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        let expected_session_id = self.established_session_id()?;
        let source_sequence = match &self.state {
            SessionState::Established {
                source_sequence, ..
            } => *source_sequence,
            _ => return Err(SessionReject::UnexpectedMessage),
        };
        if request_id == [0; 16]
            || session_id != expected_session_id
            || sequence <= source_sequence
            || envelope.message_type() != CoreV02MessageType::RouteRevoke
        {
            return Err(SessionReject::Replay);
        }
        let body = envelope
            .route_revoke_body()
            .map_err(|_| SessionReject::ControlRejected)?;
        self.require_lifecycle_binding(
            channel_id,
            body.channel_id,
            body.route_id,
            body.route_grant_digest,
        )?;
        self.revoke_channel(channel_id, body.revoked_at)?;
        self.commit_source_control(request_id, sequence)
    }

    pub(crate) fn accept_route_close(
        &mut self,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        let expected_session_id = self.established_session_id()?;
        let source_sequence = match &self.state {
            SessionState::Established {
                source_sequence, ..
            } => *source_sequence,
            _ => return Err(SessionReject::UnexpectedMessage),
        };
        if request_id == [0; 16]
            || session_id != expected_session_id
            || sequence <= source_sequence
            || envelope.message_type() != CoreV02MessageType::RouteClose
        {
            return Err(SessionReject::Replay);
        }
        let body = envelope
            .route_close_body()
            .map_err(|_| SessionReject::ControlRejected)?;
        self.require_lifecycle_binding(
            channel_id,
            body.channel_id,
            body.route_id,
            body.route_grant_digest,
        )?;
        self.close_channel(channel_id, body.closed_at)?;
        self.commit_source_control(request_id, sequence)
    }

    pub(crate) fn enforce_channel_drain(
        &mut self,
        channel_id: [u8; 16],
        monotonic_now: u64,
    ) -> Result<DrainEnforcement, SessionReject> {
        let deadline = self
            .admission
            .channel_drain_deadline(&channel_id)
            .ok_or(SessionReject::InvalidChannelState)?;
        if !deadline.is_due(monotonic_now) {
            return Ok(DrainEnforcement::Pending);
        }
        match self.admission.finish_channel_drain(&channel_id) {
            Ok(()) => {
                self.streams.revoke_channel(&channel_id);
                if let Ok(session_id) = self.established_session_id() {
                    self.stream_credits.remove_channel(session_id, channel_id);
                }
                self.stream_credit_profiles.remove(&channel_id);
                if let Some(gate) = self.datagrams.get_mut(&channel_id) {
                    gate.deactivate();
                }
                Ok(DrainEnforcement::Enforced {
                    audit_integrity: AuditIntegrity::Recorded,
                })
            }
            Err(ChannelLifecycleError::AuditUnavailable) => {
                if let Some(gate) = self.datagrams.get_mut(&channel_id) {
                    gate.deactivate();
                }
                Ok(DrainEnforcement::Enforced {
                    audit_integrity: AuditIntegrity::Failed,
                })
            }
            Err(error) => Err(map_lifecycle(error)),
        }
    }

    pub(crate) fn close_channel(
        &mut self,
        channel_id: [u8; 16],
        closed_at: u64,
    ) -> Result<(), SessionReject> {
        self.admission
            .close_live_channel(&channel_id, closed_at)
            .map_err(map_lifecycle)?;
        self.streams.revoke_channel(&channel_id);
        if let Ok(session_id) = self.established_session_id() {
            self.stream_credits.remove_channel(session_id, channel_id);
        }
        self.stream_credit_profiles.remove(&channel_id);
        if let Some(gate) = self.datagrams.get_mut(&channel_id) {
            gate.deactivate();
        }
        Ok(())
    }

    pub(crate) fn resume_scope(&self) -> Result<ResumeSessionScope, ResumeReject> {
        let SessionState::Established {
            destination_edge_id,
            session_id,
            source_edge_id,
            ..
        } = &self.state
        else {
            return Err(ResumeReject::Ineligible);
        };
        if self.session_drain_state != SessionDrainState::Active {
            return Err(ResumeReject::Ineligible);
        }
        if self.session_expired() {
            return Err(ResumeReject::Expired);
        }
        Ok(ResumeSessionScope {
            reuse_key: ResumeReuseKey {
                source_edge_id: source_edge_id.clone(),
                destination_edge_id: destination_edge_id.clone(),
                trust_profile_id: self.trust_profile_id.clone(),
                alpn: self.negotiated_alpn.clone(),
                protocol_version: 2,
            },
            authenticated_peer: self.authenticated_peer.as_str().to_owned(),
            connection_capability: self.connection_capability.clone(),
            local_role: self.local_role,
            session_id: *session_id,
        })
    }

    pub(crate) fn require_resume_authority(&self) -> Result<(), ResumeReject> {
        if self.session_expired() {
            Err(ResumeReject::Expired)
        } else if self.session_drain_state != SessionDrainState::Active {
            Err(ResumeReject::Ineligible)
        } else {
            Ok(())
        }
    }

    pub(crate) fn closed_resume_context(
        &self,
        channel_id: [u8; 16],
    ) -> Result<ResumeSessionContext, ResumeReject> {
        let channel = self
            .admission
            .closed_resume_context(&channel_id)
            .ok_or(ResumeReject::Ineligible)?;
        self.resume_context(channel)
    }

    pub(crate) fn bound_resume_context(
        &self,
        channel_id: [u8; 16],
    ) -> Result<ResumeSessionContext, ResumeReject> {
        let channel = self
            .admission
            .bound_resume_context(&channel_id)
            .ok_or(ResumeReject::Ineligible)?;
        self.resume_context(channel)
    }

    fn resume_context(
        &self,
        channel: ResumeChannelContext,
    ) -> Result<ResumeSessionContext, ResumeReject> {
        let SessionState::Established {
            client_nonce,
            destination_edge_id,
            edge_nonce,
            session_id,
            source_edge_id,
            ..
        } = &self.state
        else {
            return Err(ResumeReject::Ineligible);
        };
        if self.session_drain_state != SessionDrainState::Active {
            return Err(ResumeReject::Ineligible);
        }
        Ok(ResumeSessionContext {
            reuse_key: ResumeReuseKey {
                source_edge_id: source_edge_id.clone(),
                destination_edge_id: destination_edge_id.clone(),
                trust_profile_id: self.trust_profile_id.clone(),
                alpn: self.negotiated_alpn.clone(),
                protocol_version: 2,
            },
            authenticated_peer: self.authenticated_peer.as_str().to_owned(),
            channel,
            client_nonce: *client_nonce,
            connection_capability: self.connection_capability.clone(),
            edge_nonce: *edge_nonce,
            local_role: self.local_role,
            hard_session_deadline: self.hard_session_deadline,
            session_deadline: self.session_deadline.map(DrainDeadline::monotonic_seconds),
            session_id: *session_id,
        })
    }

    pub(crate) fn audit_resume_issue(
        &mut self,
        context: &ResumeSessionContext,
    ) -> Result<(), ResumeReject> {
        self.audit_resume(
            context.channel.channel.channel_id,
            &context.channel.channel.service_id,
            AuditAction::ResumeIssued,
        )
    }

    pub(crate) fn audit_resume_consume(
        &mut self,
        context: &ResumeSessionContext,
    ) -> Result<(), ResumeReject> {
        self.audit_resume(
            context.channel.channel.channel_id,
            &context.channel.channel.service_id,
            AuditAction::ResumeConsumed,
        )
    }

    pub(crate) fn audit_resume_purge(&mut self) -> Result<(), ResumeReject> {
        self.admission
            .audit_resume(
                None,
                "transport-resume",
                AuditAction::ResumePurged,
                AuditOutcome::Allowed,
                AuditReason::Expired,
            )
            .map_err(|_| ResumeReject::AuditUnavailable)
    }

    pub(crate) fn audit_resume_preflight(
        &mut self,
        context: &ResumeSessionContext,
    ) -> Result<(), ResumeReject> {
        self.audit_resume(
            context.channel.channel.channel_id,
            &context.channel.channel.service_id,
            AuditAction::ResumePreflightIssued,
        )
    }

    pub(crate) fn audit_resume_reject(
        &mut self,
        channel_id: [u8; 16],
        service_id: &str,
        reason: AuditReason,
    ) -> Result<(), ResumeReject> {
        self.admission
            .audit_resume(
                Some(channel_id),
                service_id,
                AuditAction::ResumeRejected,
                AuditOutcome::Denied,
                reason,
            )
            .map_err(|_| ResumeReject::AuditUnavailable)
    }

    pub(crate) fn audit_resume_session_reject(
        &mut self,
        channel_id: Option<[u8; 16]>,
        reason: AuditReason,
    ) -> Result<(), ResumeReject> {
        self.admission
            .audit_resume(
                channel_id,
                "transport-resume",
                AuditAction::ResumeRejected,
                AuditOutcome::Denied,
                reason,
            )
            .map_err(|_| ResumeReject::AuditUnavailable)
    }

    fn audit_resume(
        &mut self,
        channel_id: [u8; 16],
        service_id: &str,
        action: AuditAction,
    ) -> Result<(), ResumeReject> {
        self.admission
            .audit_resume(
                Some(channel_id),
                service_id,
                action,
                AuditOutcome::Allowed,
                AuditReason::None,
            )
            .map_err(|_| ResumeReject::AuditUnavailable)
    }

    fn established_session_id(&self) -> Result<[u8; 16], SessionReject> {
        let SessionState::Established { session_id, .. } = &self.state else {
            return Err(SessionReject::UnexpectedMessage);
        };
        Ok(*session_id)
    }

    pub(crate) fn channel_binding_request(
        &self,
        channel_id: [u8; 16],
    ) -> Result<ChannelBindingRequest, SessionReject> {
        self.require_session_active()?;
        let SessionState::Established {
            client_nonce,
            destination_edge_id,
            edge_nonce,
            session_id,
            source_edge_id,
            ..
        } = &self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        let channel = self
            .admission
            .channel(&channel_id)
            .ok_or_else(|| self.inactive_channel_reject(&channel_id))?;
        let policy_hash = self
            .admission
            .policy_hash(&channel.service_id)
            .ok_or(SessionReject::ChannelBindingFailed)?;
        Ok(ChannelBindingRequest {
            session_id: *session_id,
            source_edge_id: source_edge_id.clone(),
            destination_edge_id: destination_edge_id.clone(),
            channel_id: channel.channel_id,
            route_id: channel.route_id,
            route_grant_digest: channel.route_grant_digest,
            service_id: channel.service_id.clone(),
            transport: channel.transport.clone(),
            port: channel.port,
            policy_hash,
            client_nonce: *client_nonce,
            edge_nonce: *edge_nonce,
        })
    }

    pub(crate) fn matches_connection(&self, capability: &ConnectionBindingCapability) -> bool {
        self.connection_capability.matches(capability)
    }

    pub(crate) fn install_channel_binding(
        &mut self,
        channel_id: [u8; 16],
        binding: ChannelBinding,
    ) -> Result<(), SessionReject> {
        self.require_session_active()?;
        self.admission
            .install_binding(&channel_id, binding)
            .map_err(|error| match error {
                ChannelBindingInstallError::AuditUnavailable => SessionReject::AuditUnavailable,
                ChannelBindingInstallError::InvalidState => SessionReject::InvalidChannelState,
                ChannelBindingInstallError::UnknownChannel
                | ChannelBindingInstallError::Mismatch => SessionReject::ChannelBindingFailed,
            })?;
        let session_id = self.established_session_id()?;
        if self.stream_credit_profiles.get(&channel_id) == Some(&crate::StreamCreditProfile::V1)
            && !self.stream_credits.has_channel(session_id, channel_id)
        {
            let channel = self.bound_channel(&channel_id)?.clone();
            let generations = self
                .admission
                .credit_generations(&channel_id)
                .ok_or(SessionReject::InvalidChannelState)?;
            self.stream_credits
                .activate(StreamCreditBinding {
                    profile: crate::StreamCreditProfile::V1,
                    session_id,
                    route_id: channel.route_id,
                    route_grant_digest: channel.route_grant_digest,
                    channel_id,
                    channel_generation: generations.0,
                    revocation_generation: generations.1,
                })
                .map_err(SessionReject::StreamCredit)?;
        }
        if self.admission.bound_udp_channel(&channel_id).is_some() {
            self.datagrams
                .entry(channel_id)
                .or_insert_with(|| crate::DatagramGate::new(channel_id));
        }
        Ok(())
    }

    pub(crate) fn udp_payload_capacity(
        &self,
        channel_id: [u8; 16],
        peer_maximum: usize,
    ) -> Result<usize, crate::DatagramReject> {
        self.require_udp_channel(&channel_id)?;
        self.datagrams
            .get(&channel_id)
            .ok_or(crate::DatagramReject::InvalidState)?
            .payload_capacity(peer_maximum)
    }

    pub(crate) fn send_udp_datagram(
        &mut self,
        channel_id: [u8; 16],
        payload: &[u8],
        peer_maximum: usize,
        monotonic_milliseconds: u64,
    ) -> Result<Vec<u8>, crate::DatagramReject> {
        self.require_udp_channel(&channel_id)?;
        let (admission, datagrams) = (&mut self.admission, &mut self.datagrams);
        let gate = datagrams
            .get_mut(&channel_id)
            .ok_or(crate::DatagramReject::InvalidState)?;
        gate.send(payload, peer_maximum, monotonic_milliseconds, |mutation| {
            admission
                .audit_datagram_mutation(&channel_id, mutation)
                .map_err(|_| ())
        })
    }

    pub(crate) fn receive_udp_datagram(
        &mut self,
        frame: crate::DatagramFrame,
        monotonic_milliseconds: u64,
    ) -> Result<crate::DatagramReceive, crate::DatagramReject> {
        let channel_id = frame.channel_id();
        self.require_udp_channel(&channel_id)?;
        let (admission, datagrams) = (&mut self.admission, &mut self.datagrams);
        let gate = datagrams
            .get_mut(&channel_id)
            .ok_or(crate::DatagramReject::InvalidState)?;
        gate.receive(frame, monotonic_milliseconds, |mutation| {
            admission
                .audit_datagram_mutation(&channel_id, mutation)
                .map_err(|_| ())
        })
    }

    pub(crate) fn pop_udp_datagram(
        &mut self,
        channel_id: [u8; 16],
    ) -> Result<Option<Vec<u8>>, crate::DatagramReject> {
        self.require_udp_channel(&channel_id)?;
        let (admission, datagrams) = (&mut self.admission, &mut self.datagrams);
        let gate = datagrams
            .get_mut(&channel_id)
            .ok_or(crate::DatagramReject::InvalidState)?;
        gate.pop(|mutation| {
            admission
                .audit_datagram_mutation(&channel_id, mutation)
                .map_err(|_| ())
        })
    }

    fn require_udp_channel(&self, channel_id: &[u8; 16]) -> Result<(), crate::DatagramReject> {
        if self.session_drain_state != SessionDrainState::Active || self.session_expired() {
            return Err(crate::DatagramReject::InvalidState);
        }
        self.admission
            .bound_udp_channel(channel_id)
            .ok_or(crate::DatagramReject::InvalidState)?;
        Ok(())
    }

    fn require_bound_channel(&self, channel_id: &[u8; 16]) -> Result<(), SessionReject> {
        if self.admission.bound_channel(channel_id).is_some() {
            Ok(())
        } else if self.admission.channel(channel_id).is_some() {
            Err(SessionReject::ChannelBindingRequired)
        } else {
            Err(self.inactive_channel_reject(channel_id))
        }
    }

    fn require_session_active(&self) -> Result<(), SessionReject> {
        if self.session_drain_state == SessionDrainState::Active && !self.session_expired() {
            Ok(())
        } else {
            Err(SessionReject::InvalidChannelState)
        }
    }

    pub(crate) fn session_expired(&self) -> bool {
        let now = self.clock.monotonic_seconds();
        now >= self.hard_session_deadline
            || now.saturating_sub(self.created_at_monotonic) >= MAX_SESSION_SECONDS
            || self
                .session_deadline
                .is_some_and(|deadline| deadline.is_due(now))
    }

    fn preflight_source_control(&self, sequence: u64) -> Result<(), SessionReject> {
        match &self.state {
            SessionState::Established {
                source_sequence, ..
            } if sequence > *source_sequence => Ok(()),
            SessionState::Established { .. } => Err(SessionReject::Replay),
            _ => Err(SessionReject::UnexpectedMessage),
        }
    }

    fn preflight_destination_control(&self, sequence: u64) -> Result<(), SessionReject> {
        match &self.state {
            SessionState::Established {
                destination_sequence,
                ..
            } if sequence > *destination_sequence => Ok(()),
            SessionState::Established { .. } => Err(SessionReject::Replay),
            _ => Err(SessionReject::UnexpectedMessage),
        }
    }

    fn commit_destination_control(&mut self, sequence: u64) -> Result<(), SessionReject> {
        let SessionState::Established {
            destination_sequence,
            ..
        } = &mut self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        *destination_sequence = sequence;
        Ok(())
    }

    fn require_existing_bound_channel(&self, channel_id: &[u8; 16]) -> Result<(), SessionReject> {
        if self.admission.bound_existing_channel(channel_id).is_some() {
            Ok(())
        } else {
            Err(self.inactive_channel_reject(channel_id))
        }
    }

    fn require_lifecycle_binding(
        &self,
        channel_id: [u8; 16],
        body_channel_id: [u8; 16],
        route_id: [u8; 16],
        route_grant_digest: [u8; 32],
    ) -> Result<(), SessionReject> {
        let channel = self
            .admission
            .lifecycle_channel(&channel_id)
            .ok_or_else(|| self.inactive_channel_reject(&channel_id))?;
        if body_channel_id != channel_id
            || route_id != channel.route_id
            || route_grant_digest != channel.route_grant_digest
        {
            return Err(SessionReject::ControlRejected);
        }
        Ok(())
    }

    fn commit_source_control(
        &mut self,
        request_id: [u8; 16],
        sequence: u64,
    ) -> Result<(), SessionReject> {
        let SessionState::Established {
            source_sequence, ..
        } = &mut self.state
        else {
            return Err(SessionReject::UnexpectedMessage);
        };
        self.request_ids.insert(request_id);
        *source_sequence = sequence;
        Ok(())
    }

    fn bound_channel(&self, channel_id: &[u8; 16]) -> Result<&ActiveChannel, SessionReject> {
        if let Some(channel) = self.admission.bound_channel(channel_id) {
            Ok(channel)
        } else if self.admission.channel(channel_id).is_some() {
            Err(SessionReject::ChannelBindingRequired)
        } else {
            Err(self.inactive_channel_reject(channel_id))
        }
    }

    fn inactive_channel_reject(&self, channel_id: &[u8; 16]) -> SessionReject {
        match self.admission.channel_state(*channel_id) {
            Some(ChannelState::Revoked | ChannelState::Closed | ChannelState::Draining) => {
                SessionReject::InvalidChannelState
            }
            Some(ChannelState::Candidate) | Some(ChannelState::Active) | None => {
                SessionReject::UnexpectedMessage
            }
        }
    }

    fn authenticated_peer_matches(&self, source_edge_id: &str, destination_edge_id: &str) -> bool {
        match self.local_role {
            EdgeRole::Source => self.authenticated_peer.as_str() == destination_edge_id,
            EdgeRole::Destination => self.authenticated_peer.as_str() == source_edge_id,
        }
    }
}

impl Drop for ControlSession {
    fn drop(&mut self) {
        crate::diagnostics::global()
            .completed(crate::diagnostics::DiagnosticOwner::TransportSession);
    }
}

fn map_admission_audit(error: AdmissionReject) -> SessionReject {
    match error {
        AdmissionReject::AuditUnavailable => SessionReject::AuditUnavailable,
        other => SessionReject::Admission(other),
    }
}

fn map_lifecycle(error: ChannelLifecycleError) -> SessionReject {
    match error {
        ChannelLifecycleError::AuditUnavailable => SessionReject::AuditUnavailable,
        ChannelLifecycleError::InvalidState => SessionReject::InvalidChannelState,
        ChannelLifecycleError::UnknownChannel => SessionReject::UnexpectedMessage,
    }
}

fn binding(envelope: &CoreV02Envelope) -> Result<([u8; 16], [u8; 16], u64), SessionReject> {
    envelope
        .session_binding()
        .map_err(|_| SessionReject::ControlRejected)
}
