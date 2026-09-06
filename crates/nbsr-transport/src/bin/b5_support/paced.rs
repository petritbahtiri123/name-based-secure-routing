//! Tested pacing/accounting primitives. Live integration is a separate gate.
use std::sync::Mutex;

type Error = &'static str;

#[derive(Clone, Copy, Debug)]
pub(crate) struct PacingCounts {
    pub(crate) offered: u64,
    pub(crate) reserved: u64,
    pub(crate) missed: u64,
    pub(crate) unreserved_current: u64,
    pub(crate) max_reservation_lateness_ns: u64,
}

pub(crate) struct PacingWindow {
    numerator: u64,
    denominator_ns: u128,
    partitions: u64,
    partition: u64,
    window_ns: u64,
    duration_ns: u64,
    last_elapsed: u64,
    current_window: Option<u64>,
    invalid: bool,
    counts: PacingCounts,
}

impl PacingWindow {
    pub(crate) fn new(
        numerator: u64,
        denominator: u64,
        partitions: usize,
        partition: usize,
        window_ns: u64,
        duration_ns: u64,
    ) -> Result<Self, Error> {
        if numerator == 0
            || denominator == 0
            || !(1..=256).contains(&partitions)
            || partition >= partitions
            || window_ns == 0
            || duration_ns == 0
        {
            return Err("invalid pacing configuration");
        }
        let value = Self {
            numerator,
            denominator_ns: u128::from(denominator)
                .checked_mul(1_000_000_000)
                .ok_or("rate overflow")?,
            partitions: partitions as u64,
            partition: partition as u64,
            window_ns,
            duration_ns,
            last_elapsed: 0,
            current_window: None,
            invalid: false,
            counts: PacingCounts {
                offered: 0,
                reserved: 0,
                missed: 0,
                unreserved_current: 0,
                max_reservation_lateness_ns: 0,
            },
        };
        // Require the complete aggregate budget, not just one partition, to fit u64.
        value.aggregate(duration_ns)?;
        Ok(value)
    }

    fn aggregate(&self, elapsed: u64) -> Result<u64, Error> {
        let product = u128::from(self.numerator)
            .checked_mul(u128::from(elapsed))
            .ok_or("rate overflow")?;
        u64::try_from(product / self.denominator_ns).map_err(|_| "budget overflow")
    }

    fn cumulative(&self, elapsed: u64) -> Result<u64, Error> {
        let aggregate = u128::from(self.aggregate(elapsed)?);
        let balanced = aggregate
            .checked_add(u128::from(self.partitions - 1 - self.partition))
            .ok_or("partition overflow")?
            / u128::from(self.partitions);
        u64::try_from(balanced).map_err(|_| "partition overflow")
    }

    fn advance_checked(&mut self, elapsed: u64) -> Result<PacingCounts, Error> {
        if self.invalid || elapsed < self.last_elapsed {
            return Err("invalid pacing clock");
        }
        if elapsed >= self.duration_ns {
            let offered = self.cumulative(self.duration_ns)?;
            self.counts.offered = offered;
            self.counts.missed = offered
                .checked_sub(self.counts.reserved)
                .ok_or("reservation overflow")?;
            self.counts.unreserved_current = 0;
            self.last_elapsed = elapsed;
            return Ok(self.counts);
        }
        let window = elapsed / self.window_ns;
        if self.current_window != Some(window) {
            let start = window
                .checked_mul(self.window_ns)
                .ok_or("window overflow")?;
            let end = u64::try_from(
                (u128::from(start) + u128::from(self.window_ns)).min(u128::from(self.duration_ns)),
            )
            .map_err(|_| "window overflow")?;
            let before = self.cumulative(start)?;
            let offered = self.cumulative(end)?;
            self.counts.missed = before
                .checked_sub(self.counts.reserved)
                .ok_or("reservation overflow")?;
            self.counts.offered = offered;
            self.counts.unreserved_current =
                offered.checked_sub(before).ok_or("budget regression")?;
            self.current_window = Some(window);
        }
        self.last_elapsed = elapsed;
        Ok(self.counts)
    }

    pub(crate) fn advance(&mut self, elapsed: u64) -> Result<PacingCounts, Error> {
        let result = self.advance_checked(elapsed);
        if result.is_err() {
            self.invalid = true;
        }
        result
    }

    pub(crate) fn reserve(&mut self, elapsed: u64) -> Result<bool, Error> {
        self.advance(elapsed)?;
        if self.counts.unreserved_current == 0 {
            return Ok(false);
        }
        let Some(reserved) = self.counts.reserved.checked_add(1) else {
            self.invalid = true;
            return Err("reservation overflow");
        };
        self.counts.reserved = reserved;
        self.counts.unreserved_current -= 1;
        self.counts.max_reservation_lateness_ns = self
            .counts
            .max_reservation_lateness_ns
            .max(elapsed % self.window_ns);
        Ok(true)
    }
}

pub(crate) struct CollectedWindow {
    pub(crate) completed: u64,
    pub(crate) group_completed: Vec<u64>,
    pub(crate) latency_samples_ns: Vec<u64>,
    pub(crate) sample_capacity: usize,
}

pub(crate) struct CollectorStatus {
    pub(crate) completed: u64,
    pub(crate) retained_samples: usize,
    pub(crate) overflow_count: u64,
    pub(crate) evidence_valid: bool,
}

struct CollectorState {
    ordinal: u64,
    completed: u64,
    groups: Vec<u64>,
    samples: Vec<u64>,
    overflow: u64,
    valid: bool,
}

pub(crate) struct BoundedCollector {
    stride: u64,
    capacity: usize,
    state: Mutex<CollectorState>,
}

impl BoundedCollector {
    pub(crate) fn new(groups: usize, stride: u64, capacity: usize) -> Result<Self, Error> {
        if !(1..=4).contains(&groups) || stride == 0 || capacity == 0 {
            return Err("invalid collector configuration");
        }
        let mut samples = Vec::new();
        samples
            .try_reserve_exact(capacity)
            .map_err(|_| "sample allocation failed")?;
        Ok(Self {
            stride,
            capacity,
            state: Mutex::new(CollectorState {
                ordinal: 0,
                completed: 0,
                groups: vec![0; groups],
                samples,
                overflow: 0,
                valid: true,
            }),
        })
    }

    pub(crate) fn record_completed(&self, group: usize, latency_ns: u64) -> Result<(), Error> {
        let mut state = self.state.lock().map_err(|_| "collector lock poisoned")?;
        if group >= state.groups.len() {
            state.valid = false;
            return Err("unknown collector group");
        }
        // Continue exact completion accounting after sample overflow until caller stops.
        let values = state
            .ordinal
            .checked_add(1)
            .zip(state.completed.checked_add(1))
            .zip(state.groups[group].checked_add(1));
        let Some(((ordinal, completed), group_completed)) = values else {
            state.valid = false;
            return Err("collector counter overflow");
        };
        state.ordinal = ordinal;
        state.completed = completed;
        state.groups[group] = group_completed;
        if !state.valid {
            return Err("collector invalid");
        }
        if ordinal.is_multiple_of(self.stride) {
            if state.samples.len() >= self.capacity {
                state.valid = false;
                state.overflow = state
                    .overflow
                    .checked_add(1)
                    .ok_or("overflow counter exhausted")?;
                return Err("sample capacity exceeded");
            }
            state.samples.push(latency_ns);
        }
        Ok(())
    }

    pub(crate) fn take_window(
        &self,
        replacement: Option<Vec<u64>>,
    ) -> Result<CollectedWindow, Error> {
        let mut state = self.state.lock().map_err(|_| "collector lock poisoned")?;
        if !state.valid {
            return Err("collector invalid");
        }
        let replacement = match replacement {
            Some(buffer) if buffer.is_empty() && buffer.capacity() >= self.capacity => buffer,
            Some(_) => {
                state.valid = false;
                return Err("invalid replacement sample buffer");
            }
            None => {
                let mut buffer = Vec::new();
                if buffer.try_reserve_exact(self.capacity).is_err() {
                    state.valid = false;
                    return Err("sample allocation failed");
                }
                buffer
            }
        };
        let result = CollectedWindow {
            completed: state.completed,
            group_completed: state.groups.clone(),
            latency_samples_ns: std::mem::replace(&mut state.samples, replacement),
            sample_capacity: self.capacity,
        };
        state.completed = 0;
        state.groups.fill(0);
        Ok(result)
    }

    pub(crate) fn status(&self) -> Result<CollectorStatus, Error> {
        let state = self.state.lock().map_err(|_| "collector lock poisoned")?;
        Ok(CollectorStatus {
            completed: state.completed,
            retained_samples: state.samples.len(),
            overflow_count: state.overflow,
            evidence_valid: state.valid,
        })
    }
}
