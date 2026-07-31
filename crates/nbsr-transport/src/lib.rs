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
//! let _ = nbsr_transport::ControlSession::stream_gate;
//! ```
//!
//! ```compile_fail
//! let _ = nbsr_transport::AuthenticatedConnection::accept_application_stream;
//! ```

#![forbid(unsafe_code)]

mod admission;
mod channel_binding;
mod channel_registry;
mod channel_streams;
mod config;
mod core_v02;
mod error;
mod quinn_adapter;
mod session;
mod stream_gate;

pub use admission::{
    ActiveChannel, AdmissionPolicy, AdmissionReject, AuthorizedServicePolicy, DestinationAdmission,
    RouteGrantClaims, RouteOpenRequest,
};
pub use channel_binding::{
    ServiceChannelBinding, ServiceChannelContext, ServiceChannelExporterError,
    canonical_service_channel_context, derive_service_channel_exporter_fixture,
};
pub use channel_registry::ChannelLimits;
pub use config::{
    ClientEndpointConfig, EdgeIdentity, EdgeRole, PeerPolicy, ServerEndpointConfig, TlsMaterial,
    build_client_config, build_server_config,
};
pub use core_v02::{
    CoreV02Envelope, CoreV02Limits, CoreV02MessageType, CoreV02Reject, RouteGrantIssuer,
    ValidatedRouteGrant, decode_control_envelope, validate_route_grant_sign1,
};
pub use error::TransportError;
pub use quinn_adapter::{
    ApplicationStream, AuthenticatedConnection, ControlStream, TransportListener, connect,
};
pub use session::{ControlSession, SessionReject};
pub use stream_gate::{StreamOpenRequest, StreamReject};

pub const ALPN: &[u8] = b"nbsr-quic-1";
