//! Fixed-cardinality benchmark-only lifecycle profiling.

use std::array;
use std::sync::LazyLock;
use std::sync::atomic::{AtomicU8, AtomicU64, Ordering};
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(usize)]
pub enum LifecyclePhase {
    SourcePrepareAuthorize,
    SourceControlWrite,
    SourceAdmissionWaitRead,
    SourceAdmissionConfirm,
    QuinnOpenBi,
    SourceApplicationSetup,
    SourceFirstExchange,
    SourceReleaseCleanup,
    DestinationControlRead,
    DestinationBindingReplaySequenceChannel,
    DestinationPrepareOpen,
    DestinationAudit,
    DestinationReplayStateCommit,
    DestinationAuthorize,
    DestinationResponseWrite,
    QuinnAcceptBi,
    DestinationFirstExchange,
    DestinationReleaseCleanup,
}

impl LifecyclePhase {
    pub const ALL: [Self; 18] = [
        Self::SourcePrepareAuthorize,
        Self::SourceControlWrite,
        Self::SourceAdmissionWaitRead,
        Self::SourceAdmissionConfirm,
        Self::QuinnOpenBi,
        Self::SourceApplicationSetup,
        Self::SourceFirstExchange,
        Self::SourceReleaseCleanup,
        Self::DestinationControlRead,
        Self::DestinationBindingReplaySequenceChannel,
        Self::DestinationPrepareOpen,
        Self::DestinationAudit,
        Self::DestinationReplayStateCommit,
        Self::DestinationAuthorize,
        Self::DestinationResponseWrite,
        Self::QuinnAcceptBi,
        Self::DestinationFirstExchange,
        Self::DestinationReleaseCleanup,
    ];

    pub const fn label(self) -> &'static str {
        match self {
            Self::SourcePrepareAuthorize => "source_prepare_authorize",
            Self::SourceControlWrite => "source_control_write",
            Self::SourceAdmissionWaitRead => "source_admission_wait_read",
            Self::SourceAdmissionConfirm => "source_admission_confirm",
            Self::QuinnOpenBi => "quinn_open_bi",
            Self::SourceApplicationSetup => "source_application_setup",
            Self::SourceFirstExchange => "source_first_exchange",
            Self::SourceReleaseCleanup => "source_release_cleanup",
            Self::DestinationControlRead => "destination_control_read",
            Self::DestinationBindingReplaySequenceChannel => {
                "destination_binding_replay_sequence_channel"
            }
            Self::DestinationPrepareOpen => "destination_prepare_open",
            Self::DestinationAudit => "destination_audit",
            Self::DestinationReplayStateCommit => "destination_replay_state_commit",
            Self::DestinationAuthorize => "destination_authorize",
            Self::DestinationResponseWrite => "destination_response_write",
            Self::QuinnAcceptBi => "quinn_accept_bi",
            Self::DestinationFirstExchange => "destination_first_exchange",
            Self::DestinationReleaseCleanup => "destination_release_cleanup",
        }
    }
}

struct PhaseCounters {
    calls: AtomicU64,
    successes: AtomicU64,
    failures: AtomicU64,
    total_ns: AtomicU64,
    min_ns: AtomicU64,
    max_ns: AtomicU64,
    histogram: [AtomicU64; 64],
}

impl PhaseCounters {
    fn new() -> Self {
        Self {
            calls: AtomicU64::new(0),
            successes: AtomicU64::new(0),
            failures: AtomicU64::new(0),
            total_ns: AtomicU64::new(0),
            min_ns: AtomicU64::new(u64::MAX),
            max_ns: AtomicU64::new(0),
            histogram: array::from_fn(|_| AtomicU64::new(0)),
        }
    }
}

pub struct Profiler {
    enabled: bool,
    phases: [PhaseCounters; 18],
}

static GLOBAL: LazyLock<Profiler> =
    LazyLock::new(|| Profiler::new(std::env::var_os("NBSR_P2B_PROFILE").is_some()));
static PROCESS_ROLE: AtomicU8 = AtomicU8::new(0);

pub fn global() -> &'static Profiler {
    &GLOBAL
}
pub fn set_destination_role() {
    PROCESS_ROLE.store(2, Ordering::Relaxed);
}
pub fn is_destination_role() -> bool {
    PROCESS_ROLE.load(Ordering::Relaxed) == 2
}

impl Profiler {
    pub fn new(enabled: bool) -> Self {
        Self {
            enabled,
            phases: array::from_fn(|_| PhaseCounters::new()),
        }
    }

    pub fn measure<T, E>(
        &self,
        phase: LifecyclePhase,
        operation: impl FnOnce() -> Result<T, E>,
    ) -> Result<T, E> {
        if !self.enabled {
            return operation();
        }
        let started = Instant::now();
        let result = operation();
        self.record_ns(phase, started.elapsed().as_nanos() as u64, result.is_ok());
        result
    }

    pub fn record_ns(&self, phase: LifecyclePhase, elapsed_ns: u64, success: bool) {
        if !self.enabled {
            return;
        }
        let counters = &self.phases[phase as usize];
        counters.calls.fetch_add(1, Ordering::Relaxed);
        if success {
            counters.successes.fetch_add(1, Ordering::Relaxed);
        } else {
            counters.failures.fetch_add(1, Ordering::Relaxed);
        }
        counters.total_ns.fetch_add(elapsed_ns, Ordering::Relaxed);
        counters.min_ns.fetch_min(elapsed_ns, Ordering::Relaxed);
        counters.max_ns.fetch_max(elapsed_ns, Ordering::Relaxed);
        let bucket = elapsed_ns.max(1).ilog2() as usize;
        counters.histogram[bucket.min(63)].fetch_add(1, Ordering::Relaxed);
    }

    pub fn snapshot(&self) -> ProfileSnapshot {
        ProfileSnapshot {
            phases: array::from_fn(|index| snapshot_phase(&self.phases[index])),
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct PhaseSnapshot {
    pub calls: u64,
    pub successes: u64,
    pub failures: u64,
    pub total_ns: u64,
    pub min_ns: u64,
    pub max_ns: u64,
    pub p50_ns: u64,
    pub p95_ns: u64,
    pub p99_ns: u64,
}

pub struct ProfileSnapshot {
    phases: [PhaseSnapshot; 18],
}

impl ProfileSnapshot {
    pub fn phase(&self, phase: LifecyclePhase) -> PhaseSnapshot {
        self.phases[phase as usize]
    }
    pub fn total_calls(&self) -> u64 {
        self.phases.iter().map(|phase| phase.calls).sum()
    }
    pub fn total_successes(&self) -> u64 {
        self.phases.iter().map(|phase| phase.successes).sum()
    }

    pub fn to_json(&self, role: &str) -> String {
        let phases = LifecyclePhase::ALL.iter().map(|phase| {
            let value = self.phase(*phase);
            format!("{{\"phase\":\"{}\",\"calls\":{},\"successes\":{},\"failures\":{},\"total_ns\":{},\"mean_ns\":{},\"min_ns\":{},\"max_ns\":{},\"p50_ns\":{},\"p95_ns\":{},\"p99_ns\":{}}}", phase.label(), value.calls, value.successes, value.failures, value.total_ns, value.total_ns.checked_div(value.calls).unwrap_or(0), value.min_ns, value.max_ns, value.p50_ns, value.p95_ns, value.p99_ns)
        }).collect::<Vec<_>>().join(",");
        format!(
            "{{\"event\":\"p2b_profile\",\"schema\":\"nbsr-p2b-profile-v1\",\"role\":\"{role}\",\"phases\":[{phases}]}}"
        )
    }
}

fn snapshot_phase(counters: &PhaseCounters) -> PhaseSnapshot {
    let calls = counters.calls.load(Ordering::Relaxed);
    let quantile = |numerator: u64| {
        if calls == 0 {
            return 0;
        }
        let target = (calls * numerator).div_ceil(100);
        let mut seen = 0;
        for (index, bucket) in counters.histogram.iter().enumerate() {
            seen += bucket.load(Ordering::Relaxed);
            if seen >= target {
                return 1_u64.checked_shl(index as u32).unwrap_or(u64::MAX);
            }
        }
        0
    };
    let min_ns = if calls == 0 {
        0
    } else {
        counters.min_ns.load(Ordering::Relaxed)
    };
    let max_ns = counters.max_ns.load(Ordering::Relaxed);
    let bounded = |value: u64| value.clamp(min_ns, max_ns);
    PhaseSnapshot {
        calls,
        successes: counters.successes.load(Ordering::Relaxed),
        failures: counters.failures.load(Ordering::Relaxed),
        total_ns: counters.total_ns.load(Ordering::Relaxed),
        min_ns,
        max_ns,
        p50_ns: bounded(quantile(50)),
        p95_ns: bounded(quantile(95)),
        p99_ns: bounded(quantile(99)),
    }
}
