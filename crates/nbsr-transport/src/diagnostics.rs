//! Opt-in, aggregate ownership diagnostics for controlled performance runs.

use std::array;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

const OWNER_COUNT: usize = 11;

#[derive(Clone, Copy)]
pub enum DiagnosticOwner {
    TransportSession = 0,
    ServiceChannel = 1,
    ApplicationStream = 2,
    PendingRoutes = 3,
    ChannelRegistry = 4,
    StreamRegistry = 5,
    AuditQueue = 6,
    NbsrTask = 7,
    ReplayState = 8,
    QuicConnection = 9,
    QuicStream = 10,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct LifecycleSnapshot {
    pub created: u64,
    pub completed: u64,
    pub failed_or_cancelled: u64,
    pub current_live: u64,
    pub high_water_live: u64,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct CollectionSnapshot {
    pub inserts: u64,
    pub removals: u64,
    pub current_entries: u64,
    pub high_water_entries: u64,
    pub retained_capacity: u64,
    pub high_water_retained_capacity: u64,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct DiagnosticSnapshot {
    pub transport_sessions: LifecycleSnapshot,
    pub service_channels: LifecycleSnapshot,
    pub application_streams: LifecycleSnapshot,
    pub nbsr_tasks: LifecycleSnapshot,
    pub pending_routes: CollectionSnapshot,
    pub channel_registry: CollectionSnapshot,
    pub stream_registry: CollectionSnapshot,
    pub audit_queue: CollectionSnapshot,
    pub replay_state: CollectionSnapshot,
    pub quic_connections: LifecycleSnapshot,
    pub quic_streams: LifecycleSnapshot,
}

impl DiagnosticSnapshot {
    #[must_use]
    pub fn json_line(self, role: &str, timestamp_ns: u128, phase: &str) -> String {
        let lifecycle = |name: &str, value: LifecycleSnapshot| {
            format!(
                "\"{name}_created\":{},\"{name}_completed\":{},\"{name}_failed_or_cancelled\":{},\"{name}_current_live\":{},\"{name}_high_water_live\":{}",
                value.created,
                value.completed,
                value.failed_or_cancelled,
                value.current_live,
                value.high_water_live
            )
        };
        let collection = |name: &str, value: CollectionSnapshot| {
            format!(
                "\"{name}_inserts\":{},\"{name}_removals\":{},\"{name}_current_entries\":{},\"{name}_high_water_entries\":{},\"{name}_retained_capacity\":{},\"{name}_high_water_retained_capacity\":{}",
                value.inserts,
                value.removals,
                value.current_entries,
                value.high_water_entries,
                value.retained_capacity,
                value.high_water_retained_capacity
            )
        };
        format!(
            "{{\"event\":\"diagnostic\",\"schema\":\"nbsr-rust-ownership-v1\",\"role\":\"{role}\",\"timestamp_ns\":{timestamp_ns},\"phase\":\"{phase}\",{},{},{},{},{},{},{},{},{},{},{}}}",
            lifecycle("transport_sessions", self.transport_sessions),
            lifecycle("service_channels", self.service_channels),
            lifecycle("application_streams", self.application_streams),
            lifecycle("nbsr_tasks", self.nbsr_tasks),
            lifecycle("quic_connections", self.quic_connections),
            lifecycle("quic_streams", self.quic_streams),
            collection("pending_routes", self.pending_routes),
            collection("channel_registry", self.channel_registry),
            collection("stream_registry", self.stream_registry),
            collection("audit_queue", self.audit_queue),
            collection("replay_state", self.replay_state),
        )
    }
}

#[derive(Default)]
struct LifecycleMetric {
    created: AtomicU64,
    completed: AtomicU64,
    failed: AtomicU64,
    live: AtomicU64,
    high_water: AtomicU64,
}

#[derive(Default)]
struct CollectionMetric {
    inserts: AtomicU64,
    removals: AtomicU64,
    entries: AtomicU64,
    high_water_entries: AtomicU64,
    capacity: AtomicU64,
    high_water_capacity: AtomicU64,
}

pub struct Diagnostics {
    enabled: AtomicBool,
    lifecycle: [LifecycleMetric; OWNER_COUNT],
    collections: [CollectionMetric; OWNER_COUNT],
}

impl Diagnostics {
    #[must_use]
    pub fn new(enabled: bool) -> Self {
        Self {
            enabled: AtomicBool::new(enabled),
            lifecycle: array::from_fn(|_| LifecycleMetric::default()),
            collections: array::from_fn(|_| CollectionMetric::default()),
        }
    }

    pub fn created(&self, owner: DiagnosticOwner) {
        if !self.enabled.load(Ordering::Relaxed) {
            return;
        }
        let metric = &self.lifecycle[owner as usize];
        metric.created.fetch_add(1, Ordering::Relaxed);
        let live = metric.live.fetch_add(1, Ordering::Relaxed) + 1;
        metric.high_water.fetch_max(live, Ordering::Relaxed);
    }

    pub fn completed(&self, owner: DiagnosticOwner) {
        self.terminal(owner, true);
    }

    pub fn failed(&self, owner: DiagnosticOwner) {
        self.terminal(owner, false);
    }

    fn terminal(&self, owner: DiagnosticOwner, success: bool) {
        if !self.enabled.load(Ordering::Relaxed) {
            return;
        }
        let metric = &self.lifecycle[owner as usize];
        let mut live = metric.live.load(Ordering::Relaxed);
        loop {
            if live == 0 {
                return;
            }
            match metric.live.compare_exchange_weak(
                live,
                live - 1,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => break,
                Err(observed) => live = observed,
            }
        }
        if success {
            metric.completed.fetch_add(1, Ordering::Relaxed);
        } else {
            metric.failed.fetch_add(1, Ordering::Relaxed);
        }
    }

    pub fn observe_collection(&self, owner: DiagnosticOwner, entries: usize, capacity: usize) {
        if !self.enabled.load(Ordering::Relaxed) {
            return;
        }
        let metric = &self.collections[owner as usize];
        let previous = metric.entries.swap(entries as u64, Ordering::Relaxed);
        if entries as u64 > previous {
            metric
                .inserts
                .fetch_add(entries as u64 - previous, Ordering::Relaxed);
        } else {
            metric
                .removals
                .fetch_add(previous - entries as u64, Ordering::Relaxed);
        }
        metric
            .high_water_entries
            .fetch_max(entries as u64, Ordering::Relaxed);
        metric.capacity.store(capacity as u64, Ordering::Relaxed);
        metric
            .high_water_capacity
            .fetch_max(capacity as u64, Ordering::Relaxed);
    }

    #[must_use]
    pub fn snapshot(&self) -> DiagnosticSnapshot {
        DiagnosticSnapshot {
            transport_sessions: self.lifecycle_snapshot(DiagnosticOwner::TransportSession),
            service_channels: self.lifecycle_snapshot(DiagnosticOwner::ServiceChannel),
            application_streams: self.lifecycle_snapshot(DiagnosticOwner::ApplicationStream),
            nbsr_tasks: self.lifecycle_snapshot(DiagnosticOwner::NbsrTask),
            pending_routes: self.collection_snapshot(DiagnosticOwner::PendingRoutes),
            channel_registry: self.collection_snapshot(DiagnosticOwner::ChannelRegistry),
            stream_registry: self.collection_snapshot(DiagnosticOwner::StreamRegistry),
            audit_queue: self.collection_snapshot(DiagnosticOwner::AuditQueue),
            replay_state: self.collection_snapshot(DiagnosticOwner::ReplayState),
            quic_connections: self.lifecycle_snapshot(DiagnosticOwner::QuicConnection),
            quic_streams: self.lifecycle_snapshot(DiagnosticOwner::QuicStream),
        }
    }

    fn lifecycle_snapshot(&self, owner: DiagnosticOwner) -> LifecycleSnapshot {
        let metric = &self.lifecycle[owner as usize];
        LifecycleSnapshot {
            created: metric.created.load(Ordering::Relaxed),
            completed: metric.completed.load(Ordering::Relaxed),
            failed_or_cancelled: metric.failed.load(Ordering::Relaxed),
            current_live: metric.live.load(Ordering::Relaxed),
            high_water_live: metric.high_water.load(Ordering::Relaxed),
        }
    }

    fn collection_snapshot(&self, owner: DiagnosticOwner) -> CollectionSnapshot {
        let metric = &self.collections[owner as usize];
        CollectionSnapshot {
            inserts: metric.inserts.load(Ordering::Relaxed),
            removals: metric.removals.load(Ordering::Relaxed),
            current_entries: metric.entries.load(Ordering::Relaxed),
            high_water_entries: metric.high_water_entries.load(Ordering::Relaxed),
            retained_capacity: metric.capacity.load(Ordering::Relaxed),
            high_water_retained_capacity: metric.high_water_capacity.load(Ordering::Relaxed),
        }
    }
}

static GLOBAL: OnceLock<Diagnostics> = OnceLock::new();

#[must_use]
pub fn global() -> &'static Diagnostics {
    GLOBAL.get_or_init(|| Diagnostics::new(false))
}

/// Enables diagnostics for the remainder of this process. P1A uses a fresh
/// benchmark peer process for every run, so counters never cross run boundaries.
pub fn enable_global() {
    global().enabled.store(true, Ordering::Relaxed);
}
