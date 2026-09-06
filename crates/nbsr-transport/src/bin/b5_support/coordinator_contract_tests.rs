//! Coordinator lifecycle/accounting contract, established RED first.
use super::coordinator::{Action, Clock, Config, PacedRun, Phase};
use std::sync::{
    Arc,
    atomic::{AtomicU64, Ordering},
};

const MS: u64 = 1_000_000;

#[test]
fn snapshot_preserves_sampling_lateness_and_actual_outstanding_peak() {
    let (clock, run) = setup(8);
    start(&run);
    clock.set(3 * MS);
    complete_one(&run, 0);
    complete_one(&run, 1);
    let snapshot = run.snapshot(false, None).unwrap();
    assert_eq!(snapshot.sample_stride, 2);
    assert_eq!(snapshot.sample_capacity, 8);
    assert_eq!(snapshot.sample_overflow_count, 0);
    assert_eq!(snapshot.max_outstanding_observed, 1);
    assert_eq!(snapshot.max_reservation_lateness_ns, 3 * MS);
}

#[test]
fn status_exposes_drain_and_snapshot_seal_separately() {
    let (clock, run) = setup(8);
    assert!(!run.status().all_groups_drained);
    assert!(!run.status().sealed);
    start(&run);
    clock.set(25 * MS);
    run.drained(0).unwrap();
    assert!(!run.status().all_groups_drained);
    run.drained(1).unwrap();
    assert!(run.status().all_groups_drained);
    assert!(!run.status().sealed);
    run.snapshot(true, None).unwrap();
    assert!(run.status().sealed);
    assert!(!run.status().postflight_allowed);
}

#[derive(Default)]
struct ManualClock(AtomicU64);
impl ManualClock {
    fn set(&self, ns: u64) {
        self.0.store(ns, Ordering::SeqCst);
    }
}
impl Clock for ManualClock {
    fn now_ns(&self) -> u64 {
        self.0.load(Ordering::SeqCst)
    }
}

fn setup(capacity: usize) -> (Arc<ManualClock>, Arc<PacedRun<ManualClock>>) {
    let clock = Arc::new(ManualClock::default());
    let run = Arc::new(
        PacedRun::new(
            Config {
                groups: 2,
                streams_per_group: 1,
                max_outstanding: 1,
                rate_numerator: 200,
                rate_denominator: 1,
                window_ns: 10 * MS,
                duration_ns: 25 * MS,
                sample_stride: 2,
                sample_capacity: capacity,
            },
            Arc::clone(&clock),
        )
        .unwrap(),
    );
    (clock, run)
}

fn start(run: &PacedRun<ManualClock>) {
    run.ready(0).unwrap();
    run.ready(1).unwrap();
}

fn complete_one(run: &PacedRun<ManualClock>, partition: usize) {
    assert_eq!(run.next(partition).unwrap(), Action::Permit);
    run.issued(partition).unwrap();
    run.completed(partition, 17).unwrap();
}

#[test]
fn last_ready_sets_one_shared_origin_and_absolute_deadline() {
    let (clock, run) = setup(8);
    run.ready(0).unwrap();
    clock.set(7 * MS);
    assert_eq!(run.next(0).unwrap(), Action::AwaitReady);
    assert_eq!(run.status().origin_ns, None);
    run.ready(1).unwrap();
    assert_eq!(run.status().origin_ns, Some(7 * MS));
    assert_eq!(run.status().deadline_ns, Some(32 * MS));
    complete_one(&run, 0);
    complete_one(&run, 1);
}

#[test]
fn dropped_group_guard_fails_readiness_and_drain_predicates() {
    let (_, run) = setup(8);
    let guard = run.group_guard(1).unwrap();
    run.ready(0).unwrap();
    drop(guard);
    assert!(run.status().failed);
    assert!(run.ready(1).is_err());
    assert!(run.next(0).is_err());
    assert!(run.drained(0).is_err());
    assert!(!run.status().postflight_allowed);
}

#[test]
fn empty_budget_reads_outstanding_then_waits_without_exiting() {
    let (clock, run) = setup(8);
    start(&run);
    assert_eq!(run.next(0).unwrap(), Action::Permit);
    run.issued(0).unwrap();
    assert_eq!(run.next(0).unwrap(), Action::Read);
    run.completed(0, 19).unwrap();
    assert_eq!(run.next(0).unwrap(), Action::WaitUntil(10 * MS));
    clock.set(25 * MS);
    assert_eq!(run.next(0).unwrap(), Action::Draining);
}

#[test]
fn reservation_write_and_completion_are_distinct_commits() {
    let (clock, run) = setup(8);
    start(&run);
    assert_eq!(run.next(0).unwrap(), Action::Permit);
    clock.set(MS);
    let before_write = run.snapshot(false, None).unwrap();
    assert_eq!(
        (
            before_write.totals.reserved,
            before_write.totals.issued,
            before_write.totals.completed
        ),
        (1, 0, 0)
    );
    run.issued(0).unwrap();
    clock.set(2 * MS);
    let before_response = run.snapshot(false, None).unwrap();
    assert_eq!(
        (
            before_response.totals.reserved,
            before_response.totals.issued,
            before_response.totals.completed
        ),
        (1, 1, 0)
    );
    run.completed(0, 20).unwrap();
    clock.set(3 * MS);
    assert_eq!(run.snapshot(false, None).unwrap().totals.completed, 1);
}

#[test]
fn completion_without_an_issued_request_latches_failure() {
    let (_, run) = setup(8);
    start(&run);
    assert!(run.completed(0, 9).is_err());
    assert!(run.status().failed);
    assert!(run.next(1).is_err());
}

#[test]
fn skipped_windows_expire_without_catchup_and_final_window_is_clipped() {
    let (clock, run) = setup(8);
    start(&run);
    clock.set(21 * MS);
    complete_one(&run, 0); // Aggregate slot 5 belongs to partition 0.
    assert_eq!(run.next(1).unwrap(), Action::WaitUntil(25 * MS));
    clock.set(25 * MS);
    let snapshot = run.snapshot(false, None).unwrap();
    assert_eq!(snapshot.totals.offered, 5);
    assert_eq!(snapshot.totals.reserved, 1);
    assert_eq!(snapshot.totals.missed, 4);
    assert_eq!(snapshot.totals.unreserved_current, 0);
    assert_eq!(snapshot.phase, Phase::Steady);
    assert_eq!(run.next(0).unwrap(), Action::Draining);
}

#[test]
fn coherent_global_samples_and_counts_use_actual_contiguous_snapshot_bounds() {
    let (clock, run) = setup(8);
    start(&run);
    complete_one(&run, 0);
    clock.set(7 * MS);
    let first = run.snapshot(false, None).unwrap();
    assert_eq!((first.start_ns, first.end_ns), (0, 7 * MS));
    assert_eq!(first.sample_count, 0);
    complete_one(&run, 1);
    clock.set(26 * MS);
    let second = run.snapshot(false, None).unwrap();
    assert_eq!((second.start_ns, second.end_ns), (7 * MS, 26 * MS));
    assert_eq!(second.issue_deadline_ns, 25 * MS);
    assert_eq!(second.phase, Phase::Mixed);
    assert_eq!(second.sample_count, 1);
    assert_eq!(second.latency_samples_ns, vec![17]);
    assert_eq!(second.totals.completed, 2);
    assert_eq!(second.groups.iter().map(|g| g.completed).sum::<u64>(), 2);
    clock.set(27 * MS);
    let third = run.snapshot(false, None).unwrap();
    assert_eq!(third.phase, Phase::Drain);
    assert_eq!(third.sample_count, 0);
    assert_eq!(third.totals, second.totals);
}

#[test]
fn guard_finish_after_publication_preserves_success_and_regressed_clock_fails() {
    let (clock, run) = setup(8);
    let guard = run.group_guard(0).unwrap();
    start(&run);
    clock.set(26 * MS);
    run.drained(0).unwrap();
    run.drained(1).unwrap();
    let final_window = run.snapshot(true, None).unwrap();
    run.published_final(final_window.window_index).unwrap();
    guard.finish().unwrap();
    assert!(!run.status().failed);

    let (clock, run) = setup(8);
    start(&run);
    clock.set(2 * MS);
    run.snapshot(false, None).unwrap();
    clock.set(MS);
    assert!(run.next(0).is_err());
    assert!(run.status().failed);
}

#[test]
fn duplicate_pending_reservation_and_early_guard_finish_fail_closed() {
    let (_, run) = setup(8);
    start(&run);
    assert_eq!(run.next(0).unwrap(), Action::Permit);
    assert!(run.next(0).is_err());
    assert!(run.status().failed);

    let (_, run) = setup(8);
    let guard = run.group_guard(0).unwrap();
    assert!(guard.finish().is_err());
    assert!(run.status().failed);
}

#[test]
fn all_groups_drain_and_final_publication_precede_postflight_permission() {
    let (clock, run) = setup(8);
    start(&run);
    complete_one(&run, 0);
    assert_eq!(run.next(1).unwrap(), Action::Permit);
    run.issued(1).unwrap();
    clock.set(26 * MS);
    run.drained(0).unwrap();
    assert!(!run.status().postflight_allowed);
    assert_eq!(run.next(1).unwrap(), Action::Read);
    run.completed(1, 23).unwrap();
    run.drained(1).unwrap();
    clock.set(27 * MS);
    let final_window = run.snapshot(true, None).unwrap();
    assert_eq!(final_window.totals.completed, 2);
    assert_eq!(final_window.end_ns, 27 * MS);
    assert_eq!(final_window.phase, Phase::Mixed);
    assert!(!run.status().postflight_allowed);
    run.published_final(final_window.window_index).unwrap();
    assert!(run.status().postflight_allowed);
    assert!(run.snapshot(false, None).is_err());
}

#[test]
fn final_snapshot_cannot_bypass_slow_group() {
    let (clock, run) = setup(8);
    start(&run);
    clock.set(26 * MS);
    run.drained(0).unwrap();
    assert!(run.snapshot(true, None).is_err());
    assert!(!run.status().postflight_allowed);
}

#[test]
fn collector_overflow_and_publication_failure_never_allow_postflight() {
    let (clock, run) = setup(1);
    start(&run);
    complete_one(&run, 0);
    complete_one(&run, 1); // One retained sample.
    clock.set(10 * MS);
    complete_one(&run, 0);
    assert_eq!(run.next(1).unwrap(), Action::Permit);
    run.issued(1).unwrap();
    assert!(run.completed(1, 31).is_err()); // Second sample exceeds hard cap.
    assert!(run.status().failed);
    assert!(run.snapshot(false, None).is_err());
    assert!(!run.status().postflight_allowed);

    let (clock, run) = setup(8);
    start(&run);
    clock.set(26 * MS);
    run.drained(0).unwrap();
    run.drained(1).unwrap();
    let final_window = run.snapshot(true, None).unwrap();
    run.fail(); // stdout write failed; do not acknowledge publication.
    assert!(run.published_final(final_window.window_index).is_err());
    assert!(!run.status().postflight_allowed);
}
