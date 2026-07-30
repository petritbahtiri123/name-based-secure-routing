use std::fmt;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransportError {
    InvalidPeerIdentity,
    InvalidPeerRole,
    InvalidTimeout,
}

impl fmt::Display for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            Self::InvalidPeerIdentity => "invalid peer identity",
            Self::InvalidPeerRole => "invalid peer role",
            Self::InvalidTimeout => "invalid transport timeout",
        };
        formatter.write_str(message)
    }
}

impl std::error::Error for TransportError {}
