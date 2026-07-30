use std::fmt;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransportError {
    AlpnMismatch,
    BindFailed,
    CloseTimeout,
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
            Self::BindFailed => "transport bind failed",
            Self::CloseTimeout => "transport close timed out",
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
