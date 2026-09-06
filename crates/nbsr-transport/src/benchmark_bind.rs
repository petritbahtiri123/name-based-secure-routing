//! Explicit benchmark socket placement; TLS identities are never IP addresses.
use std::net::{Ipv4Addr, SocketAddrV4};

const CLIENT: &str = "--benchmark-client-bind";
const LISTENER: &str = "--benchmark-listen";

fn concrete(address: SocketAddrV4) -> Result<SocketAddrV4, &'static str> {
    let ip = address.ip();
    if ip.is_unspecified() || ip.is_multicast() || ip.is_broadcast() {
        return Err("benchmark bind requires concrete unicast IPv4");
    }
    Ok(address)
}

pub(crate) fn validate_client(address: SocketAddrV4) -> Result<SocketAddrV4, &'static str> {
    let address = concrete(address)?;
    if address.port() != 0 {
        return Err("benchmark client bind requires ephemeral port zero");
    }
    Ok(address)
}

fn selected(
    args: impl IntoIterator<Item = String>,
    flag: &str,
) -> Result<Option<SocketAddrV4>, &'static str> {
    let args: Vec<_> = args.into_iter().collect();
    let mut selected = None;
    for (index, value) in args.iter().enumerate() {
        if value.starts_with(CLIENT) || value.starts_with(LISTENER) {
            if value != flag {
                return Err("invalid or wrong-role benchmark bind option");
            }
            if selected.is_some() {
                return Err("duplicate benchmark bind option");
            }
            let address = args
                .get(index + 1)
                .ok_or("missing benchmark bind address")?
                .parse::<SocketAddrV4>()
                .map_err(|_| "invalid IPv4 socket address")?;
            selected = Some(concrete(address)?);
        }
    }
    Ok(selected)
}

/// Resolve only local client socket placement; peer authentication is unchanged.
pub fn client_bind(args: impl IntoIterator<Item = String>) -> Result<SocketAddrV4, &'static str> {
    validate_client(selected(args, CLIENT)?.unwrap_or(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)))
}

/// Resolve an explicit listener or preserve the legacy capture-port default.
pub fn listener_bind(
    args: impl IntoIterator<Item = String>,
    capture_port: Option<&str>,
) -> Result<SocketAddrV4, &'static str> {
    let selected = selected(args, LISTENER)?;
    if selected.is_some() && capture_port.is_some() {
        return Err("explicit listener conflicts with capture port");
    }
    if let Some(address) = selected {
        return Ok(address);
    }
    let port = capture_port
        .map(str::parse::<u16>)
        .transpose()
        .map_err(|_| "invalid capture port")?
        .unwrap_or(0);
    Ok(SocketAddrV4::new(Ipv4Addr::LOCALHOST, port))
}
