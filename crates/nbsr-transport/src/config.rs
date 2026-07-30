use std::time::Duration;

use rustls::pki_types::ServerName;

use crate::TransportError;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EdgeRole {
    Source,
    Destination,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EdgeIdentity(String);

impl EdgeIdentity {
    pub fn from_dns_name(value: impl Into<String>) -> Result<Self, TransportError> {
        let value = value.into();
        match ServerName::try_from(value.clone()) {
            Ok(ServerName::DnsName(_)) => Ok(Self(value)),
            Ok(ServerName::IpAddress(_)) | Err(_) => Err(TransportError::InvalidPeerIdentity),
            _ => Err(TransportError::InvalidPeerIdentity),
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PeerPolicy {
    local_role: EdgeRole,
    expected_peer_role: EdgeRole,
    expected_peer: EdgeIdentity,
    handshake_timeout: Duration,
    idle_timeout: Duration,
}

impl PeerPolicy {
    pub fn new(
        local_role: EdgeRole,
        expected_peer_role: EdgeRole,
        expected_peer: EdgeIdentity,
        handshake_timeout: Duration,
        idle_timeout: Duration,
    ) -> Result<Self, TransportError> {
        if local_role == expected_peer_role {
            return Err(TransportError::InvalidPeerRole);
        }
        if handshake_timeout.is_zero() || idle_timeout.is_zero() {
            return Err(TransportError::InvalidTimeout);
        }
        Ok(Self {
            local_role,
            expected_peer_role,
            expected_peer,
            handshake_timeout,
            idle_timeout,
        })
    }

    pub fn local_role(&self) -> EdgeRole {
        self.local_role
    }

    pub fn expected_peer_role(&self) -> EdgeRole {
        self.expected_peer_role
    }

    pub fn expected_peer(&self) -> &EdgeIdentity {
        &self.expected_peer
    }

    pub fn handshake_timeout(&self) -> Duration {
        self.handshake_timeout
    }

    pub fn idle_timeout(&self) -> Duration {
        self.idle_timeout
    }
}
