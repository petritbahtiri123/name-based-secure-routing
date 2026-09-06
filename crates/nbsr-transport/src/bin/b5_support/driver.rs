//! Explicit paced benchmark driver, shared by Direct and NBSR harnesses only.
#[path = "coordinator.rs"]
pub(crate) mod coordinator;
#[path = "paced.rs"]
pub(crate) mod paced;
#[path = "runtime.rs"]
pub(crate) mod runtime;

pub(crate) use coordinator::Action;
use coordinator::{Clock, Config, Counts, Phase, Snapshot};
use runtime::{AsyncRun, InstantClock};
use std::collections::BTreeMap;
use std::io::Write;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::time::Duration;

type Error = &'static str;
const NS: u64 = 1_000_000_000;
const WINDOW: u64 = 10_000_000;
const STRIDE: u64 = 64;

#[derive(Clone)]
pub(crate) struct DriverConfig {
    pub(crate) groups: usize,
    pub(crate) streams: usize,
    pub(crate) depth: usize,
    pub(crate) payload: u64,
    pub(crate) numerator: u64,
    pub(crate) denominator: u64,
    pub(crate) duration_ns: u64,
    pub(crate) progress_ns: u64,
    pub(crate) sample_capacity: usize,
}

fn number(value: &str) -> Result<u64, Error> {
    if value.is_empty() || !value.bytes().all(|c| c.is_ascii_digit()) {
        return Err("expected unsigned decimal integer");
    }
    value.parse().map_err(|_| "integer overflow")
}
fn seconds(value: &str) -> Result<u64, Error> {
    let (whole, fraction) = value.split_once('.').unwrap_or((value, ""));
    if fraction.len() > 9 || (!fraction.is_empty() && !fraction.bytes().all(|c| c.is_ascii_digit()))
    {
        return Err("invalid exact seconds");
    }
    let fraction = if fraction.is_empty() {
        0
    } else {
        number(fraction)? * 10_u64.pow(9 - fraction.len() as u32)
    };
    number(whole)?
        .checked_mul(NS)
        .and_then(|v| v.checked_add(fraction))
        .ok_or("duration overflow")
}

pub(crate) fn prepare(
    args: impl IntoIterator<Item = String>,
) -> Result<Option<Arc<Driver>>, Error> {
    let args: Vec<String> = args.into_iter().collect();
    if !args.iter().any(|s| s.starts_with("--b5-")) {
        return Ok(None);
    }
    let known = [
        "--b5-rate-numerator",
        "--b5-rate-denominator",
        "--p2a-groups",
        "--p2a-streams",
        "--p2a-outstanding-per-stream",
        "--payload-bytes",
        "--p2a-duration-seconds",
        "--p2a-progress-seconds",
        "--p2a-runtime-workers",
        "--p2a-cooldown-seconds",
        "--lifecycle",
    ];
    let mut values = BTreeMap::new();
    for (index, flag) in args.iter().enumerate() {
        if flag.starts_with("--lifecycle-")
            || [
                "--offered-rate",
                "--b4-admission-rate",
                "--p2a-counter-control",
                "--p2a-operations-per-stream",
            ]
            .contains(&flag.as_str())
        {
            return Err("paced mode conflicts with selected workload");
        }
        if flag.starts_with("--b5-") && !known.contains(&flag.as_str()) {
            return Err("unknown paced flag");
        }
        if known.contains(&flag.as_str()) {
            let value = args
                .get(index + 1)
                .filter(|v| !v.starts_with("--"))
                .ok_or("missing paced argument")?;
            if values.insert(flag.as_str(), value.as_str()).is_some() {
                return Err("duplicate paced argument");
            }
        }
    }
    let required = |key| {
        values
            .get(key)
            .copied()
            .ok_or("required paced argument absent")
    };
    let numerator = number(required("--b5-rate-numerator")?)?;
    let denominator = number(required("--b5-rate-denominator")?)?;
    let groups = number(values.get("--p2a-groups").copied().unwrap_or("1"))?;
    let streams = number(required("--p2a-streams")?)?;
    let depth = number(
        values
            .get("--p2a-outstanding-per-stream")
            .copied()
            .unwrap_or("1"),
    )?;
    let payload = number(required("--payload-bytes")?)?;
    let duration_ns = seconds(required("--p2a-duration-seconds")?)?;
    let progress_ns = seconds(required("--p2a-progress-seconds")?)?;
    if numerator == 0
        || denominator == 0
        || !matches!(groups, 1 | 2 | 4)
        || !(1..=64).contains(&streams)
        || !(1..=64).contains(&depth)
        || !matches!(payload, 1024 | 16384)
        || duration_ns == 0
        || duration_ns > 7200 * NS
        || !(NS..=60 * NS).contains(&progress_ns)
        || number(values.get("--p2a-runtime-workers").copied().unwrap_or("1"))? != 1
        || values.get("--lifecycle").is_some_and(|v| *v != "warm")
        || seconds(values.get("--p2a-cooldown-seconds").copied().unwrap_or("0"))? != 0
    {
        return Err("unsupported paced workload");
    }
    let denom = u128::from(denominator)
        .checked_mul(u128::from(NS))
        .ok_or("rate overflow")?;
    let budget = u128::from(numerator)
        .checked_mul(u128::from(duration_ns))
        .ok_or("rate overflow")?
        / denom;
    u64::try_from(budget).map_err(|_| "complete offered budget overflow")?;
    let span = progress_ns
        .checked_mul(2)
        .and_then(|v| v.checked_add(WINDOW))
        .ok_or("sample span overflow")?;
    let offered = u128::from(numerator)
        .checked_mul(u128::from(span))
        .ok_or("sample budget overflow")?
        .div_ceil(denom);
    let bound = offered
        .checked_add(u128::from(groups * streams))
        .and_then(|v| v.checked_add(u128::from(groups * streams * depth)))
        .ok_or("sample bound overflow")?;
    let capacity = bound
        .div_ceil(u128::from(STRIDE))
        .checked_add(1)
        .ok_or("sample carry overflow")?;
    let config = DriverConfig {
        groups: groups as usize,
        streams: streams as usize,
        depth: depth as usize,
        payload,
        numerator,
        denominator,
        duration_ns,
        progress_ns,
        sample_capacity: usize::try_from(capacity).map_err(|_| "sample capacity overflow")?,
    };
    Driver::from_config(config).map(Some)
}

struct FinalSummary {
    end: u64,
    counts_json: String,
    max_outstanding: u64,
}
pub(crate) struct Driver {
    pub(crate) run: Arc<AsyncRun<InstantClock>>,
    pub(crate) config: DriverConfig,
    clock: Arc<InstantClock>,
    started: AtomicBool,
    final_summary: Mutex<Option<FinalSummary>>,
    pacing_tick: tokio::sync::Notify,
}
impl Driver {
    pub(crate) fn from_config(config: DriverConfig) -> Result<Arc<Self>, Error> {
        let clock = Arc::new(InstantClock::new());
        let run = Arc::new(AsyncRun::new(
            Config {
                groups: config.groups,
                streams_per_group: config.streams,
                max_outstanding: config.depth,
                rate_numerator: config.numerator,
                rate_denominator: config.denominator,
                window_ns: WINDOW,
                duration_ns: config.duration_ns,
                sample_stride: STRIDE,
                sample_capacity: config.sample_capacity,
            },
            Arc::clone(&clock),
        )?);
        Ok(Arc::new(Self {
            run,
            config,
            clock,
            started: AtomicBool::new(false),
            final_summary: Mutex::new(None),
            pacing_tick: tokio::sync::Notify::new(),
        }))
    }
    pub(crate) fn partition(&self, group: usize, stream: usize) -> Result<usize, Error> {
        if group >= self.config.groups || stream >= self.config.streams {
            return Err("unknown stream partition");
        }
        Ok(stream * self.config.groups + group)
    }
    pub(crate) fn failure_guard(self: &Arc<Self>) -> StreamFailureGuard {
        StreamFailureGuard {
            driver: Arc::clone(self),
            armed: true,
        }
    }
    pub(crate) async fn idle_until(&self, absolute_ns: u64) -> Result<(), Error> {
        loop {
            let notified = self.pacing_tick.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            if self.run.status().failed {
                return Err("paced run failed");
            }
            if self.clock.now_ns() >= absolute_ns {
                return Ok(());
            }
            tokio::select! {
                result = self.run.wait_failed() => return result,
                () = notified => {}
            }
        }
    }

    // One shared timer thread, not one blocking task per stream or operation.
    // Windows diagnostics showed Tokio's wait skipping 10ms windows while this
    // standard-library wait did not. The pacing budget/deadline is unchanged.
    fn pacing_clock(self: &Arc<Self>) -> Result<(), Error> {
        let mut failure = self.failure_guard();
        loop {
            let status = self.run.status();
            if status.failed {
                return Err("paced run failed");
            }
            let Some(origin) = status.origin_ns else {
                std::thread::sleep(Duration::from_millis(1));
                continue;
            };
            let deadline = status.deadline_ns.ok_or("missing pacing deadline")?;
            let now = self.clock.now_ns();
            if now >= deadline {
                self.pacing_tick.notify_waiters();
                failure.disarm();
                return Ok(());
            }
            let window = now.checked_sub(origin).ok_or("clock before origin")? / WINDOW;
            let next = u128::from(origin) + (u128::from(window) + 1) * u128::from(WINDOW);
            let next =
                u64::try_from(next.min(u128::from(deadline))).map_err(|_| "tick overflow")?;
            std::thread::sleep(Duration::from_nanos(next - now));
            self.pacing_tick.notify_waiters();
        }
    }
    pub(crate) fn start_publisher(
        self: &Arc<Self>,
    ) -> Result<std::thread::JoinHandle<Result<(), Error>>, Error> {
        if self.started.swap(true, Ordering::SeqCst) {
            self.run.fail();
            return Err("publisher already started");
        }
        let driver = Arc::clone(self);
        std::thread::Builder::new()
            .name("b5-progress".into())
            .spawn(move || {
                let mut guard = driver.failure_guard();
                let runtime = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .map_err(|_| "publisher runtime failed")?;
                let result = std::thread::scope(|scope| {
                    let timer = scope.spawn(|| driver.pacing_clock());
                    let result = runtime.block_on(async {
                        // Do not retain StdoutLock across readiness/timer awaits:
                        // group diagnostics also write stdout before readiness.
                        let mut sink = std::io::stdout();
                        driver.publish_to(&mut sink).await
                    });
                    if result.is_err() {
                        driver.run.fail();
                    }
                    let timer_result = timer.join().map_err(|_| "pacing timer panicked")?;
                    result.and(timer_result)
                });
                if result.is_ok() {
                    guard.disarm();
                }
                result
            })
            .map_err(|_| {
                self.run.fail();
                "publisher spawn failed"
            })
    }

    // Single worker owns publication. Raw NDJSON is written and flushed before
    // runtime acknowledges final publication. This method owns no transport.
    pub(crate) async fn publish_to(self: &Arc<Self>, sink: &mut impl Write) -> Result<(), Error> {
        let mut failure = self.failure_guard();
        self.run.wait_ready().await?;
        let period = Duration::from_nanos(self.config.progress_ns);
        let mut ticks = tokio::time::interval_at(tokio::time::Instant::now() + period, period);
        ticks.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut previous_completed = 0;
        loop {
            let final_window = tokio::select! {
                biased;
                result = self.run.wait_drained() => { result?; true },
                _ = ticks.tick() => false,
            };
            self.run.publish(final_window, |snapshot| {
                let mut line = progress_json(snapshot, previous_completed, self.config.payload);
                line.push('\n');
                sink.write_all(line.as_bytes())?;
                sink.flush()?;
                previous_completed = snapshot.totals.completed;
                if final_window {
                    let summary = FinalSummary {
                        end: snapshot.end_ns,
                        counts_json: counts_json(snapshot),
                        max_outstanding: snapshot.max_outstanding_observed,
                    };
                    *self
                        .final_summary
                        .lock()
                        .map_err(|_| std::io::Error::other("final state poisoned"))? =
                        Some(summary);
                }
                Ok(())
            })?;
            if final_window {
                failure.disarm();
                return Ok(());
            }
        }
    }

    // Call only after publisher AND all group threads successfully joined and
    // cleanup was sampled once. cleanup_json must be output from the existing
    // internal cleanup serializer, never CLI/file/network input.
    pub(crate) fn final_record_after_joins(&self, cleanup_json: &str) -> Result<String, Error> {
        let status = self.run.status();
        if !status.postflight_allowed
            || !status.sealed
            || status
                .deadline_ns
                .zip(status.origin_ns)
                .and_then(|(deadline, origin)| deadline.checked_sub(origin))
                != Some(self.config.duration_ns)
            || !cleanup_json.starts_with('{')
            || !cleanup_json.ends_with('}')
        {
            return Err("final evidence unavailable");
        }
        let retained = self
            .final_summary
            .lock()
            .map_err(|_| "final state poisoned")?;
        let s = retained.as_ref().ok_or("no final progress")?;
        let drain = s
            .end
            .checked_sub(self.config.duration_ns)
            .ok_or("final before deadline")?;
        Ok(format!(
            "{{\"schema\":\"nbsr-b5-grouped-final-v1\",\"groups\":{},\"payload_bytes\":{},\"streams_per_group\":{},\"outstanding_per_stream\":{},\"measurement_duration_ns\":{},\"drain_duration_ns\":{}, {},\"max_outstanding_observed\":{},\"errors\":0,\"timeouts\":0,\"collector_overflow_count\":0,\"all_groups_joined\":true,\"source_cleanup\":{},\"evidence_valid\":true}}",
            self.config.groups,
            self.config.payload,
            self.config.streams,
            self.config.depth,
            self.config.duration_ns,
            drain,
            s.counts_json,
            s.max_outstanding,
            cleanup_json
        ))
    }
}

pub(crate) struct StreamFailureGuard {
    driver: Arc<Driver>,
    armed: bool,
}
impl StreamFailureGuard {
    pub(crate) fn disarm(&mut self) {
        self.armed = false;
    }
}
impl Drop for StreamFailureGuard {
    fn drop(&mut self) {
        if self.armed {
            self.driver.run.fail();
        }
    }
}

fn counters(c: &Counts) -> String {
    format!(
        "\"offered\":{},\"reserved\":{},\"issued\":{},\"completed\":{},\"missed\":{},\"unreserved_current\":{}",
        c.offered, c.reserved, c.issued, c.completed, c.missed, c.unreserved_current
    )
}
fn counts_json(snapshot: &Snapshot) -> String {
    let rows = snapshot
        .groups
        .iter()
        .enumerate()
        .map(|(id, c)| format!("{{\"group_id\":{id},{}}}", counters(c)))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{},\"group_counters\":[{}]",
        counters(&snapshot.totals),
        rows
    )
}
fn progress_json(snapshot: &Snapshot, previous_completed: u64, payload: u64) -> String {
    let mut samples = snapshot.latency_samples_ns.clone();
    samples.sort_unstable();
    let quantile = |percent: usize| {
        if samples.is_empty() {
            "null".to_owned()
        } else {
            samples[(samples.len() as u128 * percent as u128).div_ceil(100) as usize - 1]
                .to_string()
        }
    };
    let phase = match snapshot.phase {
        Phase::Steady => "steady",
        Phase::Mixed => "mixed",
        Phase::Drain => "drain",
    };
    let goodput =
        (snapshot.totals.completed - previous_completed) as f64 * 2.0 * payload as f64 * NS as f64
            / (snapshot.end_ns - snapshot.start_ns) as f64;
    format!(
        "{{\"schema\":\"nbsr-b5-grouped-progress-v1\",\"event\":\"b5_grouped_progress\",\"window_index\":{},\"phase\":\"{}\",\"elapsed_ns\":{},\"interval_start_ns\":{},\"interval_end_ns\":{},\"issue_deadline_ns\":{}, {},\"goodput_bytes_per_second\":{},\"sample_count\":{},\"sample_stride\":{},\"sample_capacity\":{},\"sample_overflow_count\":{},\"p50_latency_ns\":{},\"p95_latency_ns\":{},\"p99_latency_ns\":{},\"max_reservation_lateness_ns\":{},\"errors\":0,\"timeouts\":0,\"evidence_valid\":true}}",
        snapshot.window_index,
        phase,
        snapshot.end_ns,
        snapshot.start_ns,
        snapshot.end_ns,
        snapshot.issue_deadline_ns,
        counts_json(snapshot),
        goodput,
        snapshot.sample_count,
        snapshot.sample_stride,
        snapshot.sample_capacity,
        snapshot.sample_overflow_count,
        quantile(50),
        quantile(95),
        quantile(99),
        snapshot.max_reservation_lateness_ns
    )
}
