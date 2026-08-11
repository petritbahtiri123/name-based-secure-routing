#![cfg(feature = "benchmark-harness")]

use nbsr_transport::lifecycle_profile::{LifecyclePhase, Profiler};

#[test]
fn disabled_profiler_records_nothing() {
    let profiler = Profiler::new(false);
    profiler
        .measure(LifecyclePhase::SourcePrepareAuthorize, || Ok::<_, ()>(7))
        .unwrap();
    let snapshot = profiler.snapshot();
    assert_eq!(snapshot.total_calls(), 0);
    assert_eq!(snapshot.total_successes(), 0);
}

#[test]
fn successful_and_failed_timer_pairs_reconcile() {
    let profiler = Profiler::new(true);
    assert_eq!(
        profiler.measure(LifecyclePhase::DestinationAuthorize, || Ok::<_, ()>(3)),
        Ok(3)
    );
    assert_eq!(
        profiler.measure(LifecyclePhase::DestinationAuthorize, || Err::<(), _>("no")),
        Err("no")
    );
    let phase = profiler
        .snapshot()
        .phase(LifecyclePhase::DestinationAuthorize);
    assert_eq!(phase.calls, 2);
    assert_eq!(phase.successes, 1);
    assert_eq!(phase.failures, 1);
    assert!(phase.total_ns >= phase.min_ns);
    assert!(phase.max_ns >= phase.min_ns);
}

#[test]
fn phase_labels_are_closed_fixed_and_safe() {
    let labels = LifecyclePhase::ALL.map(LifecyclePhase::label);
    assert_eq!(labels.len(), 18);
    assert_eq!(labels[0], "source_prepare_authorize");
    assert_eq!(labels[17], "destination_release_cleanup");
    let joined = labels.join(" ").to_ascii_lowercase();
    for forbidden in ["request_id", "payload", "key", "ticket", "nonce", "secret"] {
        assert!(
            !joined.contains(forbidden),
            "forbidden telemetry label {forbidden}"
        );
    }
}

#[test]
fn histogram_quantiles_are_bounded_by_observed_range() {
    let profiler = Profiler::new(true);
    for _ in 0..8 {
        profiler.record_ns(LifecyclePhase::QuinnOpenBi, 100, true);
    }
    profiler.record_ns(LifecyclePhase::QuinnOpenBi, 10_000, true);
    let phase = profiler.snapshot().phase(LifecyclePhase::QuinnOpenBi);
    assert!((phase.min_ns..=phase.max_ns).contains(&phase.p50_ns));
    assert!((phase.p50_ns..=phase.max_ns).contains(&phase.p95_ns));
    assert!((phase.p95_ns..=phase.max_ns).contains(&phase.p99_ns));
}
