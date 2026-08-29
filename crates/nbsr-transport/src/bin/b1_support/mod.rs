use std::io::{BufRead, BufReader, Error, ErrorKind, Write};
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum MeasurementMode {
    Duration(f64),
    OperationsPerStream(u64),
}

pub(crate) fn measurement_mode(
    duration_seconds: Option<f64>,
    operations_per_stream: Option<u64>,
) -> Result<MeasurementMode, Error> {
    match (duration_seconds, operations_per_stream) {
        (Some(duration), None) if duration.is_finite() && duration > 0.0 => {
            Ok(MeasurementMode::Duration(duration))
        }
        (None, Some(operations)) if operations > 0 => {
            Ok(MeasurementMode::OperationsPerStream(operations))
        }
        _ => Err(Error::new(
            ErrorKind::InvalidInput,
            "exactly one positive P2A measurement bound is required",
        )),
    }
}

pub(crate) fn counter_phase(endpoint: Option<SocketAddr>, phase: &str) -> Result<(), Error> {
    let Some(endpoint) = endpoint else {
        return Ok(());
    };
    if !matches!(
        phase,
        "setup-complete" | "measurement-start" | "measurement-stop"
    ) {
        return Err(Error::new(ErrorKind::InvalidInput, "invalid counter phase"));
    }
    let mut connection = TcpStream::connect_timeout(&endpoint, Duration::from_secs(2))?;
    connection.set_read_timeout(Some(Duration::from_secs(2)))?;
    connection.set_write_timeout(Some(Duration::from_secs(2)))?;
    connection.write_all(phase.as_bytes())?;
    connection.write_all(b"\n")?;
    let mut response = String::new();
    BufReader::new(connection).read_line(&mut response)?;
    if !response.starts_with("{\"status\":\"ok\"") {
        return Err(Error::new(
            ErrorKind::PermissionDenied,
            "counter phase was not acknowledged",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{MeasurementMode, counter_phase, measurement_mode};
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn phase_control_sends_exact_marker_and_requires_acknowledgment() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let endpoint = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut connection, _) = listener.accept().unwrap();
            let mut marker = String::new();
            BufReader::new(connection.try_clone().unwrap())
                .read_line(&mut marker)
                .unwrap();
            assert_eq!(marker, "measurement-start\n");
            connection.write_all(b"{\"status\":\"ok\"}\n").unwrap();
        });

        counter_phase(Some(endpoint), "measurement-start").unwrap();
        server.join().unwrap();
    }

    #[test]
    fn phase_control_fails_closed_without_positive_acknowledgment() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let endpoint = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut connection, _) = listener.accept().unwrap();
            let mut marker = String::new();
            BufReader::new(connection.try_clone().unwrap())
                .read_line(&mut marker)
                .unwrap();
            connection.write_all(b"{\"status\":\"error\"}\n").unwrap();
        });

        assert!(counter_phase(Some(endpoint), "setup-complete").is_err());
        server.join().unwrap();
    }

    #[test]
    fn measurement_mode_requires_exactly_one_positive_bound() {
        assert_eq!(
            measurement_mode(Some(3.0), None).unwrap(),
            MeasurementMode::Duration(3.0)
        );
        assert_eq!(
            measurement_mode(None, Some(10)).unwrap(),
            MeasurementMode::OperationsPerStream(10)
        );
        assert!(measurement_mode(None, None).is_err());
        assert!(measurement_mode(Some(3.0), Some(10)).is_err());
        assert!(measurement_mode(Some(0.0), None).is_err());
        assert!(measurement_mode(None, Some(0)).is_err());
    }
}
