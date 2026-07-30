use std::fmt;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransportError {
    InvalidEndpointRole,
    InvalidPeerIdentity,
    InvalidPeerRole,
    InvalidTimeout,
    InvalidTlsMaterial,
}

impl fmt::Display for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            Self::InvalidEndpointRole => "invalid endpoint role",
            Self::InvalidPeerIdentity => "invalid peer identity",
            Self::InvalidPeerRole => "invalid peer role",
            Self::InvalidTimeout => "invalid transport timeout",
            Self::InvalidTlsMaterial => "invalid TLS material",
        };
        formatter.write_str(message)
    }
}

impl std::error::Error for TransportError {}
