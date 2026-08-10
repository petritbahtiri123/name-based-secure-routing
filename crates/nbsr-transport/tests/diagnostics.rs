use nbsr_transport::diagnostics::{DiagnosticOwner, Diagnostics};

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
