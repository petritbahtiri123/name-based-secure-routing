//! Origin-free control-session sequencing and reusable route admission.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Instant;

use sha2::{Digest, Sha256};

use crate::channel_binding::ChannelBindingRequest;
use crate::channel_registry::{
    ChannelBindingInstallError, ChannelLifecycleError, ResumeChannelContext,
};
use crate::channel_streams::ChannelStreams;
use crate::quinn_adapter::ConnectionBindingCapability;
use crate::resumption::{ResumeReuseKey, ResumeSessionContext, ResumeSessionScope};
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
impl SessionClock for AnchoredClock {
    fn unix_seconds(&self) -> u64 {
        self.unix_anchor
            .saturating_add(self.started.elapsed().as_secs())
    }
    fn monotonic_seconds(&self) -> u64 {
        self.started.elapsed().as_secs()
    }
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
    session_deadline: Option<DrainDeadline>,
    hard_session_deadline: u64,
    session_drain_state: SessionDrainState,
    session_drain_deadline: Option<DrainDeadline>,
    trust_profile_id: TrustProfileId,
    clock: Arc<dyn SessionClock>,
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
        )
    }

    fn new_inner(
        connection: &AuthenticatedConnection,
        admission: DestinationAdmission,
        trusted_issuers: Vec<RouteGrantIssuer>,
        trust_profile_id: TrustProfileId,
        clock: Arc<dyn SessionClock>,
        session_deadline: Option<DrainDeadline>,
    ) -> Self {
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
            streams: ChannelStreams::new(),
            session_deadline,
            hard_session_deadline: clock
                .monotonic_seconds()
                .saturating_add(MAX_SESSION_SECONDS),
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

    pub(crate) fn rollback_resume_admission(
        &mut self,
        channel_id: [u8; 16],
    ) -> Result<(), ResumeReject> {
        let result = self
            .admission
            .rollback_resume_admission(&channel_id)
            .map_err(|_| ResumeReject::AuditUnavailable);
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
        self.require_session_active()?;
        let (request_id, session_id, sequence) = binding(envelope)?;
        let expected_session_id = self.established_session_id()?;
        if session_id != expected_session_id || self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        self.preflight_source_control(sequence)?;
        let channel = self.bound_channel(&channel_id)?.clone();
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
        self.admission
            .audit_stream_authorized(&channel_id)
            .map_err(map_admission_audit)?;
        self.streams.commit_open(prepared);
        self.commit_source_control(request_id, sequence)?;
        Ok(())
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

    fn session_expired(&self) -> bool {
        let now = self.clock.monotonic_seconds();
        now >= self.hard_session_deadline
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
