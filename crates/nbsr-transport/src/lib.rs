//! Safe callers cannot construct or activate channel-registry state directly.
//!
//! ```compile_fail
//! use nbsr_transport::ChannelRegistry;
//! ```
//!
//! Application-stream admission is available only through an established
//! [`ControlSession`]. Internal per-stream gates and the legacy standalone
//! acceptance path are not public bypass APIs.
//!
//! ```compile_fail
//! use nbsr_transport::StreamGate;
//! ```
//!
//! ```compile_fail
//! use nbsr_transport::DatagramGate;
//! ```
//!
//! ```compile_fail
//! let _ = nbsr_transport::ControlSession::stream_gate;
//! ```
//!
//! ```compile_fail
//! let _ = nbsr_transport::AuthenticatedConnection::accept_application_stream;
//! ```
//!
//! Live channel bindings expose neither a constructor nor their bytes.
//!
//! ```compile_fail
//! use nbsr_transport::ChannelBinding;
//! let _ = ChannelBinding([0_u8; 32]);
//! ```
//!
//! ```compile_fail
//! fn expose(binding: &nbsr_transport::ChannelBinding) {
//!     let _ = binding.as_bytes();
//! }
//! ```
//!
//! Terminal channel mutation is a connection-owned transport operation. A
//! caller cannot bypass tracked-stream reset through [`ControlSession`].
//!
//! ```compile_fail
//! fn bypass_revoke(session: &mut nbsr_transport::ControlSession) {
//!     let _ = session.revoke_channel([0x11; 16], 0);
//! }
//! ```
//!
//! ```compile_fail
//! fn bypass_close(session: &mut nbsr_transport::ControlSession) {
//!     let _ = session.close_channel([0x11; 16], 0);
//! }
//! ```
//!
//! Resume-store consume remains behind a live authenticated connection; a
//! caller cannot mutate it directly with only a retained session object.
//!
//! ```compile_fail
//! fn bypass_resume(
//!     manager: &mut nbsr_transport::SameEdgeResumeManager,
//!     preflight: &nbsr_transport::ResumePreflight,
//!     session: &mut nbsr_transport::ControlSession,
//! ) {
//!     let _ = manager.consume(preflight, session, [0x22; 16]);
//! }
//! ```
//!
//! Resume authority APIs accept no caller-selected time.
//!
//! ```compile_fail
//! fn inject_resume_time(
//!     connection: &nbsr_transport::AuthenticatedConnection,
//!     manager: &mut nbsr_transport::SameEdgeResumeManager,
//!     handle: &nbsr_transport::ResumeHandle,
//!     session: &mut nbsr_transport::ControlSession,
//! ) {
//!     let _ = connection.preflight_same_edge_resume(manager, handle, session, 0);
//! }
//! ```
//!
//! ```compile_fail
//! fn inject_issue_time(
//!     manager: &mut nbsr_transport::SameEdgeResumeManager,
//!     session: &mut nbsr_transport::ControlSession,
//!     handle: nbsr_transport::ResumeHandle,
//! ) {
//!     let _ = manager.issue(session, [0x11; 16], handle, 3_599, 0);
//! }
//! ```
//!
//! ```compile_fail
//! fn inject_later_stage_time(
//!     connection: &nbsr_transport::AuthenticatedConnection,
//!     manager: &mut nbsr_transport::SameEdgeResumeManager,
//!     preflight: &nbsr_transport::ResumePreflight,
//!     session: &mut nbsr_transport::ControlSession,
//!     envelope: &nbsr_transport::CoreV02Envelope,
//! ) {
//!     let _ = connection.accept_route_open_for_resume(manager, preflight, session, envelope, 0);
//!     let _ = connection.consume_same_edge_resume(
//!         manager, preflight, session, [0x22; 16], 0, 0,
//!     );
//! }
//! ```
//!
//! Session time is transport-owned authority. External callers cannot inject a
//! clock or construct a session with caller-selected deadlines.
//!
//! ```compile_fail
//! use nbsr_transport::SessionClock;
//! ```
//!
//! ```compile_fail
//! let _ = nbsr_transport::ControlSession::new_with_clock;
//! ```
//!
//! ```compile_fail
//! let _ = nbsr_transport::ControlSession::new_with_monotonic_deadline;
//! ```

#![forbid(unsafe_code)]

#[cfg(test)]
extern crate self as nbsr_transport;

mod admission;
mod audit;
mod channel_binding;
mod channel_lifecycle;
mod channel_registry;
mod channel_streams;
mod config;
mod core_v02;
mod datagram_gate;
mod error;
mod quinn_adapter;
mod resumption;
mod session;
#[cfg(test)]
mod session_tests;
mod stream_gate;

pub use admission::{
    ActiveChannel, AdmissionPolicy, AdmissionReject, AuthorizedServicePolicy, DestinationAdmission,
    RouteGrantClaims, RouteOpenRequest,
};
pub use audit::{AuditAction, AuditEvent, AuditOutcome, AuditReason, SafeServiceId};
pub use channel_binding::{
    ChannelBinding, ServiceChannelBinding, ServiceChannelContext, ServiceChannelExporterError,
    canonical_service_channel_context, derive_service_channel_exporter_fixture,
};
pub use channel_lifecycle::{
    AuditIntegrity, ChannelState, DrainDeadline, DrainEnforcement, DrainReject, MAX_DRAIN_SECONDS,
    SessionDrainEnforcement, SessionDrainState,
};
pub use channel_registry::ChannelLimits;
pub use config::{
    ClientEndpointConfig, EdgeIdentity, EdgeRole, PeerPolicy, ServerEndpointConfig, TlsMaterial,
    build_client_config, build_server_config,
};
pub use core_v02::{
    CoreV02Envelope, CoreV02Limits, CoreV02MessageType, CoreV02Reject, RouteCloseBody,
    RouteDrainBody, RouteGrantIssuer, RouteRevokeBody, ValidatedRouteGrant,
    decode_control_envelope, validate_route_grant_sign1,
};
pub(crate) use datagram_gate::{DatagramAuditMutation, DatagramDropReason, DatagramGate};
pub use datagram_gate::{
    DatagramFrame, DatagramReceive, DatagramReject, MAX_DATAGRAM_PAYLOAD, decode_datagram_frame,
    encode_datagram_frame, max_datagram_payload,
};
pub use error::TransportError;
pub use quinn_adapter::{
    ApplicationStream, ApplicationStreamPermit, AuthenticatedConnection, ControlStream,
    TransportListener, connect,
};
pub use resumption::{
    ResumeAdmissionReject, ResumeCorrelation, ResumeHandle, ResumePreflight, ResumeReject,
    SameEdgeResumeManager, TrustProfileId,
};
pub use session::{ControlSession, MAX_SESSION_SECONDS, SessionReject};
pub use stream_gate::{StreamOpenRequest, StreamReject};

pub const ALPN: &[u8] = b"nbsr-quic-1";
