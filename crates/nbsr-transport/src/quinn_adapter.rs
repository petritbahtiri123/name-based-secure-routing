use std::net::{IpAddr, Ipv4Addr, SocketAddr};

use quinn::crypto::rustls::HandshakeData;
use quinn::{Connection, Endpoint, VarInt};
use rustls::pki_types::CertificateDer;
use tokio::time::timeout;
use x509_parser::extensions::GeneralName;
use x509_parser::prelude::{FromDer, X509Certificate};

use crate::{
    ALPN, ClientEndpointConfig, EdgeIdentity, PeerPolicy, ServerEndpointConfig, TransportError,
};

pub struct TransportListener {
    endpoint: Endpoint,
    policy: PeerPolicy,
}

impl TransportListener {
    pub fn bind(
        config: ServerEndpointConfig,
        bind_address: SocketAddr,
    ) -> Result<Self, TransportError> {
        let endpoint =
            Endpoint::server(config.quinn, bind_address).map_err(|_| TransportError::BindFailed)?;
        Ok(Self {
            endpoint,
            policy: config.policy,
        })
    }

    pub fn local_addr(&self) -> Result<SocketAddr, TransportError> {
        self.endpoint
            .local_addr()
            .map_err(|_| TransportError::BindFailed)
    }

    pub async fn accept_one(&self) -> Result<AuthenticatedConnection, TransportError> {
        let incoming = timeout(self.policy.handshake_timeout(), self.endpoint.accept())
            .await
            .map_err(|_| TransportError::HandshakeTimeout)?
            .ok_or(TransportError::PeerUnavailable)?;
        let connection = timeout(self.policy.handshake_timeout(), incoming)
            .await
            .map_err(|_| TransportError::HandshakeTimeout)?
            .map_err(|_| TransportError::HandshakeFailed)?;
        authenticate_connection(connection, self.endpoint.clone(), &self.policy)
    }

    pub async fn close(self) -> Result<(), TransportError> {
        self.endpoint.close(VarInt::from_u32(0), b"");
        timeout(self.policy.handshake_timeout(), self.endpoint.wait_idle())
            .await
            .map_err(|_| TransportError::CloseTimeout)
    }
}

pub async fn connect(
    config: ClientEndpointConfig,
    remote: SocketAddr,
) -> Result<AuthenticatedConnection, TransportError> {
    let mut endpoint = Endpoint::client(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0))
        .map_err(|_| TransportError::BindFailed)?;
    endpoint.set_default_client_config(config.quinn);

    let connecting = endpoint
        .connect(remote, config.policy.expected_peer().as_str())
        .map_err(|_| TransportError::ConnectFailed)?;
    let connection = timeout(config.policy.handshake_timeout(), connecting)
        .await
        .map_err(|_| TransportError::HandshakeTimeout)?
        .map_err(|_| TransportError::HandshakeFailed)?;
    authenticate_connection(connection, endpoint, &config.policy)
}

pub struct AuthenticatedConnection {
    endpoint: Endpoint,
    connection: Connection,
    authenticated_peer: EdgeIdentity,
    negotiated_alpn: Vec<u8>,
    close_timeout: std::time::Duration,
}

impl AuthenticatedConnection {
    pub fn authenticated_peer(&self) -> &EdgeIdentity {
        &self.authenticated_peer
    }

    pub fn negotiated_alpn(&self) -> &[u8] {
        &self.negotiated_alpn
    }

    pub async fn close(self) -> Result<(), TransportError> {
        self.connection.close(VarInt::from_u32(0), b"");
        timeout(self.close_timeout, self.endpoint.wait_idle())
            .await
            .map_err(|_| TransportError::CloseTimeout)
    }
}

fn authenticate_connection(
    connection: Connection,
    endpoint: Endpoint,
    policy: &PeerPolicy,
) -> Result<AuthenticatedConnection, TransportError> {
    let handshake = connection
        .handshake_data()
        .ok_or(TransportError::HandshakeFailed)?
        .downcast::<HandshakeData>()
        .map_err(|_| TransportError::HandshakeFailed)?;
    let negotiated_alpn = handshake.protocol.ok_or(TransportError::AlpnMismatch)?;
    if negotiated_alpn.as_slice() != ALPN {
        connection.close(VarInt::from_u32(0), b"");
        return Err(TransportError::AlpnMismatch);
    }

    let identity = connection
        .peer_identity()
        .ok_or(TransportError::PeerIdentityUnavailable)?
        .downcast::<Vec<CertificateDer<'static>>>()
        .map_err(|_| TransportError::PeerIdentityUnavailable)?;
    let leaf = identity
        .first()
        .ok_or(TransportError::PeerIdentityUnavailable)?;
    let (_, certificate) = X509Certificate::from_der(leaf.as_ref())
        .map_err(|_| TransportError::PeerIdentityUnavailable)?;
    let san = certificate
        .subject_alternative_name()
        .map_err(|_| TransportError::PeerIdentityUnavailable)?
        .ok_or(TransportError::PeerIdentityUnavailable)?;
    let dns_names = san
        .value
        .general_names
        .iter()
        .filter_map(|name| match name {
            GeneralName::DNSName(name) => Some(*name),
            _ => None,
        })
        .collect::<Vec<_>>();

    if dns_names.as_slice() != [policy.expected_peer().as_str()] {
        connection.close(VarInt::from_u32(0), b"");
        return Err(TransportError::PeerIdentityMismatch);
    }

    Ok(AuthenticatedConnection {
        endpoint,
        connection,
        authenticated_peer: policy.expected_peer().clone(),
        negotiated_alpn,
        close_timeout: policy.handshake_timeout(),
    })
}
