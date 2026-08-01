use std::fmt;
use std::sync::Arc;
use std::time::Duration;

use quinn::crypto::rustls::{QuicClientConfig, QuicServerConfig};
use quinn::{ClientConfig, ServerConfig, TransportConfig, VarInt};
use rustls::client::Resumption;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, ServerName};
use rustls::server::WebPkiClientVerifier;
use rustls::{RootCertStore, version};

use crate::{ALPN, TransportError};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EdgeRole {
    Source,
    Destination,
}

pub struct TlsMaterial {
    certificate_chain: Vec<CertificateDer<'static>>,
    private_key: PrivateKeyDer<'static>,
    trust_roots: RootCertStore,
}

impl TlsMaterial {
    pub fn new(
        certificate_chain: Vec<CertificateDer<'static>>,
        private_key: PrivateKeyDer<'static>,
        trust_roots: RootCertStore,
    ) -> Result<Self, TransportError> {
        if certificate_chain.is_empty() || trust_roots.is_empty() {
            return Err(TransportError::InvalidTlsMaterial);
        }
        Ok(Self {
            certificate_chain,
            private_key,
            trust_roots,
        })
    }
}

impl fmt::Debug for TlsMaterial {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("TlsMaterial")
            .field("certificate_count", &self.certificate_chain.len())
            .field("private_key", &"[redacted]")
            .field("trust_anchor_count", &self.trust_roots.len())
            .finish()
    }
}

pub struct ClientEndpointConfig {
    pub(crate) quinn: ClientConfig,
    pub(crate) policy: PeerPolicy,
}

impl fmt::Debug for ClientEndpointConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ClientEndpointConfig")
            .field("policy", &self.policy)
            .finish_non_exhaustive()
    }
}

pub struct ServerEndpointConfig {
    pub(crate) quinn: ServerConfig,
    pub(crate) policy: PeerPolicy,
}

impl fmt::Debug for ServerEndpointConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ServerEndpointConfig")
            .field("policy", &self.policy)
            .finish_non_exhaustive()
    }
}

pub fn build_client_config(
    policy: PeerPolicy,
    material: TlsMaterial,
) -> Result<ClientEndpointConfig, TransportError> {
    if policy.local_role() != EdgeRole::Source
        || policy.expected_peer_role() != EdgeRole::Destination
    {
        return Err(TransportError::InvalidEndpointRole);
    }

    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let mut tls = rustls::ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .map_err(|_| TransportError::InvalidTlsMaterial)?
        .with_root_certificates(material.trust_roots)
        .with_client_auth_cert(material.certificate_chain, material.private_key)
        .map_err(|_| TransportError::InvalidTlsMaterial)?;
    tls.alpn_protocols = vec![ALPN.to_vec()];
    tls.enable_early_data = false;
    tls.resumption = Resumption::disabled();

    let crypto = QuicClientConfig::try_from(tls).map_err(|_| TransportError::InvalidTlsMaterial)?;
    let mut quinn = ClientConfig::new(Arc::new(crypto));
    quinn.transport_config(transport_config(policy.idle_timeout())?);

    Ok(ClientEndpointConfig { quinn, policy })
}

pub fn build_server_config(
    policy: PeerPolicy,
    material: TlsMaterial,
) -> Result<ServerEndpointConfig, TransportError> {
    if policy.local_role() != EdgeRole::Destination
        || policy.expected_peer_role() != EdgeRole::Source
    {
        return Err(TransportError::InvalidEndpointRole);
    }

    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let verifier = WebPkiClientVerifier::builder_with_provider(
        Arc::new(material.trust_roots),
        Arc::clone(&provider),
    )
    .build()
    .map_err(|_| TransportError::InvalidTlsMaterial)?;
    let mut tls = rustls::ServerConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .map_err(|_| TransportError::InvalidTlsMaterial)?
        .with_client_cert_verifier(verifier)
        .with_single_cert(material.certificate_chain, material.private_key)
        .map_err(|_| TransportError::InvalidTlsMaterial)?;
    tls.alpn_protocols = vec![ALPN.to_vec()];
    tls.max_early_data_size = 0;

    let crypto = QuicServerConfig::try_from(tls).map_err(|_| TransportError::InvalidTlsMaterial)?;
    let mut quinn = ServerConfig::with_crypto(Arc::new(crypto));
    quinn.transport = transport_config(policy.idle_timeout())?;

    Ok(ServerEndpointConfig { quinn, policy })
}

fn transport_config(idle_timeout: Duration) -> Result<Arc<TransportConfig>, TransportError> {
    let idle_timeout = idle_timeout
        .try_into()
        .map_err(|_| TransportError::InvalidTimeout)?;
    let mut transport = TransportConfig::default();
    transport.max_idle_timeout(Some(idle_timeout));
    // Stream 0 is the only control stream; WP3 permits one application stream.
    transport.max_concurrent_bidi_streams(VarInt::from_u32(2));
    transport.max_concurrent_uni_streams(VarInt::from_u32(0));
    crate::quinn_adapter::configure_datagram_buffers(&mut transport);
    Ok(Arc::new(transport))
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
