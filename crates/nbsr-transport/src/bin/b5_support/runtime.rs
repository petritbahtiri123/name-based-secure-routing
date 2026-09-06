//! Test-only async lifecycle wrapper. Owns no transport or publisher worker.
use super::coordinator::{Action, Clock, Config, GroupGuard, PacedRun, Snapshot, Status};
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tokio::sync::Notify;

type Error = &'static str;

pub(crate) struct InstantClock {
    epoch: Instant,
}
impl InstantClock {
    pub(crate) fn new() -> Self {
        Self {
            epoch: Instant::now(),
        }
    }
}
impl Clock for InstantClock {
    fn now_ns(&self) -> u64 {
        // The coordinator calls this under its lock; overflow panics and poisons
        // that lock rather than silently truncating an elapsed timestamp.
        u64::try_from(self.epoch.elapsed().as_nanos())
            .expect("monotonic clock exceeds u64 nanoseconds")
    }
}

pub(crate) struct AsyncRun<C: Clock> {
    run: Arc<PacedRun<C>>,
    changed: Notify,
    publisher: Mutex<Vec<u64>>,
}
impl<C: Clock> AsyncRun<C> {
    pub(crate) fn new(config: Config, clock: Arc<C>) -> Result<Self, Error> {
        let capacity = config.sample_capacity;
        let run = Arc::new(PacedRun::new(config, clock)?);
        let mut spare = Vec::new();
        spare
            .try_reserve_exact(capacity)
            .map_err(|_| "sample allocation failed")?;
        Ok(Self {
            run,
            changed: Notify::new(),
            publisher: Mutex::new(spare),
        })
    }

    pub(crate) fn status(&self) -> Status {
        self.run.status()
    }

    pub(crate) fn fail(&self) {
        self.run.fail();
        self.changed.notify_waiters();
    }

    fn checked<T>(&self, result: Result<T, Error>) -> Result<T, Error> {
        if result.is_err() {
            self.fail();
        }
        result
    }

    pub(crate) fn ready(&self, group: usize) -> Result<(), Error> {
        let result = self.checked(self.run.ready(group));
        self.changed.notify_waiters();
        result
    }

    pub(crate) fn drained(&self, group: usize) -> Result<(), Error> {
        let result = self.checked(self.run.drained(group));
        self.changed.notify_waiters();
        result
    }

    pub(crate) fn next(&self, partition: usize) -> Result<Action, Error> {
        self.checked(self.run.next(partition))
    }

    pub(crate) fn issued(&self, partition: usize) -> Result<(), Error> {
        self.checked(self.run.issued(partition))
    }

    pub(crate) fn completed(&self, partition: usize, latency_ns: u64) -> Result<(), Error> {
        self.checked(self.run.completed(partition, latency_ns))
    }

    async fn wait_for(&self, predicate: impl Fn(&Status) -> bool) -> Result<(), Error> {
        loop {
            let notified = self.changed.notified();
            tokio::pin!(notified);
            // Register before taking the predicate snapshot. A transition after
            // this registration either appears in status or wakes this future.
            notified.as_mut().enable();
            let status = self.status();
            if status.failed {
                return Err("paced run failed");
            }
            if predicate(&status) {
                return Ok(());
            }
            notified.await;
        }
    }

    pub(crate) async fn wait_ready(&self) -> Result<(), Error> {
        self.wait_for(|s| s.origin_ns.is_some()).await
    }

    pub(crate) async fn wait_drained(&self) -> Result<(), Error> {
        self.wait_for(|s| s.all_groups_drained).await
    }

    pub(crate) async fn wait_postflight(&self) -> Result<(), Error> {
        self.wait_for(|s| s.postflight_allowed).await
    }

    pub(crate) async fn wait_failed(&self) -> Result<(), Error> {
        self.wait_for(|_| false).await
    }

    // The caller provides bounded synchronous serialization/output. It must
    // return Ok only after the complete record has been written (and flushed if
    // buffered). No coordinator lock is held while it performs output. A sole
    // publisher is required; concurrent/reentrant publication fails closed.
    pub(crate) fn publish(
        &self,
        final_window: bool,
        sink: impl FnOnce(&Snapshot) -> std::io::Result<()>,
    ) -> Result<(), Error> {
        let mut failure = FailOnDrop {
            run: self,
            armed: true,
        };
        let mut publisher = self
            .publisher
            .try_lock()
            .map_err(|_| "publisher busy or poisoned")?;
        let mut snapshot = self.checked(
            self.run
                .snapshot(final_window, Some(std::mem::take(&mut *publisher))),
        )?;
        // Only the sole publisher owns this window. Sort outside coordinator
        // locks, then return its storage for the next swap after publication.
        snapshot.latency_samples_ns.sort_unstable();
        sink(&snapshot).map_err(|_| "progress output failed")?;
        if final_window {
            self.checked(self.run.published_final(snapshot.window_index))?;
        }
        // Concurrent group failure may have occurred while output was underway.
        if self.status().failed {
            return Err("paced run failed during publication");
        }
        snapshot.latency_samples_ns.clear();
        *publisher = snapshot.latency_samples_ns;
        failure.armed = false;
        self.changed.notify_waiters();
        Ok(())
    }

    pub(crate) fn group_guard(
        self: &Arc<Self>,
        group: usize,
    ) -> Result<RuntimeGroupGuard<C>, Error> {
        let inner = self.checked(self.run.group_guard(group))?;
        Ok(RuntimeGroupGuard {
            run: Arc::clone(self),
            inner: Some(inner),
        })
    }
}

struct FailOnDrop<'a, C: Clock> {
    run: &'a AsyncRun<C>,
    armed: bool,
}
impl<C: Clock> Drop for FailOnDrop<'_, C> {
    fn drop(&mut self) {
        if self.armed {
            self.run.fail();
        }
    }
}

pub(crate) struct RuntimeGroupGuard<C: Clock> {
    run: Arc<AsyncRun<C>>,
    inner: Option<GroupGuard<C>>,
}
impl<C: Clock> RuntimeGroupGuard<C> {
    pub(crate) fn finish(mut self) -> Result<(), Error> {
        let result = self.inner.take().ok_or("guard already finished")?.finish();
        self.run.checked(result)
    }
}
impl<C: Clock> Drop for RuntimeGroupGuard<C> {
    fn drop(&mut self) {
        // Drop the coordinator guard first: failure must be visible before wake.
        drop(self.inner.take());
        self.run.changed.notify_waiters();
    }
}
