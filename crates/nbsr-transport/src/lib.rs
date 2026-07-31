#![forbid(unsafe_code)]

mod admission;
mod config;
mod core_v02;
mod error;
mod quinn_adapter;

pub use admission::{
    ActiveChannel, AdmissionPolicy, AdmissionReject, DestinationAdmission, RouteGrantClaims,
    RouteOpenRequest,
};
pub use config::{
    ClientEndpointConfig, EdgeIdentity, EdgeRole, PeerPolicy, ServerEndpointConfig, TlsMaterial,
    build_client_config, build_server_config,
};
pub use core_v02::{
    CoreV02Envelope, CoreV02Limits, CoreV02MessageType, CoreV02Reject, RouteGrantIssuer,
    ValidatedRouteGrant, decode_control_envelope, validate_route_grant_sign1,
};
pub use error::TransportError;
pub use quinn_adapter::{AuthenticatedConnection, ControlStream, TransportListener, connect};

pub const ALPN: &[u8] = b"nbsr-quic-1";
