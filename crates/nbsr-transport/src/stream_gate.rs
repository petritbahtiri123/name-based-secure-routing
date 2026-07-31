//! Single-service application-stream admission for the WP3 loopback profile.

use crate::{ActiveChannel, CoreV02Envelope};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StreamReject {
    ChannelMismatch,
    ControlRejected,
    DuplicateStream,
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

pub struct StreamGate {
    channel: ActiveChannel,
    state: StreamGateState,
}

enum StreamGateState {
    AwaitingOpen,
    AwaitingAccept(StreamOpenRequest),
    Accepted(StreamOpenRequest),
    Opened,
}

impl StreamGate {
    pub fn new(channel: ActiveChannel) -> Self {
        Self {
            channel,
            state: StreamGateState::AwaitingOpen,
        }
    }

    pub fn authorize_open(&mut self, envelope: &CoreV02Envelope) -> Result<(), StreamReject> {
        if !matches!(self.state, StreamGateState::AwaitingOpen) {
            return Err(StreamReject::DuplicateStream);
        }
        let request = envelope
            .stream_open_request()
            .map_err(|_| StreamReject::ControlRejected)?;
        self.validate_request(&request)?;
        self.state = StreamGateState::AwaitingAccept(request);
        Ok(())
    }

    pub fn accept(&mut self, envelope: &CoreV02Envelope) -> Result<(), StreamReject> {
        let StreamGateState::AwaitingAccept(request) = &self.state else {
            return Err(StreamReject::ControlRejected);
        };
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
        if request.quic_stream_id != 4 {
            return Err(StreamReject::DuplicateStream);
        }
        Ok(())
    }
}
