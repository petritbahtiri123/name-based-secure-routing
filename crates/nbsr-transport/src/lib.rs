#![forbid(unsafe_code)]

mod config;
mod error;
mod quinn_adapter;

pub use config::{
    ClientEndpointConfig, EdgeIdentity, EdgeRole, PeerPolicy, ServerEndpointConfig, TlsMaterial,
    build_client_config, build_server_config,
};
pub use error::TransportError;
pub use quinn_adapter::{AuthenticatedConnection, TransportListener, connect};

pub const ALPN: &[u8] = b"nbsr-quic-1";
