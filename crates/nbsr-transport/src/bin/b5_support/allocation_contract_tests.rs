//! Counts real large allocations on this test thread, outside all setup.
use super::*;
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::sync::atomic::AtomicU64;

thread_local! {
    static TRACK: Cell<bool> = const { Cell::new(false) };
    static LARGE: Cell<usize> = const { Cell::new(0) };
}
struct CountingAllocator;
fn count(size: usize) {
    if size >= 32_768 && TRACK.try_with(Cell::get).unwrap_or(false) {
        let _ = LARGE.try_with(|value| value.set(value.get() + 1));
    }
}
// Test-only forwarding allocator; allocation/deallocation ownership stays in System.
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        count(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        count(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        count(size);
        unsafe { System.realloc(pointer, layout, size) }
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) }
    }
}
#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

fn measured<T>(work: impl FnOnce() -> T) -> (T, usize) {
    struct Reset;
    impl Drop for Reset {
        fn drop(&mut self) {
            TRACK.with(|value| value.set(false));
        }
    }
    LARGE.with(|value| value.set(0));
    TRACK.with(|value| value.set(true));
    let reset = Reset;
    let value = work();
    drop(reset);
    (value, LARGE.with(Cell::get))
}

#[test]
fn progress_percentiles_do_not_allocate_another_latency_buffer() {
    let counts = Counts {
        offered: 8192,
        reserved: 8192,
        issued: 8192,
        completed: 8192,
        ..Counts::default()
    };
    let snapshot = Snapshot {
        window_index: 1,
        start_ns: 0,
        end_ns: NS,
        issue_deadline_ns: NS,
        phase: Phase::Steady,
        totals: counts,
        groups: vec![counts],
        sample_count: 8192,
        latency_samples_ns: (0..8192).collect(),
        sample_stride: 1,
        sample_capacity: 8192,
        sample_overflow_count: 0,
        max_outstanding_observed: 1,
        max_reservation_lateness_ns: 0,
    };
    let (line, allocations) = measured(|| progress_json(&snapshot, 0, 1024));
    let value: serde_json::Value = serde_json::from_str(&line).unwrap();
    assert_eq!(value["p50_latency_ns"], 4095);
    assert_eq!(value["p95_latency_ns"], 7782);
    assert_eq!(value["p99_latency_ns"], 8110);
    assert_eq!(value["completed"], 8192);
    assert_eq!(
        allocations, 0,
        "large allocations in progress serialization"
    );
}

#[derive(Default)]
struct ManualClock(AtomicU64);
impl Clock for ManualClock {
    fn now_ns(&self) -> u64 {
        self.0.load(Ordering::SeqCst)
    }
}

#[test]
fn repeated_publication_reuses_prepared_latency_storage() {
    let clock = Arc::new(ManualClock::default());
    let run = AsyncRun::new(
        Config {
            groups: 1,
            streams_per_group: 1,
            max_outstanding: 1,
            rate_numerator: 1_000_000,
            rate_denominator: 1,
            window_ns: 10_000_000,
            duration_ns: NS,
            sample_stride: 1,
            sample_capacity: 8192,
        },
        Arc::clone(&clock),
    )
    .unwrap();
    run.ready(0).unwrap();
    let (_, allocations) = measured(|| {
        for window in 1..=3 {
            for latency in (1..=8192).rev() {
                assert_eq!(run.next(0).unwrap(), Action::Permit);
                run.issued(0).unwrap();
                run.completed(0, latency).unwrap();
            }
            clock.0.store(window * 10_000_000, Ordering::SeqCst);
            run.publish(false, |snapshot| {
                assert_eq!(snapshot.totals.completed, 8192 * window);
                let value: serde_json::Value =
                    serde_json::from_str(&progress_json(snapshot, 8192 * (window - 1), 1024))
                        .unwrap();
                assert_eq!(value["sample_count"], 8192);
                assert_eq!(value["p50_latency_ns"], 4096);
                assert_eq!(value["p95_latency_ns"], 7783);
                assert_eq!(value["p99_latency_ns"], 8111);
                Ok(())
            })
            .unwrap();
        }
    });
    assert!(!run.status().failed);
    assert_eq!(allocations, 0, "large replacement allocations after setup");
}
