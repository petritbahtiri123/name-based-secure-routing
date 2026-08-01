use std::collections::HashMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, Weak};

use bytes::Bytes;
use quinn::crypto::rustls::HandshakeData;
use quinn::{Connection, Endpoint, RecvStream, SendStream, VarInt};
use rustls::pki_types::CertificateDer;
use tokio::io::AsyncReadExt;
use tokio::sync::{Mutex as AsyncMutex, Notify};
use tokio::time::timeout;
use x509_parser::extensions::GeneralName;
use x509_parser::prelude::{FromDer, X509Certificate};

use crate::channel_binding::{EXPORTER_LABEL, EXPORTER_LENGTH, canonical_service_channel_context};
use crate::{
    ALPN, ChannelBinding, ClientEndpointConfig, ControlSession, CoreV02Envelope, EdgeIdentity,
    EdgeRole, PeerPolicy, ServerEndpointConfig, ServiceChannelContext, ServiceChannelExporterError,
    SessionReject, TransportError,
};

const DATAGRAM_BUFFER_BYTES: usize = 262_144;
// 23 fixed bytes + 9-byte u64 sequence + 3-byte length + 1200-byte payload.
const MAX_LOCAL_ENCODED_DATAGRAM_BYTES: usize = 1_235;
const MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM: usize = 1_048_576;
const MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL: usize = 8_388_608;

fn live_exporter_context(
    context: &ServiceChannelContext<'_>,
) -> Result<Vec<u8>, ServiceChannelExporterError> {
    canonical_service_channel_context(context)
}

pub(crate) fn configure_datagram_buffers(transport: &mut quinn::TransportConfig) {
    transport.datagram_receive_buffer_size(Some(DATAGRAM_BUFFER_BYTES));
    transport.datagram_send_buffer_size(DATAGRAM_BUFFER_BYTES);
}

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

pub struct ApplicationStreamPermit {
    binding_capability: ConnectionBindingCapability,
    channel_id: [u8; 16],
    stream_id: u64,
}

impl ApplicationStreamPermit {
    pub(crate) fn new(
        binding_capability: ConnectionBindingCapability,
        channel_id: [u8; 16],
        stream_id: u64,
    ) -> Self {
        Self {
            binding_capability,
            channel_id,
            stream_id,
        }
    }
}

struct ApplicationStreamParts {
    send: SendStream,
    receive: RecvStream,
}

struct SharedApplicationStream {
    cancelled: AtomicBool,
    inner: AsyncMutex<ApplicationStreamParts>,
    notify: Notify,
    channel_quota: Mutex<Option<Arc<ChannelByteQuota>>>,
    inbound_bytes: HeldChannelBytes,
    outbound_bytes: HeldChannelBytes,
}

#[derive(Default)]
struct ChannelByteQuota {
    buffered: Mutex<usize>,
}

struct ChannelByteReservation {
    quota: Arc<ChannelByteQuota>,
    bytes: usize,
}

#[derive(Default)]
struct HeldChannelBytes {
    reservations: Mutex<Vec<ChannelByteReservation>>,
}

impl HeldChannelBytes {
    fn retain(&self, reservation: ChannelByteReservation) {
        self.reservations
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .push(reservation);
    }

    fn retain_all(&self, reservations: Vec<ChannelByteReservation>) {
        self.reservations
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .extend(reservations);
    }

    fn release(&self) {
        self.reservations
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clear();
    }
}

impl ChannelByteQuota {
    fn reserve(self: &Arc<Self>, bytes: usize) -> Result<ChannelByteReservation, TransportError> {
        let mut buffered = self
            .buffered
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let next = buffered
            .checked_add(bytes)
            .ok_or(TransportError::ApplicationPayloadTooLarge)?;
        if next > MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL {
            return Err(TransportError::ApplicationPayloadTooLarge);
        }
        *buffered = next;
        Ok(ChannelByteReservation {
            quota: Arc::clone(self),
            bytes,
        })
    }
}

impl Drop for ChannelByteReservation {
    fn drop(&mut self) {
        let mut buffered = self
            .quota
            .buffered
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        *buffered = buffered.saturating_sub(self.bytes);
    }
}

type TrackedStream = Weak<SharedApplicationStream>;
type TrackedChannelStreams = HashMap<u64, TrackedStream>;

impl SharedApplicationStream {
    fn force_reset(&self) {
        self.cancelled.store(true, Ordering::Release);
        self.inbound_bytes.release();
        self.outbound_bytes.release();
        self.notify.notify_waiters();
        if let Ok(mut inner) = self.inner.try_lock() {
            reset_parts(&mut inner);
        }
    }
}

struct TrackedApplicationStreams {
    by_channel: Mutex<HashMap<[u8; 16], TrackedChannelStreams>>,
    channel_quotas: Mutex<HashMap<[u8; 16], Weak<ChannelByteQuota>>>,
}

impl TrackedApplicationStreams {
    fn new() -> Self {
        Self {
            by_channel: Mutex::new(HashMap::new()),
            channel_quotas: Mutex::new(HashMap::new()),
        }
    }

    fn track(&self, channel_id: [u8; 16], stream: &ApplicationStream) {
        let quota = {
            let mut quotas = self
                .channel_quotas
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            quotas.retain(|_, quota| quota.strong_count() != 0);
            if let Some(quota) = quotas.get(&channel_id).and_then(Weak::upgrade) {
                quota
            } else {
                let quota = Arc::new(ChannelByteQuota::default());
                quotas.insert(channel_id, Arc::downgrade(&quota));
                quota
            }
        };
        *stream
            .shared
            .channel_quota
            .lock()
            .unwrap_or_else(|error| error.into_inner()) = Some(quota);
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
            channel_quota: Mutex::new(None),
            inbound_bytes: HeldChannelBytes::default(),
            outbound_bytes: HeldChannelBytes::default(),
        }),
    }
}

fn reset_parts(parts: &mut ApplicationStreamParts) {
    let code = VarInt::from_u32(1);
    let _ = parts.send.reset(code);
    let _ = parts.receive.stop(code);
}

async fn read_live_payload(
    receive: &mut RecvStream,
    quota: Option<Arc<ChannelByteQuota>>,
) -> Result<(Vec<u8>, Vec<ChannelByteReservation>), TransportError> {
    let mut payload = Vec::new();
    let mut reservations = Vec::new();
    let mut chunk = [0_u8; 16_384];
    loop {
        let read = receive
            .read(&mut chunk)
            .await
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        let Some(read) = read else { break };
        if payload.len().saturating_add(read) > MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM {
            return Err(TransportError::ApplicationPayloadTooLarge);
        }
        if let Some(quota) = quota.as_ref() {
            reservations.push(quota.reserve(read)?);
        }
        payload.extend_from_slice(&chunk[..read]);
    }
    Ok((payload, reservations))
}

impl ApplicationStream {
    pub fn id(&self) -> u64 {
        self.id
    }

    pub async fn send_payload(&mut self, payload: &[u8]) -> Result<(), TransportError> {
        if payload.len() > MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM {
            return Err(TransportError::ApplicationPayloadTooLarge);
        }
        let quota = self
            .shared
            .channel_quota
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clone();
        let reservation = quota
            .as_ref()
            .map(|quota| quota.reserve(payload.len()))
            .transpose()?;
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
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        if let Some(reservation) = reservation {
            self.shared.outbound_bytes.retain(reservation);
        }
        Ok(())
    }

    pub async fn receive_payload(&mut self) -> Result<Vec<u8>, TransportError> {
        let notified = self.shared.notify.notified();
        tokio::pin!(notified);
        let mut inner = self.shared.inner.lock().await;
        if self.shared.cancelled.load(Ordering::Acquire) {
            reset_parts(&mut inner);
            return Err(TransportError::ApplicationStreamRejected);
        }
        let quota = self
            .shared
            .channel_quota
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clone();
        tokio::select! {
            _ = &mut notified => {
                reset_parts(&mut inner);
                Err(TransportError::ApplicationStreamRejected)
            }
            result = read_live_payload(&mut inner.receive, quota) => {
                let (payload, reservations) = result.map_err(|error| match error {
                    TransportError::ApplicationStreamFailed => {
                        TransportError::ApplicationStreamRejected
                    }
                    error => error,
                })?;
                self.shared.inbound_bytes.retain_all(reservations);
                Ok(payload)
            }
        }
    }

    /// Releases this stream's successfully returned inbound and outbound
    /// payload reservations. Payload bytes remain owned by the caller, but no
    /// longer count as transport-buffered after this explicit handoff.
    pub fn release_buffered_payloads(&self) {
        self.shared.inbound_bytes.release();
        self.shared.outbound_bytes.release();
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
        let quota = self
            .shared
            .channel_quota
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clone();
        let (payload, inbound_reservations) = match tokio::select! {
            _ = &mut notified => {
                reset_parts(&mut inner);
                return Err(TransportError::ApplicationStreamRejected);
            }
            result = read_live_payload(&mut inner.receive, quota.clone()) => result,
        } {
            Ok(payload) => payload,
            Err(_) => {
                let code = VarInt::from_u32(2);
                let _ = inner.send.reset(code);
                let _ = inner.receive.stop(code);
                return Err(TransportError::ApplicationPayloadTooLarge);
            }
        };
        let outbound_reservation = quota
            .as_ref()
            .map(|quota| quota.reserve(payload.len()))
            .transpose()?;
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
        self.shared.inbound_bytes.retain_all(inbound_reservations);
        if let Some(reservation) = outbound_reservation {
            self.shared.outbound_bytes.retain(reservation);
        }
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
        // rustls applies RFC 8446 Hash(context) internally. Passing the
        // already-hashed context here would hash it a second time.
        let exporter_context = live_exporter_context(context)?;
        let mut output = [0_u8; EXPORTER_LENGTH];
        self.connection
            .export_keying_material(&mut output, EXPORTER_LABEL, &exporter_context)
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

    pub fn udp_payload_capacity(
        &self,
        session: &ControlSession,
        channel_id: [u8; 16],
    ) -> Result<usize, crate::DatagramReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(crate::DatagramReject::ConnectionMismatch);
        }
        if self.connection.close_reason().is_some() {
            return Err(crate::DatagramReject::TransportFailed);
        }
        let peer_maximum = self
            .connection
            .max_datagram_size()
            .ok_or(crate::DatagramReject::PeerMaximum)?;
        session.udp_payload_capacity(channel_id, peer_maximum)
    }

    pub fn send_udp_datagram(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
        payload: &[u8],
        monotonic_milliseconds: u64,
    ) -> Result<(), crate::DatagramReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(crate::DatagramReject::ConnectionMismatch);
        }
        if self.connection.close_reason().is_some() {
            return Err(crate::DatagramReject::TransportFailed);
        }
        let peer_maximum = self
            .connection
            .max_datagram_size()
            .ok_or(crate::DatagramReject::PeerMaximum)?;
        let encoded =
            session.send_udp_datagram(channel_id, payload, peer_maximum, monotonic_milliseconds)?;
        self.connection
            .send_datagram(Bytes::from(encoded))
            .map_err(|error| match error {
                quinn::SendDatagramError::TooLarge => crate::DatagramReject::PeerMaximum,
                quinn::SendDatagramError::UnsupportedByPeer
                | quinn::SendDatagramError::Disabled
                | quinn::SendDatagramError::ConnectionLost(_) => {
                    crate::DatagramReject::TransportFailed
                }
            })
    }

    pub async fn receive_udp_datagram(
        &self,
        session: &mut ControlSession,
        monotonic_milliseconds: u64,
    ) -> Result<crate::DatagramReceive, crate::DatagramReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(crate::DatagramReject::ConnectionMismatch);
        }
        let frame = self.read_inbound_datagram().await?;
        session.receive_udp_datagram(frame, monotonic_milliseconds)
    }

    async fn read_inbound_datagram(&self) -> Result<crate::DatagramFrame, crate::DatagramReject> {
        let wire = self
            .connection
            .read_datagram()
            .await
            .map_err(|_| crate::DatagramReject::TransportFailed)?;
        decode_inbound_datagram(&wire)
    }

    pub fn pop_udp_datagram(
        &self,
        session: &mut ControlSession,
        channel_id: [u8; 16],
    ) -> Result<Option<Vec<u8>>, crate::DatagramReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(crate::DatagramReject::ConnectionMismatch);
        }
        session.pop_udp_datagram(channel_id)
    }

    pub fn preflight_same_edge_resume(
        &self,
        manager: &mut crate::SameEdgeResumeManager,
        handle: &crate::ResumeHandle,
        session: &mut ControlSession,
        monotonic_now: u64,
    ) -> Result<crate::ResumePreflight, crate::ResumeReject> {
        self.require_live_resume_connection(session, None)?;
        manager.preflight_same_edge(handle, session, monotonic_now)
    }

    pub fn accept_route_open_for_resume(
        &self,
        manager: &mut crate::SameEdgeResumeManager,
        preflight: &crate::ResumePreflight,
        session: &mut ControlSession,
        envelope: &CoreV02Envelope,
        monotonic_now: u64,
    ) -> Result<crate::ActiveChannel, crate::ResumeAdmissionReject> {
        self.require_live_resume_connection(session, None)
            .map_err(crate::ResumeAdmissionReject::Resume)?;
        manager
            .prepare_resume_admission(preflight, session, monotonic_now)
            .map_err(crate::ResumeAdmissionReject::Resume)?;
        let channel = session
            .accept_route_open(envelope)
            .map_err(crate::ResumeAdmissionReject::Session)?;
        manager.commit_resume_admission(preflight, channel.channel_id);
        Ok(channel)
    }

    pub fn consume_same_edge_resume(
        &self,
        manager: &mut crate::SameEdgeResumeManager,
        preflight: &crate::ResumePreflight,
        session: &mut ControlSession,
        new_channel_id: [u8; 16],
        monotonic_now: u64,
        unix_now: u64,
    ) -> Result<crate::ResumeCorrelation, crate::ResumeReject> {
        let owns_admission = manager.owns_resume_admission(preflight, new_channel_id);
        let result = self
            .require_live_resume_connection(session, Some(new_channel_id))
            .and_then(|_| {
                manager.consume(preflight, session, new_channel_id, monotonic_now, unix_now)
            });
        if result.is_err() && owns_admission {
            manager.retire_failed_admission(preflight);
            session.rollback_resume_admission(new_channel_id)?;
        }
        result
    }

    fn require_live_resume_connection(
        &self,
        session: &mut ControlSession,
        channel_id: Option<[u8; 16]>,
    ) -> Result<(), crate::ResumeReject> {
        if !session.matches_connection(&self.binding_capability) {
            session.audit_resume_session_reject(
                channel_id,
                crate::AuditReason::FreshAuthorizationRequired,
            )?;
            return Err(crate::ResumeReject::FreshAuthorizationRequired);
        }
        if self.connection.close_reason().is_some() {
            session.audit_resume_session_reject(channel_id, crate::AuditReason::InvalidState)?;
            return Err(crate::ResumeReject::Ineligible);
        }
        Ok(())
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

    async fn open_application_stream(&self) -> Result<ApplicationStream, TransportError> {
        let (send, receive) = self
            .connection
            .open_bi()
            .await
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        Ok(application_stream(send, receive))
    }

    pub async fn open_session_stream(
        &self,
        permit: &ApplicationStreamPermit,
    ) -> Result<ApplicationStream, TransportError> {
        if !self.binding_capability.matches(&permit.binding_capability) {
            return Err(TransportError::ApplicationStreamRejected);
        }
        let stream = self.open_application_stream().await?;
        if stream.id != permit.stream_id {
            let _ = stream.reject().await;
            return Err(TransportError::ApplicationStreamRejected);
        }
        self.tracked_streams.track(permit.channel_id, &stream);
        Ok(stream)
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
    ) -> Result<crate::SessionDrainEnforcement, SessionReject> {
        if !session.matches_connection(&self.binding_capability) {
            return Err(SessionReject::ConnectionMismatch);
        }
        let mut audit_integrity = crate::AuditIntegrity::Recorded;
        for channel_id in session.due_draining_channels(monotonic_now) {
            let channel_result = session.enforce_channel_drain(channel_id, monotonic_now)?;
            if matches!(channel_result, crate::DrainEnforcement::Enforced { .. }) {
                self.tracked_streams.reset_channel(&channel_id);
            }
            if matches!(
                channel_result,
                crate::DrainEnforcement::Enforced {
                    audit_integrity: crate::AuditIntegrity::Failed,
                }
            ) {
                audit_integrity = crate::AuditIntegrity::Failed;
            }
        }
        match session.enforce_session_drain(monotonic_now)? {
            crate::DrainEnforcement::Pending => {
                Ok(crate::SessionDrainEnforcement::Pending { audit_integrity })
            }
            crate::DrainEnforcement::Enforced {
                audit_integrity: session_audit_integrity,
            } => {
                if session_audit_integrity == crate::AuditIntegrity::Failed {
                    audit_integrity = crate::AuditIntegrity::Failed;
                }
                self.tracked_streams.reset_all();
                self.connection
                    .close(VarInt::from_u32(1), b"session drain deadline");
                Ok(crate::SessionDrainEnforcement::Enforced { audit_integrity })
            }
        }
    }
}

fn decode_inbound_datagram(wire: &[u8]) -> Result<crate::DatagramFrame, crate::DatagramReject> {
    crate::decode_datagram_frame(wire, MAX_LOCAL_ENCODED_DATAGRAM_BYTES)
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

#[cfg(test)]
mod datagram_adapter_tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn live_exporter_supplies_canonical_context_for_rustls_to_hash_once() {
        let context = ServiceChannelContext {
            session_id: [0x01; 16],
            source_edge_id: "source.edge",
            destination_edge_id: "destination.edge",
            channel_id: [0x02; 16],
            route_id: [0x03; 16],
            route_grant_digest: [0x04; 32],
            service_id: "service.example",
            transport: "tcp",
            port: 443,
            policy_hash: [0x05; 32],
            client_nonce: [0x06; 32],
            edge_nonce: [0x07; 32],
        };
        let expected = crate::canonical_service_channel_context(&context).unwrap();

        assert_eq!(live_exporter_context(&context).unwrap(), expected);
    }

    #[test]
    fn live_channel_quota_rejects_bytes_beyond_eight_mib() {
        let quota = Arc::new(ChannelByteQuota::default());
        let first = quota.reserve(8 * 1_048_576).expect("eight MiB admitted");
        assert!(matches!(
            quota.reserve(1),
            Err(TransportError::ApplicationPayloadTooLarge)
        ));
        drop(first);
        assert!(quota.reserve(1).is_ok());
    }

    #[test]
    fn live_channel_quota_remains_held_until_explicit_payload_release() {
        let quota = Arc::new(ChannelByteQuota::default());
        let inbound = HeldChannelBytes::default();
        for _ in 0..8 {
            inbound.retain(quota.reserve(1_048_576).expect("one MiB admitted"));
        }
        assert!(matches!(
            quota.reserve(1),
            Err(TransportError::ApplicationPayloadTooLarge)
        ));
        inbound.release();

        let outbound = HeldChannelBytes::default();
        for _ in 0..8 {
            outbound.retain(quota.reserve(1_048_576).expect("one MiB admitted"));
        }
        assert!(matches!(
            quota.reserve(1),
            Err(TransportError::ApplicationPayloadTooLarge)
        ));
        outbound.release();
        assert!(quota.reserve(1_048_576).is_ok());
    }

    #[allow(dead_code)]
    mod support {
        include!(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/support/mod.rs"));
    }

    #[test]
    fn inbound_decode_uses_the_exact_local_profile_maximum() {
        let wire = crate::encode_datagram_frame(
            [0xa1; 16],
            u64::MAX,
            &[0x5a; crate::MAX_DATAGRAM_PAYLOAD],
            usize::MAX,
        )
        .unwrap();
        assert_eq!(wire.len(), 1_235);
        assert_eq!(
            decode_inbound_datagram(&wire).unwrap().payload().len(),
            crate::MAX_DATAGRAM_PAYLOAD
        );

        let mut too_large = wire;
        too_large.push(0);
        assert_eq!(
            decode_inbound_datagram(&too_large),
            Err(crate::DatagramReject::PeerMaximum)
        );
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn raw_rejects_malformed_and_replay_without_harming_siblings() {
        let pki = support::TestPki::generate_for("source.edge", "destination.edge");
        let source_policy = PeerPolicy::new(
            EdgeRole::Source,
            EdgeRole::Destination,
            EdgeIdentity::from_dns_name("destination.edge").unwrap(),
            Duration::from_secs(2),
            Duration::from_secs(10),
        )
        .unwrap();
        let destination_policy = PeerPolicy::new(
            EdgeRole::Destination,
            EdgeRole::Source,
            EdgeIdentity::from_dns_name("source.edge").unwrap(),
            Duration::from_secs(2),
            Duration::from_secs(10),
        )
        .unwrap();
        let source_config =
            crate::build_client_config(source_policy, pki.source_material()).unwrap();
        let destination_config =
            crate::build_server_config(destination_policy, pki.destination_material()).unwrap();
        let listener = TransportListener::bind(
            destination_config,
            SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
        )
        .unwrap();
        let address = listener.local_addr().unwrap();
        let (source, destination) =
            tokio::join!(connect(source_config, address), listener.accept_one());
        let source = source.unwrap();
        let destination = destination.unwrap();

        assert!(source.connection.max_datagram_size().is_some());
        assert!(destination.connection.max_datagram_size().is_some());

        let channel_a = [0xa1; 16];
        let channel_b = [0xb2; 16];
        let valid_a = crate::encode_datagram_frame(channel_a, 1, b"target", usize::MAX).unwrap();
        let mut malformed_a = valid_a.clone();
        malformed_a.splice(22..23, [0x18, 0x01]);
        source
            .connection
            .send_datagram(Bytes::from(malformed_a))
            .unwrap();
        assert_eq!(
            destination.read_inbound_datagram().await,
            Err(crate::DatagramReject::InvalidFrame)
        );

        let mut gate_a = crate::DatagramGate::new(channel_a);
        source
            .connection
            .send_datagram(Bytes::from(valid_a.clone()))
            .unwrap();
        let first_a = destination.read_inbound_datagram().await.unwrap();
        assert_eq!(
            gate_a.receive(first_a, 0, |_| Ok(())),
            Ok(crate::DatagramReceive::Queued)
        );
        source
            .connection
            .send_datagram(Bytes::from(valid_a))
            .unwrap();
        let replay_a = destination.read_inbound_datagram().await.unwrap();
        assert_eq!(
            gate_a.receive(replay_a, 0, |_| Ok(())),
            Err(crate::DatagramReject::Replay)
        );

        let mut gate_b = crate::DatagramGate::new(channel_b);
        let valid_b = crate::encode_datagram_frame(channel_b, 1, b"sibling", usize::MAX).unwrap();
        source
            .connection
            .send_datagram(Bytes::from(valid_b))
            .unwrap();
        let frame_b = destination.read_inbound_datagram().await.unwrap();
        assert_eq!(
            gate_b.receive(frame_b, 0, |_| Ok(())),
            Ok(crate::DatagramReceive::Queued)
        );
        assert_eq!(gate_b.pop(|_| Ok(())), Ok(Some(b"sibling".to_vec())));

        let mut held_streams = Vec::new();
        for _ in 0..64 {
            let (mut send, receive) =
                tokio::time::timeout(Duration::from_secs(1), source.connection.open_bi())
                    .await
                    .expect("transport admits 64 simultaneously open application streams")
                    .unwrap();
            // Quinn opens streams lazily on first use; materialize the stream
            // before waiting for the peer's accept_bi future.
            send.write_all(&[0]).await.unwrap();
            let accepted =
                tokio::time::timeout(Duration::from_secs(1), destination.connection.accept_bi())
                    .await
                    .expect("peer observes each held application stream")
                    .unwrap();
            held_streams.push(((send, receive), accepted));
        }
        drop(held_streams);

        let quota = Arc::new(ChannelByteQuota::default());
        let held = HeldChannelBytes::default();
        for _ in 0..8 {
            let (mut send, _) = source.connection.open_bi().await.unwrap();
            let sender = tokio::spawn(async move {
                send.write_all(&vec![0x5a; 1_048_576]).await.unwrap();
                send.finish().unwrap();
            });
            let (_, mut receive) = destination.connection.accept_bi().await.unwrap();
            let received = read_live_payload(&mut receive, Some(Arc::clone(&quota))).await;
            sender.await.unwrap();
            let (payload, reservations) = received.expect("one MiB returned");
            assert_eq!(payload.len(), 1_048_576);
            held.retain_all(reservations);
        }

        let (mut rejected_send, _) = source.connection.open_bi().await.unwrap();
        let rejected_sender = tokio::spawn(async move {
            rejected_send
                .write_all(&vec![0x5a; 1_048_576])
                .await
                .unwrap();
            rejected_send.finish().unwrap();
        });
        let (_, mut rejected_receive) = destination.connection.accept_bi().await.unwrap();
        let rejected = read_live_payload(&mut rejected_receive, Some(Arc::clone(&quota))).await;
        let _ = rejected_receive.stop(VarInt::from_u32(2));
        let _ = rejected_sender.await;
        assert!(matches!(
            rejected,
            Err(TransportError::ApplicationPayloadTooLarge)
        ));

        held.release();
        let (mut released_send, _) = source.connection.open_bi().await.unwrap();
        let released_sender = tokio::spawn(async move {
            released_send
                .write_all(&vec![0x5a; 1_048_576])
                .await
                .unwrap();
            released_send.finish().unwrap();
        });
        let (_, mut released_receive) = destination.connection.accept_bi().await.unwrap();
        let released = read_live_payload(&mut released_receive, Some(Arc::clone(&quota))).await;
        released_sender.await.unwrap();
        assert_eq!(released.expect("quota released").0.len(), 1_048_576);

        let (mut source_send, mut source_receive) = source.connection.open_bi().await.unwrap();
        source_send.write_all(b"tcp-sibling").await.unwrap();
        source_send.finish().unwrap();
        let (mut destination_send, mut destination_receive) =
            destination.connection.accept_bi().await.unwrap();
        let received = destination_receive.read_to_end(64).await.unwrap();
        assert_eq!(received, b"tcp-sibling");
        destination_send.write_all(&received).await.unwrap();
        destination_send.finish().unwrap();
        assert_eq!(
            source_receive.read_to_end(64).await.unwrap(),
            b"tcp-sibling"
        );

        source.close().await.unwrap();
        destination.close().await.unwrap();
        listener.close().await.unwrap();
    }
}
