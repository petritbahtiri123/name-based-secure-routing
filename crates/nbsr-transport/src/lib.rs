//! Safe callers cannot construct or activate channel-registry state directly.
//!
//! ```compile_fail
//! use nbsr_transport::ChannelRegistry;
//! ```

#![forbid(unsafe_code)]

mod admission;
mod channel_registry;
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
pub use stream_gate::{StreamGate, StreamOpenRequest, StreamReject};

pub const ALPN: &[u8] = b"nbsr-quic-1";
