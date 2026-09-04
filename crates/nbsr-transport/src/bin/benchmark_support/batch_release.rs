//! Benchmark-only pre-connect release pacing. Never consulted by transport logic.
use std::future::Future;
use std::time::Duration;

#[derive(Clone, Copy)]
pub struct BatchRelease {
    batch_size: usize,
    interval: Duration,
    origin: std::time::Instant,
}

impl BatchRelease {
    pub fn new(batch_size: usize, interval: Duration) -> Result<Self, &'static str> {
        if batch_size == 0 || interval.is_zero() {
            return Err("batch size and interval must be positive");
        }
        Ok(Self {
            batch_size,
            interval,
            origin: std::time::Instant::now(),
        })
    }

    pub fn from_options(
        batch_size: Option<usize>,
        interval_ms: Option<u64>,
    ) -> Result<Option<Self>, &'static str> {
        match (batch_size, interval_ms) {
            (None, None) => Ok(None),
            (Some(batch), Some(interval)) if matches!(batch, 8 | 16 | 32) => {
                Self::new(batch, Duration::from_millis(interval)).map(Some)
            }
            (Some(_), Some(_)) => Err("diagnostic batch size must be 8, 16, or 32"),
            _ => Err("batch size and release interval must be supplied together"),
        }
    }

    pub fn scheduled_delay(&self, client: usize) -> Duration {
        self.interval
            .saturating_mul((client / self.batch_size) as u32)
    }

    async fn wait(&self, client: usize) {
        tokio::time::sleep_until(tokio::time::Instant::from_std(
            self.origin + self.scheduled_delay(client),
        ))
        .await;
    }
}

pub async fn after_release<F, Fut, T>(gate: Option<BatchRelease>, client: usize, operation: F) -> T
where
    F: FnOnce() -> Fut,
    Fut: Future<Output = T>,
{
    if let Some(gate) = &gate {
        gate.wait(client).await;
    }
    operation().await
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicBool, Ordering};
    use tokio::time::Instant;

    #[test]
    fn exact_batch_boundaries_are_deterministic() {
        let gate = BatchRelease::new(8, Duration::from_millis(20)).unwrap();
        assert_eq!(gate.scheduled_delay(0), Duration::ZERO);
        assert_eq!(gate.scheduled_delay(7), Duration::ZERO);
        assert_eq!(gate.scheduled_delay(8), Duration::from_millis(20));
        assert_eq!(gate.scheduled_delay(15), Duration::from_millis(20));
        assert_eq!(gate.scheduled_delay(16), Duration::from_millis(40));
    }

    #[test]
    fn disabled_and_invalid_options_fail_closed() {
        assert!(BatchRelease::from_options(None, None).unwrap().is_none());
        assert!(BatchRelease::from_options(Some(8), None).is_err());
        assert!(BatchRelease::from_options(None, Some(10)).is_err());
        assert!(BatchRelease::from_options(Some(7), Some(10)).is_err());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn waiting_is_async_and_operation_starts_after_release() {
        let gate = BatchRelease::new(8, Duration::from_millis(30)).unwrap();
        let heartbeat = Arc::new(AtomicBool::new(false));
        let beat = heartbeat.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(5)).await;
            beat.store(true, Ordering::SeqCst);
        });
        let start = Instant::now();
        let observed = after_release(Some(gate), 8, || async { Instant::now() }).await;
        assert!(heartbeat.load(Ordering::SeqCst));
        assert!(observed.duration_since(start) >= Duration::from_millis(20));
    }

    #[tokio::test(flavor = "current_thread")]
    async fn cancellation_never_starts_the_client_operation() {
        let gate = BatchRelease::new(8, Duration::from_millis(100)).unwrap();
        let started = Arc::new(AtomicBool::new(false));
        let child_started = started.clone();
        let task = tokio::spawn(async move {
            after_release(Some(gate), 8, || async {
                child_started.store(true, Ordering::SeqCst);
            })
            .await
        });
        tokio::time::sleep(Duration::from_millis(5)).await;
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        assert!(!started.load(Ordering::SeqCst));
    }

    #[tokio::test(flavor = "current_thread")]
    async fn disabled_gate_preserves_immediate_existing_behavior() {
        let start = Instant::now();
        after_release(None, 999, || async {}).await;
        assert!(start.elapsed() < Duration::from_millis(20));
    }
}
