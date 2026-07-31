//! Single-service application-stream admission for the WP3 loopback profile.

use crate::ActiveChannel;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StreamReject {
    ChannelMismatch,
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
    opened: bool,
}

impl StreamGate {
    pub fn new(channel: ActiveChannel) -> Self {
        Self {
            channel,
            opened: false,
        }
    }

    pub fn authorize(&mut self, request: &StreamOpenRequest) -> Result<(), StreamReject> {
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
        if request.quic_stream_id != 4 || self.opened {
            return Err(StreamReject::DuplicateStream);
        }
        self.opened = true;
        Ok(())
    }
}
