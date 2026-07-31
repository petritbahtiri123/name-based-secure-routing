use std::net::{IpAddr, Ipv4Addr, SocketAddr};

use quinn::crypto::rustls::HandshakeData;
use quinn::{Connection, Endpoint, RecvStream, SendStream, VarInt};
use rustls::pki_types::CertificateDer;
use tokio::io::AsyncReadExt;
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

pub struct ControlStream {
    send: SendStream,
    receive: RecvStream,
}

impl ControlStream {
    pub async fn send_envelope(
        &mut self,
        envelope: &crate::CoreV02Envelope,
    ) -> Result<(), TransportError> {
        let wire = envelope.encode();
        let prefix = encode_frame_length(wire.len())?;
        self.send
            .write_all(&prefix)
            .await
            .map_err(|_| TransportError::ControlStreamFailed)?;
        self.send
            .write_all(&wire)
            .await
            .map_err(|_| TransportError::ControlStreamFailed)
    }

    pub async fn receive_envelope(
        &mut self,
        limits: crate::CoreV02Limits,
    ) -> Result<crate::CoreV02Envelope, TransportError> {
        let first = self
            .receive
            .read_u8()
            .await
            .map_err(|_| TransportError::ControlStreamFailed)?;
        let length = decode_frame_length(first, &mut self.receive).await?;
        if length == 0 || length > limits.max_frame_bytes || length > 65_536 {
            return Err(TransportError::ControlFrameTooLarge);
        }
        let mut wire = vec![0; length];
        self.receive
            .read_exact(&mut wire)
            .await
            .map_err(|_| TransportError::ControlStreamFailed)?;
        crate::decode_control_envelope(&wire, limits).map_err(TransportError::ControlRejected)
    }
}

fn encode_frame_length(length: usize) -> Result<Vec<u8>, TransportError> {
    if !(1..=65_536).contains(&length) {
        return Err(TransportError::ControlFrameTooLarge);
    }
    let length = length as u64;
    if length <= 63 {
        Ok(vec![length as u8])
    } else if length <= 16_383 {
        Ok(((0x4000 | length as u16).to_be_bytes()).to_vec())
    } else {
        Ok(((0x8000_0000 | length as u32).to_be_bytes()).to_vec())
    }
}

async fn decode_frame_length(first: u8, receive: &mut RecvStream) -> Result<usize, TransportError> {
    let width = 1usize << (first >> 6);
    let mut bytes = vec![first & 0x3f];
    if width > 1 {
        let mut rest = vec![0; width - 1];
        receive
            .read_exact(&mut rest)
            .await
            .map_err(|_| TransportError::ControlStreamFailed)?;
        bytes.extend_from_slice(&rest);
    }
    let value = bytes
        .into_iter()
        .fold(0usize, |value, byte| (value << 8) | usize::from(byte));
    if (width == 1 && value > 63)
        || (width == 2 && !(64..=16_383).contains(&value))
        || (width == 4 && !(16_384..=1_073_741_823).contains(&value))
        || width == 8
    {
        return Err(TransportError::ControlFrameInvalid);
    }
    Ok(value)
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

    pub async fn open_control_stream(&self) -> Result<ControlStream, TransportError> {
        let (send, receive) = self
            .connection
            .open_bi()
            .await
            .map_err(|_| TransportError::ControlStreamFailed)?;
        Ok(ControlStream { send, receive })
    }

    pub async fn accept_control_stream(&self) -> Result<ControlStream, TransportError> {
        let (send, receive) = self
            .connection
            .accept_bi()
            .await
            .map_err(|_| TransportError::ControlStreamFailed)?;
        Ok(ControlStream { send, receive })
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
