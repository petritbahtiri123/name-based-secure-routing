use std::io;
use std::net::{SocketAddr, UdpSocket};

pub(crate) fn bind_receive_socket(address: SocketAddr) -> io::Result<UdpSocket> {
    let socket = UdpSocket::bind(address)?;
    // Windows' measured 64 KiB default dropped admission datagrams in AFD.
    // Bound the per-listener buffer to 1 MiB, enough for the observed 512-peer
    // burst of <=1452-byte datagrams, without changing QUIC/application credit.
    #[cfg(windows)]
    socket2::SockRef::from(&socket).set_recv_buffer_size(1024 * 1024)?;
    Ok(socket)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(windows)]
    fn receive_buffer_covers_measured_admission_burst() {
        let socket = bind_receive_socket("127.0.0.1:0".parse().unwrap()).unwrap();
        let bytes = socket2::SockRef::from(&socket).recv_buffer_size().unwrap();
        assert!(bytes >= 1024 * 1024, "actual SO_RCVBUF={bytes}");
    }

    #[test]
    fn bind_conflict_remains_an_error() {
        let socket = bind_receive_socket("127.0.0.1:0".parse().unwrap()).unwrap();
        assert!(bind_receive_socket(socket.local_addr().unwrap()).is_err());
    }
}
