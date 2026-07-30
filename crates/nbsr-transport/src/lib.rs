#![forbid(unsafe_code)]

mod config;
mod error;

pub use config::{EdgeIdentity, EdgeRole, PeerPolicy};
pub use error::TransportError;

pub const ALPN: &[u8] = b"nbsr-quic-1";
