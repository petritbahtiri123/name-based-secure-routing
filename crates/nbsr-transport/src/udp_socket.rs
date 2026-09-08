use std::io;
use std::net::{SocketAddr, UdpSocket};

pub(crate) fn bind_receive_socket(address: SocketAddr) -> io::Result<UdpSocket> {
    let socket = UdpSocket::bind(address)?;
    // Windows' measured 64 KiB default dropped admission datagrams in AFD.
    // Bound the per-listener buffer to 1 MiB, enough for the observed 512-peer
    // burst of <=1452-byte datagrams, without changing QUIC/application credit.
    #[cfg(windows)]
    socket2::SockRef::from(&socket).set_recv_buffer_size(1024 * 1024)?;
    #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
    {
        let setting = match std::env::var("NBSR_BENCH_UDP_RECEIVE_BUFFER_BYTES") {
            Ok(value) => Some(value),
            Err(std::env::VarError::NotPresent) => None,
            Err(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "invalid benchmark buffer setting",
                ));
            }
        };
        if let Some(bytes) = benchmark_receive_buffer_bytes(setting.as_deref())? {
            let socket_ref = socket2::SockRef::from(&socket);
            let before = socket_ref.recv_buffer_size()?;
            if before < bytes {
                socket_ref.set_recv_buffer_size(bytes)?;
                if socket_ref.recv_buffer_size()? < before {
                    return Err(io::Error::other(
                        "benchmark buffer request reduced receive capacity",
                    ));
                }
            }
        }
    }
    Ok(socket)
}

#[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
fn benchmark_receive_buffer_bytes(setting: Option<&str>) -> io::Result<Option<usize>> {
    match setting {
        None => Ok(None),
        Some("1048576") => Ok(Some(1024 * 1024)),
        Some(_) => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "unsupported benchmark buffer request",
        )),
    }
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
    #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
    fn linux_benchmark_buffer_request_is_explicit_and_bounded() {
        assert_eq!(benchmark_receive_buffer_bytes(None).unwrap(), None);
        assert_eq!(
            benchmark_receive_buffer_bytes(Some("1048576")).unwrap(),
            Some(1024 * 1024)
        );
        for value in ["", "0", "-1", "1048577", "garbage"] {
            assert!(benchmark_receive_buffer_bytes(Some(value)).is_err());
        }
    }

    #[test]
    fn bind_conflict_remains_an_error() {
        let socket = bind_receive_socket("127.0.0.1:0".parse().unwrap()).unwrap();
        assert!(bind_receive_socket(socket.local_addr().unwrap()).is_err());
    }
}
