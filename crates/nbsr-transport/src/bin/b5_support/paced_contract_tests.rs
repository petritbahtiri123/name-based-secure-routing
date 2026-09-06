//! Deterministic pacing and bounded sampling contracts, established RED first.
use super::{BoundedCollector, PacingWindow};

#[test]
fn stream_partitions_balance_cumulative_stream_and_group_offered_work() {
    let groups = 4;
    let streams = 64;
    let partitions = groups * streams;
    let mut pacing: Vec<_> = (0..partitions)
        .map(|partition| {
            PacingWindow::new(10_333, 1, partitions, partition, 10_000_000, 100_000_000).unwrap()
        })
        .collect();
    for window in 0..10_u64 {
        let offered: Vec<_> = pacing
            .iter_mut()
            .map(|partition| partition.advance(window * 10_000_000).unwrap().offered)
            .collect();
        assert_eq!(
            offered.iter().sum::<u64>(),
            10_333 * ((window + 1) * 10_000_000) / 1_000_000_000
        );
        assert!(offered.iter().max().unwrap() - offered.iter().min().unwrap() <= 1);
        let group_totals: Vec<u64> = (0..groups)
            .map(|group| {
                (0..streams)
                    .map(|stream| offered[stream * groups + group])
                    .sum()
            })
            .collect();
        assert!(group_totals.iter().max().unwrap() - group_totals.iter().min().unwrap() <= 1);
        if window == 0 {
            assert!(offered.contains(&0)); // No promise of work in every window.
        }
        if window == 9 {
            assert!(offered.iter().all(|count| *count >= 4));
        }
    }
}

#[test]
fn rational_group_budgets_sum_to_exact_cumulative_target() {
    let mut groups: Vec<_> = (0..4)
        .map(|group| PacingWindow::new(615_799, 100, 4, group, 10_000_000, 40_000_000).unwrap())
        .collect();
    let mut offered = 0;
    for group in &mut groups {
        offered += group.advance(0).unwrap().offered;
    }
    assert_eq!(offered, 61); // floor(6157.99 * .01), not four rounded rates.
    let counts: Vec<_> = groups
        .iter_mut()
        .map(|g| g.advance(0).unwrap().offered)
        .collect();
    assert_eq!(counts, [16, 15, 15, 15]);
}

#[test]
fn expiration_never_carries_unused_slots_into_a_later_window() {
    let mut pace = PacingWindow::new(1_000, 1, 1, 0, 10_000_000, 100_000_000).unwrap();
    assert_eq!(pace.advance(0).unwrap().unreserved_current, 10);
    assert!(pace.reserve(0).unwrap());
    let skipped = pace.advance(35_000_000).unwrap();
    assert_eq!(skipped.offered, 40);
    assert_eq!(skipped.reserved, 1);
    assert_eq!(skipped.missed, 29);
    assert_eq!(skipped.unreserved_current, 10);
    for _ in 0..10 {
        assert!(pace.reserve(35_000_000).unwrap());
    }
    assert!(!pace.reserve(35_000_000).unwrap());
    assert_eq!(pace.advance(35_000_000).unwrap().reserved, 11);
}

#[test]
fn partial_last_window_is_clipped_and_deadline_expires_unused_budget() {
    let mut pace = PacingWindow::new(1_000, 1, 1, 0, 10_000_000, 25_000_000).unwrap();
    let final_window = pace.advance(20_000_000).unwrap();
    assert_eq!(final_window.offered, 25);
    assert_eq!(final_window.missed, 20);
    assert_eq!(final_window.unreserved_current, 5);
    assert!(pace.reserve(24_999_999).unwrap());
    assert!(!pace.reserve(25_000_000).unwrap());
    let final_counts = pace.advance(25_000_000).unwrap();
    assert_eq!(final_counts.offered, 25);
    assert_eq!(final_counts.reserved, 1);
    assert_eq!(final_counts.missed, 24);
    assert_eq!(final_counts.unreserved_current, 0);
}

#[test]
fn invalid_rates_groups_times_and_unrepresentable_budget_fail_closed() {
    assert!(PacingWindow::new(0, 1, 1, 0, 10_000_000, 1).is_err());
    assert!(PacingWindow::new(1, 0, 1, 0, 10_000_000, 1).is_err());
    assert!(PacingWindow::new(1, 1, 0, 0, 10_000_000, 1).is_err());
    assert!(PacingWindow::new(1, 1, 2, 2, 10_000_000, 1).is_err());
    assert!(PacingWindow::new(1, 1, 1, 0, 0, 1).is_err());
    assert!(PacingWindow::new(1, 1, 1, 0, 10_000_000, 0).is_err());
    assert!(PacingWindow::new(u64::MAX, 1, 1, 0, 10_000_000, u64::MAX).is_err());
    let mut pace = PacingWindow::new(1, 1, 1, 0, 10_000_000, 100_000_000).unwrap();
    pace.advance(10_000_000).unwrap();
    assert!(pace.advance(9_999_999).is_err());
}

#[test]
fn reservation_accounts_lateness_without_changing_the_budget() {
    let mut pace = PacingWindow::new(100, 1, 1, 0, 10_000_000, 20_000_000).unwrap();
    assert!(pace.reserve(3_000_000).unwrap());
    assert!(!pace.reserve(4_000_000).unwrap());
    let counters = pace.advance(4_000_000).unwrap();
    assert_eq!(counters.max_reservation_lateness_ns, 3_000_000);
    assert_eq!(
        counters.offered,
        counters.reserved + counters.missed + counters.unreserved_current
    );
}

#[test]
fn coherent_collector_samples_global_ordinals_and_exact_group_counts() {
    let collector = BoundedCollector::new(2, 2, 2).unwrap();
    collector.record_completed(0, 10).unwrap();
    collector.record_completed(1, 20).unwrap();
    collector.record_completed(1, 30).unwrap();
    collector.record_completed(0, 40).unwrap();
    let window = collector.take_window(None).unwrap();
    assert_eq!(window.completed, 4);
    assert_eq!(window.group_completed, [2, 2]);
    assert_eq!(window.latency_samples_ns, [20, 40]);
    assert_eq!(window.sample_capacity, 2);
    let empty = collector.take_window(None).unwrap();
    assert_eq!(empty.completed, 0);
    assert_eq!(empty.group_completed, [0, 0]);
    assert!(empty.latency_samples_ns.is_empty());
    collector.record_completed(1, 50).unwrap();
    collector.record_completed(0, 60).unwrap();
    assert_eq!(
        collector.take_window(None).unwrap().latency_samples_ns,
        [60]
    );
}

#[test]
fn collector_stall_has_hard_cap_and_latched_overflow_invalidity() {
    let collector = BoundedCollector::new(1, 1, 2).unwrap();
    collector.record_completed(0, 10).unwrap();
    collector.record_completed(0, 20).unwrap();
    assert!(collector.record_completed(0, 30).is_err());
    let status = collector.status().unwrap();
    assert_eq!(status.retained_samples, 2);
    assert_eq!(status.completed, 3); // operation happened; never erase it.
    assert_eq!(status.overflow_count, 1);
    assert!(!status.evidence_valid);
    assert!(collector.take_window(None).is_err()); // No plausible percentile after loss.
    assert!(collector.record_completed(0, 40).is_err());
    assert_eq!(collector.status().unwrap().retained_samples, 2);
}

#[test]
fn collector_rejects_invalid_identity_and_capacity() {
    assert!(BoundedCollector::new(0, 1, 1).is_err());
    assert!(BoundedCollector::new(1, 0, 1).is_err());
    assert!(BoundedCollector::new(1, 1, 0).is_err());
    let collector = BoundedCollector::new(2, 1, 2).unwrap();
    assert!(collector.record_completed(2, 10).is_err());
    assert_eq!(collector.status().unwrap().completed, 0);
}

#[test]
fn invalid_replacement_buffer_latches_failure_without_erasing_samples() {
    for replacement in [Vec::with_capacity(1), vec![99, 100]] {
        let collector = BoundedCollector::new(1, 1, 2).unwrap();
        collector.record_completed(0, 42).unwrap();
        assert!(collector.take_window(Some(replacement)).is_err());
        let status = collector.status().unwrap();
        assert!(!status.evidence_valid);
        assert_eq!(status.completed, 1);
        assert_eq!(status.retained_samples, 1);
        assert!(collector.take_window(None).is_err());
    }
}
