//! Bounded B3 acceptance concurrency. Never changes transport deadlines.
pub(crate) fn parse(
    serial: bool,
    connections: usize,
    requested: Option<&str>,
) -> Result<usize, &'static str> {
    let Some(requested) = requested else {
        // A stalled handshake must not occupy the only admission slot.
        // The explicit one-slot override remains available for comparisons.
        return Ok(if serial {
            connections.min(2)
        } else {
            connections
        });
    };
    if !serial || connections < 2 {
        return Err("accept window override requires concurrent B3 memory holds");
    }
    if !matches!(requested, "1" | "2" | "4" | "8" | "16" | "32") {
        return Err("accept window must be 1, 2, 4, 8, 16, or 32");
    }
    let window = requested
        .parse::<usize>()
        .expect("validated window literal");
    if window > connections {
        return Err("accept window exceeds offered connections");
    }
    Ok(window)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn explicit_two_accepts_preserve_an_independent_progress_slot() {
        assert_eq!(parse(true, 2048, Some("2")), Ok(2));
    }

    #[test]
    fn omitted_override_bounds_b3_to_two_without_changing_b4() {
        assert_eq!(parse(true, 2048, None), Ok(2));
        assert_eq!(parse(true, 1, None), Ok(1));
        assert_eq!(parse(true, 2048, Some("1")), Ok(1));
        assert_eq!(parse(false, 512, None), Ok(512));
    }

    #[test]
    fn malformed_unbounded_or_cross_workload_overrides_fail_closed() {
        for requested in ["", "0", "3", "64", "01", "-1", "2 "] {
            assert!(parse(true, 2048, Some(requested)).is_err(), "{requested}");
        }
        assert!(parse(false, 512, Some("2")).is_err());
        assert!(parse(true, 1, Some("2")).is_err());
        assert!(parse(true, 1, Some("1")).is_err());
        assert!(parse(true, 2, Some("4")).is_err());
    }
}
