//! Origin-free control-session sequencing and reusable route admission.

use std::collections::HashSet;

use sha2::{Digest, Sha256};

use crate::{
    ActiveChannel, AdmissionReject, AuthenticatedConnection, CoreV02Envelope, CoreV02MessageType,
    DestinationAdmission, EdgeIdentity, RouteGrantIssuer, StreamGate,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionReject {
    Admission(AdmissionReject),
    ControlRejected,
    Replay,
    UnexpectedMessage,
}

pub struct ControlSession {
    admission: DestinationAdmission,
    authenticated_peer: EdgeIdentity,
    trusted_issuers: Vec<RouteGrantIssuer>,
    state: SessionState,
    request_ids: HashSet<[u8; 16]>,
}

enum SessionState {
    AwaitingClientHello,
    AwaitingEdgeHello {
        client_nonce: [u8; 32],
        client_session_public_key: [u8; 32],
        destination_edge_id: String,
        request_id: [u8; 16],
        session_id: [u8; 16],
        source_sequence: u64,
    },
    Established {
        destination_sequence: u64,
        pending: Option<PendingRoute>,
        session_id: [u8; 16],
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
    ) -> Self {
        Self {
            admission,
            authenticated_peer: connection.authenticated_peer().clone(),
            trusted_issuers,
            state: SessionState::AwaitingClientHello,
            request_ids: HashSet::new(),
        }
    }

    pub fn active_channels(&self) -> usize {
        self.admission.active_channels()
    }

    pub fn accept_client_hello(&mut self, envelope: &CoreV02Envelope) -> Result<(), SessionReject> {
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
            || hello.source_edge_id != self.authenticated_peer.as_str()
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
        self.request_ids.insert(request_id);
        self.state = SessionState::AwaitingEdgeHello {
            client_nonce: hello.client_nonce,
            client_session_public_key: hello.client_session_public_key,
            destination_edge_id: hello.destination_edge_id,
            request_id,
            session_id,
            source_sequence: sequence,
        };
        Ok(())
    }

    pub fn confirm_edge_hello(&mut self, envelope: &CoreV02Envelope) -> Result<(), SessionReject> {
        let (request_id, session_id, sequence) = binding(envelope)?;
        let SessionState::AwaitingEdgeHello {
            client_nonce,
            client_session_public_key,
            destination_edge_id,
            request_id: hello_request_id,
            session_id: hello_session_id,
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
        if hello.source_edge_id != self.authenticated_peer.as_str()
            || hello.destination_edge_id != *destination_edge_id
            || hello.client_nonce != *client_nonce
            || hello.edge_nonce != self.admission.expected_edge_nonce()
            || hello.client_session_key_thumbprint != thumbprint
        {
            return Err(SessionReject::ControlRejected);
        }
        self.state = SessionState::Established {
            destination_sequence: sequence,
            pending: None,
            session_id,
            source_sequence: *source_sequence,
        };
        Ok(())
    }

    pub fn accept_route_open(
        &mut self,
        envelope: &CoreV02Envelope,
    ) -> Result<ActiveChannel, SessionReject> {
        let (request_id, session_id, sequence) = binding(envelope)?;
        if self.request_ids.contains(&request_id) {
            return Err(SessionReject::Replay);
        }
        let SessionState::Established {
            destination_sequence: _,
            pending,
            session_id: expected_session_id,
            source_sequence,
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
            .admit_route_open(envelope, &self.trusted_issuers)
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

    pub fn stream_gate(&self, channel_id: [u8; 16]) -> Result<StreamGate, SessionReject> {
        self.admission
            .channel(&channel_id)
            .cloned()
            .map(StreamGate::new)
            .ok_or(SessionReject::UnexpectedMessage)
    }
}

fn binding(envelope: &CoreV02Envelope) -> Result<([u8; 16], [u8; 16], u64), SessionReject> {
    envelope
        .session_binding()
        .map_err(|_| SessionReject::ControlRejected)
}
