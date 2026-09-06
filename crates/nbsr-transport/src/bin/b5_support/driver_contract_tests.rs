use super::driver::{self, Driver};
use std::sync::Arc;

#[test]
#[ignore = "isolated timer diagnostic; not a benchmark acceptance test"]
fn isolated_ten_ms_timer_diagnostic() {
    use std::time::{Duration, Instant};
    for mode in ["tokio", "std"] {
        for repeat in 1..=3 {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap();
            let rows = runtime.block_on(async {
                let origin = Instant::now();
                let mut rows = Vec::with_capacity(100);
                for _ in 0..100 {
                    let before = origin.elapsed().as_nanos() as u64;
                    let deadline = (before / 10_000_000 + 1) * 10_000_000;
                    let delay = Duration::from_nanos(deadline - before);
                    if mode == "tokio" {
                        tokio::time::sleep(delay).await;
                    } else {
                        std::thread::sleep(delay);
                    }
                    rows.push((before, deadline, origin.elapsed().as_nanos() as u64));
                }
                rows
            });
            println!(
                "{}",
                serde_json::json!({"schema":"nbsr-b5-isolated-timer-diagnostic-v1", "mode":mode,"repeat":repeat,"rows":rows})
            );
        }
    }
}

fn args() -> Vec<String> {
    [
        "source",
        "--b5-rate-numerator",
        "200",
        "--b5-rate-denominator",
        "1",
        "--p2a-groups",
        "2",
        "--p2a-streams",
        "1",
        "--p2a-outstanding-per-stream",
        "1",
        "--payload-bytes",
        "16384",
        "--p2a-duration-seconds",
        "30.0",
        "--p2a-progress-seconds",
        "1",
        "--p2a-runtime-workers",
        "1",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect()
}

#[test]
fn absent_new_flags_preserves_default_and_exact_decimal_duration_parses() {
    assert!(
        driver::prepare(["source".to_owned(), "--legacy-unknown".to_owned()])
            .unwrap()
            .is_none()
    );
    let run = driver::prepare(args()).unwrap().unwrap();
    assert_eq!(run.config.duration_ns, 30_000_000_000);
    assert_eq!(run.partition(0, 0).unwrap(), 0);
    assert_eq!(run.partition(1, 0).unwrap(), 1);
    assert!(run.partition(2, 0).is_err());
}

#[test]
fn paced_cooldown_cannot_be_silently_accepted() {
    let mut values = args();
    values.extend(["--p2a-cooldown-seconds".into(), "1".into()]);
    assert!(driver::prepare(values).is_err());
    let mut values = args();
    values.extend(["--p2a-cooldown-seconds".into(), "0.0".into()]);
    assert!(driver::prepare(values).unwrap().is_some());
}

#[test]
fn missing_duplicate_and_mixed_modes_are_rejected_but_warm_is_allowed() {
    for extra in [
        vec!["--b5-rate-numerator", "1"],
        vec!["--offered-rate", "1"],
        vec!["--b4-admission-rate", "1"],
        vec!["--p2a-counter-control", "127.0.0.1:1"],
        vec!["--p2a-operations-per-stream", "1"],
        vec!["--lifecycle", "cold"],
        vec!["--lifecycle-authority-dir", "fixture"],
    ] {
        let mut values = args();
        values.extend(extra.into_iter().map(str::to_owned));
        assert!(driver::prepare(values).is_err());
    }
    let mut values = args();
    values.extend(["--lifecycle".into(), "warm".into()]);
    assert!(driver::prepare(values).unwrap().is_some());
    assert!(driver::prepare(["--b5-rate-numerator".into(), "1".into()]).is_err());
    assert!(driver::prepare(["--b5-rate-numerator".into()]).is_err());
}

#[test]
fn bounds_nonfinite_fractional_rate_and_budget_overflow_fail_closed() {
    for (flag, bad) in [
        ("--p2a-duration-seconds", "7200.000000001"),
        ("--p2a-duration-seconds", "NaN"),
        ("--p2a-progress-seconds", "0.9"),
        ("--p2a-runtime-workers", "2"),
        ("--payload-bytes", "8192"),
        ("--b5-rate-numerator", "1.2"),
        ("--b5-rate-denominator", "0"),
        ("--b5-rate-numerator", "18446744073709551615"),
    ] {
        let mut values = args();
        let index = values.iter().position(|s| s == flag).unwrap();
        values[index + 1] = bad.into();
        assert!(driver::prepare(values).is_err(), "{flag}={bad}");
    }
}

#[test]
fn capacity_covers_two_intervals_edge_and_outstanding() {
    // ceil((ceil(200 * 2.01) + 2 partitions + 2 outstanding) / 64) + 1 carry.
    let run = driver::prepare(args()).unwrap().unwrap();
    assert_eq!(run.config.sample_capacity, 8);
}

fn short_driver() -> Arc<Driver> {
    let parsed = driver::prepare(args()).unwrap().unwrap();
    let mut config = parsed.config.clone();
    config.duration_ns = 1_000_000;
    config.progress_ns = 1_000_000;
    Driver::from_config(config).unwrap()
}

#[tokio::test(flavor = "current_thread")]
async fn publisher_final_matches_progress_and_only_follows_all_drains() {
    let driver = short_driver();
    driver.run.ready(0).unwrap();
    driver.run.ready(1).unwrap();
    tokio::time::sleep(std::time::Duration::from_millis(3)).await;
    driver.run.drained(0).unwrap();
    driver.run.drained(1).unwrap();
    let mut bytes = Vec::new();
    driver.publish_to(&mut bytes).await.unwrap();
    let line: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(line["schema"], "nbsr-b5-grouped-progress-v1");
    assert_eq!(line.as_object().unwrap().len(), 27);
    assert_eq!(line["phase"], "mixed");
    assert_eq!(line["sample_count"], 0);
    assert!(line["p99_latency_ns"].is_null());
    assert!(driver.run.status().postflight_allowed);
    let final_line: serde_json::Value =
        serde_json::from_str(&driver.final_record_after_joins("{}").unwrap()).unwrap();
    assert_eq!(final_line["schema"], "nbsr-b5-grouped-final-v1");
    assert_eq!(final_line.as_object().unwrap().len(), 21);
    assert_eq!(final_line["completed"], line["completed"]);
    assert_eq!(
        final_line["measurement_duration_ns"].as_u64().unwrap()
            + final_line["drain_duration_ns"].as_u64().unwrap(),
        line["elapsed_ns"].as_u64().unwrap()
    );
}

#[tokio::test(flavor = "current_thread")]
async fn sink_flush_failure_and_stream_guard_release_waiters() {
    struct BrokenFlush;
    impl std::io::Write for BrokenFlush {
        fn write(&mut self, value: &[u8]) -> std::io::Result<usize> {
            Ok(value.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Err(std::io::Error::other("flush failure"))
        }
    }
    let driver = short_driver();
    driver.run.ready(0).unwrap();
    driver.run.ready(1).unwrap();
    tokio::time::sleep(std::time::Duration::from_millis(3)).await;
    driver.run.drained(0).unwrap();
    driver.run.drained(1).unwrap();
    assert!(driver.publish_to(&mut BrokenFlush).await.is_err());
    assert!(driver.run.wait_postflight().await.is_err());
    assert!(driver.final_record_after_joins("{}").is_err());

    let driver = short_driver();
    driver.idle_until(0).await.unwrap();
    let guard = driver.failure_guard();
    drop(guard);
    assert!(driver.idle_until(1_000_000_000).await.is_err());
}

#[test]
fn publisher_thread_propagates_failure_before_readiness_without_output() {
    let driver = short_driver();
    let handle = driver.start_publisher().unwrap();
    driver.run.fail();
    assert!(handle.join().unwrap().is_err());
    assert!(driver.start_publisher().is_err());
}
