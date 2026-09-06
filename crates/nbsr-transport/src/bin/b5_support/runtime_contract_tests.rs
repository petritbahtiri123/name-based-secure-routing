//! Literal RED contracts for the async coordinator wrapper, without transports.
use super::coordinator::{Action, Clock, Config};
use super::runtime::{AsyncRun, InstantClock};
use std::future::Future;
use std::sync::{
    Arc,
    atomic::{AtomicU64, AtomicUsize, Ordering},
};
use std::task::{Context, Poll, Wake, Waker};

#[derive(Default)]
struct ManualClock(AtomicU64);
impl Clock for ManualClock {
    fn now_ns(&self) -> u64 {
        self.0.load(Ordering::SeqCst)
    }
}
fn config() -> Config {
    Config {
        groups: 2,
        streams_per_group: 1,
        max_outstanding: 1,
        rate_numerator: 200,
        rate_denominator: 1,
        window_ns: 10_000_000,
        duration_ns: 25_000_000,
        sample_stride: 2,
        sample_capacity: 8,
    }
}
fn setup() -> (Arc<ManualClock>, Arc<AsyncRun<ManualClock>>) {
    let clock = Arc::new(ManualClock::default());
    let run = Arc::new(AsyncRun::new(config(), Arc::clone(&clock)).unwrap());
    (clock, run)
}
#[derive(Default)]
struct WakeCount(AtomicUsize);
impl Wake for WakeCount {
    fn wake(self: Arc<Self>) {
        self.0.fetch_add(1, Ordering::SeqCst);
    }
    fn wake_by_ref(self: &Arc<Self>) {
        self.0.fetch_add(1, Ordering::SeqCst);
    }
}

#[test]
fn notify_registers_before_readiness_and_late_waiter_sees_stored_predicate() {
    let (_, run) = setup();
    let wakes = Arc::new(WakeCount::default());
    let waker = Waker::from(Arc::clone(&wakes));
    let mut cx = Context::from_waker(&waker);
    let mut first = Box::pin(run.wait_ready());
    assert!(first.as_mut().poll(&mut cx).is_pending());
    run.ready(0).unwrap();
    assert!(first.as_mut().poll(&mut cx).is_pending());
    let before = wakes.0.load(Ordering::SeqCst);
    run.ready(1).unwrap();
    assert!(wakes.0.load(Ordering::SeqCst) > before);
    assert!(matches!(first.as_mut().poll(&mut cx), Poll::Ready(Ok(()))));
    let mut late = Box::pin(run.wait_ready());
    assert!(matches!(late.as_mut().poll(&mut cx), Poll::Ready(Ok(()))));
}

#[tokio::test(flavor = "current_thread")]
async fn guard_drop_wakes_ready_and_postflight_waiters_with_failure() {
    let (_, run) = setup();
    let guard = run.group_guard(1).unwrap();
    let ready = tokio::spawn({
        let run = Arc::clone(&run);
        async move { run.wait_ready().await }
    });
    let post = tokio::spawn({
        let run = Arc::clone(&run);
        async move { run.wait_postflight().await }
    });
    tokio::task::yield_now().await;
    drop(guard);
    let result = tokio::time::timeout(std::time::Duration::from_secs(2), async {
        assert!(ready.await.unwrap().is_err());
        assert!(post.await.unwrap().is_err());
    })
    .await;
    assert!(result.is_ok(), "failure notification was lost");
}

#[tokio::test(flavor = "current_thread")]
async fn final_sink_success_is_required_before_postflight_wakes() {
    let (clock, run) = setup();
    let guard = run.group_guard(0).unwrap();
    run.ready(0).unwrap();
    run.ready(1).unwrap();
    clock.0.store(26_000_000, Ordering::SeqCst);
    run.drained(0).unwrap();
    let wakes = Arc::new(WakeCount::default());
    let waker = Waker::from(Arc::clone(&wakes));
    let mut cx = Context::from_waker(&waker);
    let mut drained = Box::pin(run.wait_drained());
    let mut post = Box::pin(run.wait_postflight());
    assert!(drained.as_mut().poll(&mut cx).is_pending());
    assert!(post.as_mut().poll(&mut cx).is_pending());
    run.drained(1).unwrap();
    assert!(matches!(
        drained.as_mut().poll(&mut cx),
        Poll::Ready(Ok(()))
    ));
    assert!(post.as_mut().poll(&mut cx).is_pending());
    run.publish(true, |snapshot| {
        assert_eq!(snapshot.totals.completed, 0);
        // Taking a status lock in the sink must be safe: serialization is outside it.
        assert!(run.status().sealed);
        assert!(!run.status().postflight_allowed);
        Ok(())
    })
    .unwrap();
    assert!(matches!(post.as_mut().poll(&mut cx), Poll::Ready(Ok(()))));
    guard.finish().unwrap();
    assert!(!run.status().failed);
}

#[tokio::test(flavor = "current_thread")]
async fn sink_error_latches_failure_and_releases_postflight_waiter() {
    let (clock, run) = setup();
    run.ready(0).unwrap();
    run.ready(1).unwrap();
    clock.0.store(26_000_000, Ordering::SeqCst);
    run.drained(0).unwrap();
    run.drained(1).unwrap();
    assert!(
        run.publish(true, |_| Err(std::io::Error::other(
            "injected write failure"
        )))
        .is_err()
    );
    assert!(run.status().failed);
    assert!(!run.status().postflight_allowed);
    assert!(run.wait_postflight().await.is_err());
    assert!(run.wait_drained().await.is_err());
}

#[test]
fn sink_panic_invalidates_even_after_final_snapshot_sealed() {
    let (clock, run) = setup();
    run.ready(0).unwrap();
    run.ready(1).unwrap();
    clock.0.store(26_000_000, Ordering::SeqCst);
    run.drained(0).unwrap();
    run.drained(1).unwrap();
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let _ = run.publish(true, |_| -> std::io::Result<()> {
            panic!("injected sink panic")
        });
    }));
    assert!(result.is_err());
    assert!(run.status().failed);
    assert!(!run.status().postflight_allowed);
}

#[test]
fn instant_clock_is_monotonic_and_uses_one_epoch() {
    let clock = InstantClock::new();
    let first = clock.now_ns();
    assert!(clock.now_ns() >= first);
    let run = AsyncRun::new(config(), Arc::new(clock)).unwrap();
    run.ready(0).unwrap();
    run.ready(1).unwrap();
    let status = run.status();
    assert_eq!(
        status.deadline_ns.unwrap() - status.origin_ns.unwrap(),
        25_000_000
    );
}

#[test]
fn forwarding_methods_keep_exact_counts_and_notify_on_failure() {
    let (clock, run) = setup();
    run.ready(0).unwrap();
    run.ready(1).unwrap();
    assert_eq!(run.next(0).unwrap(), Action::Permit);
    run.issued(0).unwrap();
    run.completed(0, 12).unwrap();
    clock.0.store(1_000_000, Ordering::SeqCst);
    run.publish(false, |snapshot| {
        assert_eq!(snapshot.totals.completed, 1);
        Ok(())
    })
    .unwrap();
    let wakes = Arc::new(WakeCount::default());
    let waker = Waker::from(Arc::clone(&wakes));
    let mut cx = Context::from_waker(&waker);
    let mut waiting = Box::pin(run.wait_postflight());
    assert!(waiting.as_mut().poll(&mut cx).is_pending());
    assert!(run.completed(0, 12).is_err());
    assert!(wakes.0.load(Ordering::SeqCst) > 0);
    assert!(matches!(
        waiting.as_mut().poll(&mut cx),
        Poll::Ready(Err(_))
    ));
}
