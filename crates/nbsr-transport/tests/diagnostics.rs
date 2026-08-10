use std::fs;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use nbsr_transport::diagnostics::{DestinationDiagnosticSampler, DiagnosticOwner, Diagnostics};

#[test]
fn disabled_diagnostics_do_not_account_or_retain_state() {
    let diagnostics = Diagnostics::new(false);
    diagnostics.created(DiagnosticOwner::ApplicationStream);
    diagnostics.completed(DiagnosticOwner::ApplicationStream);

    assert_eq!(diagnostics.snapshot().application_streams.created, 0);
    assert_eq!(diagnostics.snapshot().application_streams.current_live, 0);
}

#[test]
fn lifecycle_success_and_failure_are_mutually_exclusive_and_conserve() {
    let diagnostics = Diagnostics::new(true);
    diagnostics.created(DiagnosticOwner::ApplicationStream);
    diagnostics.created(DiagnosticOwner::ApplicationStream);
    diagnostics.completed(DiagnosticOwner::ApplicationStream);
    diagnostics.failed(DiagnosticOwner::ApplicationStream);

    let metric = diagnostics.snapshot().application_streams;
    assert_eq!(metric.created, 2);
    assert_eq!(metric.completed, 1);
    assert_eq!(metric.failed_or_cancelled, 1);
    assert_eq!(metric.current_live, 0);
    assert_eq!(metric.high_water_live, 2);
    assert_eq!(
        metric.created - metric.completed - metric.failed_or_cancelled,
        metric.current_live
    );
}

#[test]
fn collection_snapshot_separates_entries_from_retained_capacity() {
    let diagnostics = Diagnostics::new(true);
    diagnostics.observe_collection(DiagnosticOwner::StreamRegistry, 3, 8);
    diagnostics.observe_collection(DiagnosticOwner::StreamRegistry, 1, 8);

    let metric = diagnostics.snapshot().stream_registry;
    assert_eq!(metric.current_entries, 1);
    assert_eq!(metric.high_water_entries, 3);
    assert_eq!(metric.retained_capacity, 8);
    assert_eq!(metric.high_water_retained_capacity, 8);
}

#[test]
fn destination_sampler_writes_bounded_snapshots_and_joins_cleanly() {
    let diagnostics = Box::leak(Box::new(Diagnostics::new(true)));
    let path = std::env::temp_dir().join(format!(
        "nbsr-p1b-sampler-{}-{}.ndjson",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    diagnostics.created(DiagnosticOwner::TransportSession);
    let sampler =
        DestinationDiagnosticSampler::start(&path, diagnostics, Duration::from_millis(10));
    diagnostics.observe_collection(DiagnosticOwner::ReplayState, 7, 14);
    std::thread::sleep(Duration::from_millis(35));
    let outcome = sampler.stop_and_join();

    assert!(outcome.output_opened);
    assert!(!outcome.io_failed);
    assert!(outcome.snapshots_written >= 2);
    let output = fs::read_to_string(&path).unwrap();
    let lines = output.lines().collect::<Vec<_>>();
    assert_eq!(lines.len() as u64, outcome.snapshots_written);
    assert!(
        lines
            .iter()
            .all(|line| line.contains("\"role\":\"destination\""))
    );
    assert!(
        lines
            .iter()
            .any(|line| line.contains("\"replay_state_current_entries\":7"))
    );
    assert!(!output.contains("ticket"));
    assert!(!output.contains("nonce"));
    assert!(!output.contains("payload"));
    assert!(!output.contains("request_id"));
    fs::remove_file(path).unwrap();
}

#[test]
fn destination_sampler_file_failure_is_non_fatal_and_joinable() {
    let diagnostics = Box::leak(Box::new(Diagnostics::new(true)));
    let impossible = std::env::temp_dir().join(format!(
        "nbsr-p1b-missing-{}/diagnostics.ndjson",
        std::process::id()
    ));
    let outcome =
        DestinationDiagnosticSampler::start(&impossible, diagnostics, Duration::from_millis(10))
            .stop_and_join();

    assert!(!outcome.output_opened);
    assert!(outcome.io_failed);
    assert_eq!(outcome.snapshots_written, 0);
}
