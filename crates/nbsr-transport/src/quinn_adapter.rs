use std::collections::HashMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, Weak};

use quinn::crypto::rustls::HandshakeData;
use quinn::{Connection, Endpoint, RecvStream, SendStream, VarInt};
use rustls::pki_types::CertificateDer;
use tokio::io::AsyncReadExt;
use tokio::sync::{Mutex as AsyncMutex, Notify};
use tokio::time::timeout;
use x509_parser::extensions::GeneralName;
use x509_parser::prelude::{FromDer, X509Certificate};

use crate::channel_binding::{EXPORTER_LABEL, EXPORTER_LENGTH, service_channel_context_hash};
use crate::{
    ALPN, ChannelBinding, ClientEndpointConfig, ControlSession, CoreV02Envelope, EdgeIdentity,
    EdgeRole, PeerPolicy, ServerEndpointConfig, ServiceChannelContext, ServiceChannelExporterError,
    SessionReject, TransportError,
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

pub struct ApplicationStream {
    id: u64,
    shared: Arc<SharedApplicationStream>,
}

struct ApplicationStreamParts {
    send: SendStream,
    receive: RecvStream,
}

struct SharedApplicationStream {
    cancelled: AtomicBool,
    inner: AsyncMutex<ApplicationStreamParts>,
    notify: Notify,
}

type TrackedStream = Weak<SharedApplicationStream>;
type TrackedChannelStreams = HashMap<u64, TrackedStream>;

impl SharedApplicationStream {
    fn force_reset(&self) {
        self.cancelled.store(true, Ordering::Release);
        self.notify.notify_waiters();
        if let Ok(mut inner) = self.inner.try_lock() {
            reset_parts(&mut inner);
        }
    }
}

struct TrackedApplicationStreams {
    by_channel: Mutex<HashMap<[u8; 16], TrackedChannelStreams>>,
}

impl TrackedApplicationStreams {
    fn new() -> Self {
        Self {
            by_channel: Mutex::new(HashMap::new()),
        }
    }

    fn track(&self, channel_id: [u8; 16], stream: &ApplicationStream) {
        let mut by_channel = self
            .by_channel
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let streams = by_channel.entry(channel_id).or_default();
        streams.retain(|_, stream| stream.strong_count() != 0);
        streams.insert(stream.id, Arc::downgrade(&stream.shared));
    }

    fn reset_channel(&self, channel_id: &[u8; 16]) {
        let streams = self
            .by_channel
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .remove(channel_id)
            .unwrap_or_default();
        for stream in streams.into_values().filter_map(|stream| stream.upgrade()) {
            stream.force_reset();
        }
    }

    fn reset_all(&self) {
        let streams = std::mem::take(
            &mut *self
                .by_channel
                .lock()
                .unwrap_or_else(|error| error.into_inner()),
        );
        for stream in streams
            .into_values()
            .flat_map(HashMap::into_values)
            .filter_map(|stream| stream.upgrade())
        {
            stream.force_reset();
        }
    }
}

fn application_stream(send: SendStream, receive: RecvStream) -> ApplicationStream {
    let id = VarInt::from(send.id()).into_inner();
    ApplicationStream {
        id,
        shared: Arc::new(SharedApplicationStream {
            cancelled: AtomicBool::new(false),
            inner: AsyncMutex::new(ApplicationStreamParts { send, receive }),
            notify: Notify::new(),
        }),
    }
}

fn reset_parts(parts: &mut ApplicationStreamParts) {
    let code = VarInt::from_u32(1);
    let _ = parts.send.reset(code);
    let _ = parts.receive.stop(code);
}

impl ApplicationStream {
    pub fn id(&self) -> u64 {
        self.id
    }

    pub async fn send_payload(&mut self, payload: &[u8]) -> Result<(), TransportError> {
        let notified = self.shared.notify.notified();
        tokio::pin!(notified);
        let mut inner = self.shared.inner.lock().await;
        if self.shared.cancelled.load(Ordering::Acquire) {
            reset_parts(&mut inner);
            return Err(TransportError::ApplicationStreamRejected);
        }
        tokio::select! {
            _ = &mut notified => {
                reset_parts(&mut inner);
                return Err(TransportError::ApplicationStreamRejected);
            }
            result = inner.send.write_all(payload) => {
                result.map_err(|_| TransportError::ApplicationStreamFailed)?;
            }
        }
        if self.shared.cancelled.load(Ordering::Acquire) {
            reset_parts(&mut inner);
            return Err(TransportError::ApplicationStreamRejected);
        }
        inner
            .send
            .finish()
            .map_err(|_| TransportError::ApplicationStreamFailed)
    }

    pub async fn receive_payload(&mut self) -> Result<Vec<u8>, TransportError> {
        let notified = self.shared.notify.notified();
        tokio::pin!(notified);
        let mut inner = self.shared.inner.lock().await;
        if self.shared.cancelled.load(Ordering::Acquire) {
            reset_parts(&mut inner);
            return Err(TransportError::ApplicationStreamRejected);
        }
        tokio::select! {
            _ = &mut notified => {
                reset_parts(&mut inner);
                Err(TransportError::ApplicationStreamRejected)
            }
            result = inner.receive.read_to_end(4_096) => {
                result.map_err(|_| TransportError::ApplicationStreamRejected)
            }
        }
    }

    pub async fn send_and_receive(&mut self, payload: &[u8]) -> Result<Vec<u8>, TransportError> {
        self.send_payload(payload).await?;
        self.receive_payload().await
    }

    async fn reject(self) -> Result<(), TransportError> {
        self.shared.cancelled.store(true, Ordering::Release);
        self.shared.notify.notify_waiters();
        let mut inner = self.shared.inner.lock().await;
        let code = VarInt::from_u32(1);
        inner
            .send
            .reset(code)
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        inner
            .receive
            .stop(code)
            .map_err(|_| TransportError::ApplicationStreamFailed)
    }

    pub async fn echo_once(&mut self) -> Result<Vec<u8>, TransportError> {
        let notified = self.shared.notify.notified();
        tokio::pin!(notified);
        let mut inner = self.shared.inner.lock().await;
        if self.shared.cancelled.load(Ordering::Acquire) {
            reset_parts(&mut inner);
            return Err(TransportError::ApplicationStreamRejected);
        }
        let payload = match tokio::select! {
            _ = &mut notified => {
                reset_parts(&mut inner);
                return Err(TransportError::ApplicationStreamRejected);
            }
            result = inner.receive.read_to_end(4_097) => result,
        } {
            Ok(payload) if payload.len() <= 4_096 => payload,
            Ok(_) | Err(_) => {
                let code = VarInt::from_u32(2);
                let _ = inner.send.reset(code);
                let _ = inner.receive.stop(code);
                return Err(TransportError::ApplicationPayloadTooLarge);
            }
        };
        tokio::select! {
            _ = &mut notified => {
                reset_parts(&mut inner);
                return Err(TransportError::ApplicationStreamRejected);
            }
            result = inner.send.write_all(&payload) => {
                result.map_err(|_| TransportError::ApplicationStreamFailed)?;
            }
        }
        inner
            .send
            .finish()
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        Ok(payload)
    }
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
    authenticated_peer_role: EdgeRole,
    binding_capability: ConnectionBindingCapability,
    local_role: EdgeRole,
    negotiated_alpn: Vec<u8>,
    close_timeout: std::time::Duration,
    tracked_streams: Arc<TrackedApplicationStreams>,
}

struct ConnectionBindingMarker;

/// Opaque exact-connection capability minted once after Quinn authentication.
///
/// A session clone keeps the allocation alive, so another live connection
/// cannot acquire the same allocation identity even if names and roles match.
#[derive(Clone)]
pub(crate) struct ConnectionBindingCapability(Arc<ConnectionBindingMarker>);

impl ConnectionBindingCapability {
    fn new() -> Self {
        Self(Arc::new(ConnectionBindingMarker))
    }

    pub(crate) fn matches(&self, other: &Self) -> bool {
        Arc::ptr_eq(&self.0, &other.0)
    }
}

impl AuthenticatedConnection {
    pub fn authenticated_peer(&self) -> &EdgeIdentity {
        &self.authenticated_peer
    }

    pub fn negotiated_alpn(&self) -> &[u8] {
        &self.negotiated_alpn
    }

    pub(crate) fn binding_capability(&self) -> ConnectionBindingCapability {
        self.binding_capability.clone()
    }

    pub(crate) fn local_role(&self) -> EdgeRole {
        self.local_role
    }

    pub fn export_channel_binding(
        &self,
        context: &ServiceChannelContext<'_>,
    ) -> Result<ChannelBinding, ServiceChannelExporterError> {
        let context_hash = service_channel_context_hash(context)?;
        let mut output = [0_u8; EXPORTER_LENGTH];
        self.connection
            .export_keying_material(&mut output, EXPORTER_LABEL, &context_hash)
            .map_err(|_| ServiceChannelExporterError::LiveExportFailed)?;
        Ok(ChannelBinding::from_exporter(context.channel_id, output))
    }

    pub fn bind_channel(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
    ) -> Result<(), SessionReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(SessionReject::ConnectionMismatch);
        }
        let request = session.channel_binding_request(channel_id)?;
        let matches_session = match (self.local_role, self.authenticated_peer_role) {
            (EdgeRole::Source, EdgeRole::Destination) => {
                self.authenticated_peer.as_str() == request.destination_edge_id
            }
            (EdgeRole::Destination, EdgeRole::Source) => {
                self.authenticated_peer.as_str() == request.source_edge_id
            }
            _ => false,
        };
        if !matches_session {
            return Err(SessionReject::ConnectionMismatch);
        }
        let binding = self
            .export_channel_binding(&request.context())
            .map_err(|_| SessionReject::ChannelBindingFailed)?;
        session.install_channel_binding(channel_id, binding)
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

    pub async fn open_application_stream(&self) -> Result<ApplicationStream, TransportError> {
        let (send, receive) = self
            .connection
            .open_bi()
            .await
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        Ok(application_stream(send, receive))
    }

    pub async fn accept_session_stream(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
    ) -> Result<ApplicationStream, TransportError> {
        let (send, receive) = self
            .connection
            .accept_bi()
            .await
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        let stream = application_stream(send, receive);
        if session
            .authorize_application_stream(channel_id, stream.id())
            .is_err()
        {
            let _ = stream.reject().await;
            return Err(TransportError::ApplicationStreamRejected);
        }
        self.tracked_streams.track(channel_id, &stream);
        Ok(stream)
    }

    pub async fn reject_next_application_stream(&self) -> Result<u64, TransportError> {
        let (send, receive) = self
            .connection
            .accept_bi()
            .await
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        let stream = application_stream(send, receive);
        let id = stream.id();
        stream.reject().await?;
        Ok(id)
    }

    pub async fn enforce_channel_drain(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
        monotonic_now: u64,
    ) -> Result<crate::DrainEnforcement, SessionReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(SessionReject::ConnectionMismatch);
        }
        let result = session.enforce_channel_drain(channel_id, monotonic_now)?;
        if matches!(result, crate::DrainEnforcement::Enforced { .. }) {
            self.tracked_streams.reset_channel(&channel_id);
        }
        Ok(result)
    }

    pub fn accept_route_revoke(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(SessionReject::ConnectionMismatch);
        }
        session.accept_route_revoke(channel_id, envelope)?;
        self.tracked_streams.reset_channel(&channel_id);
        Ok(())
    }

    pub fn accept_route_close(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<(), SessionReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(SessionReject::ConnectionMismatch);
        }
        session.accept_route_close(channel_id, envelope)?;
        self.tracked_streams.reset_channel(&channel_id);
        Ok(())
    }

    pub async fn enforce_session_drain(
        &self,
        session: &mut ControlSession,
        monotonic_now: u64,
    ) -> Result<crate::DrainEnforcement, SessionReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(SessionReject::ConnectionMismatch);
        }
        for channel_id in session.due_draining_channels(monotonic_now) {
            let channel_result = session.enforce_channel_drain(channel_id, monotonic_now)?;
            if matches!(channel_result, crate::DrainEnforcement::Enforced { .. }) {
                self.tracked_streams.reset_channel(&channel_id);
            }
        }
        let result = session.enforce_session_drain(monotonic_now)?;
        if matches!(result, crate::DrainEnforcement::Enforced { .. }) {
            self.tracked_streams.reset_all();
            self.connection
                .close(VarInt::from_u32(1), b"session drain deadline");
        }
        Ok(result)
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
        authenticated_peer_role: policy.expected_peer_role(),
        binding_capability: ConnectionBindingCapability::new(),
        local_role: policy.local_role(),
        negotiated_alpn,
        close_timeout: policy.handshake_timeout(),
        tracked_streams: Arc::new(TrackedApplicationStreams::new()),
    })
}
