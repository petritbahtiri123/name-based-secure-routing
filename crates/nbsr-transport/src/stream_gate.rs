//! Single-service application-stream admission for the WP3 loopback profile.

use crate::{ActiveChannel, CoreV02Envelope};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StreamReject {
    ChannelMismatch,
    ControlRejected,
    DuplicateStream,
    OverCapacity,
    RouteMismatch,
    UnsupportedTransport,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StreamOpenRequest {
    pub quic_stream_id: u64,
    pub channel_id: [u8; 16],
    pub route_id: [u8; 16],
    pub route_grant_digest: [u8; 32],
    pub transport: String,
    pub port: u16,
}

#[derive(Clone)]
pub(crate) struct StreamGate {
    channel: ActiveChannel,
    state: StreamGateState,
}

#[derive(Clone)]
enum StreamGateState {
    AwaitingOpen,
    AwaitingAccept {
        control: StreamControlBinding,
        request: StreamOpenRequest,
    },
    Accepted(StreamOpenRequest),
    Opened,
}

#[derive(Clone, Copy)]
struct StreamControlBinding {
    request_id: [u8; 16],
    session_id: [u8; 16],
}

impl StreamGate {
    pub(crate) fn new(channel: ActiveChannel) -> Self {
        Self {
            channel,
            state: StreamGateState::AwaitingOpen,
        }
    }

    pub(crate) fn authorize_open(
        &mut self,
        envelope: &CoreV02Envelope,
    ) -> Result<(), StreamReject> {
        if !matches!(self.state, StreamGateState::AwaitingOpen) {
            return Err(StreamReject::DuplicateStream);
        }
        let request = envelope
            .stream_open_request()
            .map_err(|_| StreamReject::ControlRejected)?;
        self.validate_request(&request)?;
        let (request_id, session_id, _) = envelope
            .session_binding()
            .map_err(|_| StreamReject::ControlRejected)?;
        self.state = StreamGateState::AwaitingAccept {
            control: StreamControlBinding {
                request_id,
                session_id,
            },
            request,
        };
        Ok(())
    }

    pub(crate) fn accept(&mut self, envelope: &CoreV02Envelope) -> Result<(), StreamReject> {
        let StreamGateState::AwaitingAccept { control, request } = &self.state else {
            return Err(StreamReject::ControlRejected);
        };
        let (request_id, session_id, _) = envelope
            .session_binding()
            .map_err(|_| StreamReject::ControlRejected)?;
        if request_id != control.request_id || session_id != control.session_id {
            return Err(StreamReject::ControlRejected);
        }
        let (stream_id, channel_id, route_id) = envelope
            .stream_accept_binding()
            .map_err(|_| StreamReject::ControlRejected)?;
        if stream_id != request.quic_stream_id || channel_id != request.channel_id {
            return Err(StreamReject::ChannelMismatch);
        }
        if route_id != request.route_id {
            return Err(StreamReject::RouteMismatch);
        }
        self.state = StreamGateState::Accepted(request.clone());
        Ok(())
    }

    pub(crate) fn authorize_application_stream(
        &mut self,
        actual_stream_id: u64,
    ) -> Result<(), StreamReject> {
        let StreamGateState::Accepted(request) = &self.state else {
            return Err(StreamReject::ControlRejected);
        };
        if actual_stream_id != request.quic_stream_id {
            return Err(StreamReject::DuplicateStream);
        }
        self.state = StreamGateState::Opened;
        Ok(())
    }

    pub(crate) fn is_opened(&self) -> bool {
        matches!(self.state, StreamGateState::Opened)
    }

    pub(crate) fn is_accepted(&self) -> bool {
        matches!(self.state, StreamGateState::Accepted(_))
    }

    fn validate_request(&self, request: &StreamOpenRequest) -> Result<(), StreamReject> {
        if request.transport != self.channel.transport || request.port != self.channel.port {
            return Err(StreamReject::UnsupportedTransport);
        }
        if request.channel_id != self.channel.channel_id
            || request.route_grant_digest != self.channel.route_grant_digest
        {
            return Err(StreamReject::ChannelMismatch);
        }
        if request.route_id != self.channel.route_id {
            return Err(StreamReject::RouteMismatch);
        }
        if request.quic_stream_id < 4
            || !request.quic_stream_id.is_multiple_of(4)
            || request.quic_stream_id > 4_611_686_018_427_387_903
        {
            return Err(StreamReject::DuplicateStream);
        }
        Ok(())
    }
}
