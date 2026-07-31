use std::fmt;

use crate::CoreV02Reject;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransportError {
    AlpnMismatch,
    ApplicationPayloadTooLarge,
    ApplicationStreamFailed,
    ApplicationStreamRejected,
    BindFailed,
    CloseTimeout,
    ControlFrameInvalid,
    ControlFrameTooLarge,
    ControlRejected(CoreV02Reject),
    ControlStreamFailed,
    ConnectFailed,
    HandshakeFailed,
    HandshakeTimeout,
    InvalidEndpointRole,
    InvalidPeerIdentity,
    InvalidPeerRole,
    InvalidTimeout,
    InvalidTlsMaterial,
    PeerIdentityMismatch,
    PeerIdentityUnavailable,
    PeerUnavailable,
}

impl fmt::Display for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            Self::AlpnMismatch => "ALPN mismatch",
            Self::ApplicationPayloadTooLarge => "application payload exceeds the profile bound",
            Self::ApplicationStreamFailed => "application stream failed",
            Self::ApplicationStreamRejected => "application stream rejected",
            Self::BindFailed => "transport bind failed",
            Self::CloseTimeout => "transport close timed out",
            Self::ControlFrameInvalid => "invalid control frame",
            Self::ControlFrameTooLarge => "control frame exceeds the profile bound",
            Self::ControlRejected(_) => "control frame rejected",
            Self::ControlStreamFailed => "control stream failed",
            Self::ConnectFailed => "transport connect failed",
            Self::HandshakeFailed => "transport handshake failed",
            Self::HandshakeTimeout => "transport handshake timed out",
            Self::InvalidEndpointRole => "invalid endpoint role",
            Self::InvalidPeerIdentity => "invalid peer identity",
            Self::InvalidPeerRole => "invalid peer role",
            Self::InvalidTimeout => "invalid transport timeout",
            Self::InvalidTlsMaterial => "invalid TLS material",
            Self::PeerIdentityMismatch => "peer identity mismatch",
            Self::PeerIdentityUnavailable => "peer identity unavailable",
            Self::PeerUnavailable => "peer unavailable",
        };
        formatter.write_str(message)
    }
}

impl std::error::Error for TransportError {}
