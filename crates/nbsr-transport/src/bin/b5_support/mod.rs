use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Debug, Eq, PartialEq)]
pub(crate) struct ProgressWindow {
    pub(crate) interval_ns: u64,
    pub(crate) completed_operations: u64,
    pub(crate) sample_count: usize,
    pub(crate) p50_latency_ns: Option<u64>,
    pub(crate) p95_latency_ns: Option<u64>,
    pub(crate) p99_latency_ns: Option<u64>,
    pub(crate) latency_sample_stride: u64,
}

fn percentile(values: &[u64], percentile: f64) -> Option<u64> {
    if values.is_empty() {
        return None;
    }
    Some(values[((values.len() - 1) as f64 * percentile).round() as usize])
}

pub(crate) fn progress_window(
    interval_ns: u64,
    completed_operations: u64,
    mut latency_samples: Vec<u64>,
    latency_sample_stride: u64,
) -> ProgressWindow {
    latency_samples.sort_unstable();
    ProgressWindow {
        interval_ns,
        completed_operations,
        sample_count: latency_samples.len(),
        p50_latency_ns: percentile(&latency_samples, 0.50),
        p95_latency_ns: percentile(&latency_samples, 0.95),
        p99_latency_ns: percentile(&latency_samples, 0.99),
        latency_sample_stride,
    }
}

pub(crate) fn record_bounded_tail(values: &mut Vec<u64>, value: u64, capacity: usize) {
    assert!(capacity > 0);
    if values.len() == capacity {
        values.remove(0);
    }
    values.push(value);
}

pub(crate) struct SoakTelemetry {
    completed: AtomicU64,
    observed: AtomicU64,
    latency_samples: Mutex<Vec<u64>>,
    sample_stride: u64,
}

impl SoakTelemetry {
    pub(crate) fn new(sample_stride: u64) -> Result<Self, &'static str> {
        if sample_stride == 0 {
            return Err("latency sample stride must be positive");
        }
        Ok(Self {
            completed: AtomicU64::new(0),
            observed: AtomicU64::new(0),
            latency_samples: Mutex::new(Vec::new()),
            sample_stride,
        })
    }

    pub(crate) fn record(&self, latency_ns: u64) {
        let ordinal = self.observed.fetch_add(1, Ordering::Relaxed) + 1;
        self.completed.fetch_add(1, Ordering::Relaxed);
        if ordinal.is_multiple_of(self.sample_stride) {
            self.latency_samples
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .push(latency_ns);
        }
    }

    pub(crate) fn take_window(&self, interval_ns: u64) -> ProgressWindow {
        let completed = self.completed.swap(0, Ordering::Relaxed);
        let samples = std::mem::take(
            &mut *self
                .latency_samples
                .lock()
                .unwrap_or_else(|error| error.into_inner()),
        );
        progress_window(interval_ns, completed, samples, self.sample_stride)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn progress_window_preserves_exact_count_and_sampled_percentiles() {
        let window = progress_window(5_000_000_000, 250, vec![10, 20, 30, 40], 64);

        assert_eq!(window.completed_operations, 250);
        assert_eq!(window.sample_count, 4);
        assert_eq!(window.p50_latency_ns, Some(30));
        assert_eq!(window.p95_latency_ns, Some(40));
        assert_eq!(window.p99_latency_ns, Some(40));
        assert_eq!(window.latency_sample_stride, 64);
    }

    #[test]
    fn progress_window_is_explicit_when_no_latency_sample_exists() {
        let window = progress_window(1_000_000_000, 3, Vec::new(), 64);

        assert_eq!(window.completed_operations, 3);
        assert_eq!(window.sample_count, 0);
        assert_eq!(window.p99_latency_ns, None);
    }

    #[test]
    fn soak_telemetry_samples_boundedly_and_resets_each_window() {
        let telemetry = SoakTelemetry::new(2).unwrap();
        telemetry.record(10);
        telemetry.record(20);
        telemetry.record(30);
        telemetry.record(40);

        let first = telemetry.take_window(1_000);
        assert_eq!(first.completed_operations, 4);
        assert_eq!(first.sample_count, 2);
        assert_eq!(first.p50_latency_ns, Some(40));
        assert_eq!(telemetry.take_window(1_000).completed_operations, 0);
        assert!(SoakTelemetry::new(0).is_err());
    }

    #[test]
    fn final_latency_sample_retains_only_the_bounded_tail() {
        let mut values = Vec::new();
        for value in 0..10 {
            record_bounded_tail(&mut values, value, 4);
        }

        assert_eq!(values, vec![6, 7, 8, 9]);
    }
}
