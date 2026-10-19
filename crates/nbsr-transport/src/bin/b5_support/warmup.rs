//! Warmup uses the same aggregate budget and no-catch-up policy as measurement.
use crate::b5_driver::paced;
const WINDOW_NS: u64 = 10_000_000;

pub(crate) struct WarmupPacer {
    window: paced::PacingWindow,
    duration_ns: u64,
}

impl WarmupPacer {
    pub(crate) fn new(
        numerator: u64,
        denominator: u64,
        partitions: usize,
        partition: usize,
        duration_ns: u64,
    ) -> Result<Self, &'static str> {
        Ok(Self {
            window: paced::PacingWindow::new(
                numerator,
                denominator,
                partitions,
                partition,
                WINDOW_NS,
                duration_ns,
            )?,
            duration_ns,
        })
    }
    pub(crate) fn reserve(&mut self, elapsed_ns: u64) -> Result<bool, &'static str> {
        self.window.reserve(elapsed_ns)
    }
    pub(crate) fn next_tick(&self, elapsed_ns: u64) -> u64 {
        ((elapsed_ns / WINDOW_NS)
            .saturating_add(1)
            .saturating_mul(WINDOW_NS))
        .min(self.duration_ns)
    }
}
