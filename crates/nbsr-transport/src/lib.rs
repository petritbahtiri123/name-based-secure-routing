#![forbid(unsafe_code)]

mod config;
mod error;

pub use config::{
    ClientEndpointConfig, EdgeIdentity, EdgeRole, PeerPolicy, ServerEndpointConfig, TlsMaterial,
    build_client_config, build_server_config,
};
pub use error::TransportError;

pub const ALPN: &[u8] = b"nbsr-quic-1";
