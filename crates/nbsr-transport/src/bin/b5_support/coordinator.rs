//! Test-only paced lifecycle/accounting coordinator. No transport operations.
use super::paced::{BoundedCollector, PacingWindow};
use std::sync::{Arc, Mutex};

type Error = &'static str;
pub(crate) trait Clock: Send + Sync {
    fn now_ns(&self) -> u64;
}
pub(crate) struct Config {
    pub(crate) groups: usize,
    pub(crate) streams_per_group: usize,
    pub(crate) max_outstanding: usize,
    pub(crate) rate_numerator: u64,
    pub(crate) rate_denominator: u64,
    pub(crate) window_ns: u64,
    pub(crate) duration_ns: u64,
    pub(crate) sample_stride: u64,
    pub(crate) sample_capacity: usize,
}
#[derive(Debug, PartialEq)]
pub(crate) enum Action {
    AwaitReady,
    Permit,
    Read,
    WaitUntil(u64),
    Draining,
}
#[derive(Debug, PartialEq)]
pub(crate) enum Phase {
    Steady,
    Mixed,
    Drain,
}
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub(crate) struct Counts {
    pub(crate) offered: u64,
    pub(crate) reserved: u64,
    pub(crate) issued: u64,
    pub(crate) completed: u64,
    pub(crate) missed: u64,
    pub(crate) unreserved_current: u64,
}
impl Counts {
    fn add(&mut self, other: Self) -> Result<(), Error> {
        macro_rules! add { ($($f:ident),*) => { $(self.$f = self.$f.checked_add(other.$f).ok_or("counter overflow")?;)* }; }
        add!(
            offered,
            reserved,
            issued,
            completed,
            missed,
            unreserved_current
        );
        Ok(())
    }
}
pub(crate) struct Status {
    pub(crate) origin_ns: Option<u64>,
    pub(crate) deadline_ns: Option<u64>,
    pub(crate) failed: bool,
    pub(crate) postflight_allowed: bool,
    pub(crate) all_groups_drained: bool,
    pub(crate) sealed: bool,
}
pub(crate) struct Snapshot {
    pub(crate) window_index: u64,
    pub(crate) start_ns: u64,
    pub(crate) end_ns: u64,
    pub(crate) issue_deadline_ns: u64,
    pub(crate) phase: Phase,
    pub(crate) totals: Counts,
    pub(crate) groups: Vec<Counts>,
    pub(crate) sample_count: usize,
    pub(crate) latency_samples_ns: Vec<u64>,
}
struct Partition {
    pacer: PacingWindow,
    pending: bool,
    issued: u64,
    completed: u64,
}
struct State {
    failed: bool,
    ready: Vec<bool>,
    drained: Vec<bool>,
    guards: Vec<bool>,
    origin: Option<u64>,
    deadline: Option<u64>,
    last_clock: Option<u64>,
    last_end: u64,
    index: u64,
    sealed: bool,
    published: bool,
    partitions: Vec<Partition>,
    collector: BoundedCollector,
}
pub(crate) struct PacedRun<C: Clock> {
    config: Config,
    clock: Arc<C>,
    state: Mutex<State>,
}
impl<C: Clock> PacedRun<C> {
    pub(crate) fn new(config: Config, clock: Arc<C>) -> Result<Self, Error> {
        if !matches!(config.groups, 1 | 2 | 4)
            || !(1..=64).contains(&config.streams_per_group)
            || !(1..=64).contains(&config.max_outstanding)
        {
            return Err("invalid coordinator bounds");
        }
        let count = config
            .groups
            .checked_mul(config.streams_per_group)
            .ok_or("partition overflow")?;
        let partitions = (0..count)
            .map(|id| {
                Ok(Partition {
                    pacer: PacingWindow::new(
                        config.rate_numerator,
                        config.rate_denominator,
                        count,
                        id,
                        config.window_ns,
                        config.duration_ns,
                    )?,
                    pending: false,
                    issued: 0,
                    completed: 0,
                })
            })
            .collect::<Result<Vec<_>, Error>>()?;
        let collector =
            BoundedCollector::new(config.groups, config.sample_stride, config.sample_capacity)?;
        let state = State {
            failed: false,
            ready: vec![false; config.groups],
            drained: vec![false; config.groups],
            guards: vec![false; config.groups],
            origin: None,
            deadline: None,
            last_clock: None,
            last_end: 0,
            index: 0,
            sealed: false,
            published: false,
            partitions,
            collector,
        };
        Ok(Self {
            config,
            clock,
            state: Mutex::new(state),
        })
    }
    // This is the sole mutation entry. Inner collector locks are always acquired
    // while holding this outer lock. Clock reads cannot precede lock acquisition.
    fn change<T>(
        &self,
        operation: impl FnOnce(&mut State, u64) -> Result<T, Error>,
    ) -> Result<T, Error> {
        let mut state = self.state.lock().map_err(|_| "coordinator lock poisoned")?;
        if state.failed {
            return Err("coordinator failed");
        }
        let now = self.clock.now_ns();
        if state.last_clock.is_some_and(|last| now < last) {
            state.failed = true;
            return Err("clock regressed");
        }
        state.last_clock = Some(now);
        let result = operation(&mut state, now);
        if result.is_err() {
            state.failed = true;
        }
        result
    }
    pub(crate) fn status(&self) -> Status {
        let state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        let failed = state.failed || self.state.is_poisoned();
        Status {
            origin_ns: state.origin,
            deadline_ns: state.deadline,
            failed,
            postflight_allowed: state.published && !failed,
            all_groups_drained: state.origin.is_some() && state.drained.iter().all(|value| *value),
            sealed: state.sealed,
        }
    }
    pub(crate) fn fail(&self) {
        self.state.lock().unwrap_or_else(|e| e.into_inner()).failed = true;
    }
    pub(crate) fn ready(&self, group: usize) -> Result<(), Error> {
        self.change(|s, now| {
            let ready = s.ready.get_mut(group).ok_or("unknown group")?;
            if *ready || s.sealed {
                return Err("duplicate readiness");
            }
            *ready = true;
            if s.ready.iter().all(|v| *v) {
                s.deadline = Some(
                    now.checked_add(self.config.duration_ns)
                        .ok_or("deadline overflow")?,
                );
                s.origin = Some(now);
            }
            Ok(())
        })
    }
    pub(crate) fn next(&self, partition: usize) -> Result<Action, Error> {
        self.change(|s, now| {
            if s.sealed || partition >= s.partitions.len() {
                return Err("invalid partition state");
            }
            let Some(origin) = s.origin else {
                return Ok(Action::AwaitReady);
            };
            if s.drained[partition % self.config.groups] {
                return Err("group already drained");
            }
            let elapsed = now.checked_sub(origin).ok_or("clock before origin")?;
            let p = &mut s.partitions[partition];
            if p.pending {
                return Err("write still pending");
            }
            let outstanding = p
                .issued
                .checked_sub(p.completed)
                .ok_or("completion mismatch")?;
            p.pacer.advance(elapsed)?;
            if outstanding < self.config.max_outstanding as u64 && p.pacer.reserve(elapsed)? {
                p.pending = true;
                return Ok(Action::Permit);
            }
            if outstanding > 0 {
                return Ok(Action::Read);
            }
            if elapsed >= self.config.duration_ns {
                return Ok(Action::Draining);
            }
            let next = (u128::from(elapsed / self.config.window_ns) + 1)
                * u128::from(self.config.window_ns);
            let next = next.min(u128::from(self.config.duration_ns)) as u64;
            Ok(Action::WaitUntil(
                origin.checked_add(next).ok_or("wake deadline overflow")?,
            ))
        })
    }
    pub(crate) fn issued(&self, partition: usize) -> Result<(), Error> {
        self.change(|s, _| {
            if s.sealed {
                return Err("measurement sealed");
            }
            let p = s.partitions.get_mut(partition).ok_or("unknown partition")?;
            if !p.pending {
                return Err("write without reservation");
            }
            p.issued = p.issued.checked_add(1).ok_or("issued overflow")?;
            p.pending = false;
            Ok(())
        })
    }
    pub(crate) fn completed(&self, partition: usize, latency_ns: u64) -> Result<(), Error> {
        self.change(|s, _| {
            if s.sealed {
                return Err("measurement sealed");
            }
            let p = s.partitions.get_mut(partition).ok_or("unknown partition")?;
            if p.completed >= p.issued {
                return Err("completion without issue");
            }
            p.completed = p.completed.checked_add(1).ok_or("completed overflow")?;
            s.collector
                .record_completed(partition % self.config.groups, latency_ns)
        })
    }
    pub(crate) fn drained(&self, group: usize) -> Result<(), Error> {
        self.change(|s, now| {
            if group >= self.config.groups || s.sealed || s.drained[group] {
                return Err("invalid drain");
            }
            if now < s.deadline.ok_or("not started")? {
                return Err("issuing still open");
            }
            if s.partitions
                .iter()
                .skip(group)
                .step_by(self.config.groups)
                .any(|p| p.pending || p.issued != p.completed)
            {
                return Err("outstanding work");
            }
            s.drained[group] = true;
            Ok(())
        })
    }
    pub(crate) fn snapshot(&self, final_window: bool) -> Result<Snapshot, Error> {
        self.change(|s, now| {
            if s.sealed || (final_window && !s.drained.iter().all(|v| *v)) {
                return Err("invalid final state");
            }
            let end = now
                .checked_sub(s.origin.ok_or("not started")?)
                .ok_or("clock before origin")?;
            if end <= s.last_end {
                return Err("empty snapshot interval");
            }
            let mut groups = vec![Counts::default(); self.config.groups];
            for (id, p) in s.partitions.iter_mut().enumerate() {
                let c = p.pacer.advance(end)?;
                groups[id % self.config.groups].add(Counts {
                    offered: c.offered,
                    reserved: c.reserved,
                    missed: c.missed,
                    unreserved_current: c.unreserved_current,
                    issued: p.issued,
                    completed: p.completed,
                })?;
            }
            let mut totals = Counts::default();
            for group in &groups {
                totals.add(*group)?;
            }
            let window = s.collector.take_window()?;
            let phase = if end <= self.config.duration_ns {
                Phase::Steady
            } else if s.last_end >= self.config.duration_ns {
                Phase::Drain
            } else {
                Phase::Mixed
            };
            s.index = s.index.checked_add(1).ok_or("window index overflow")?;
            let snapshot = Snapshot {
                window_index: s.index,
                start_ns: s.last_end,
                end_ns: end,
                issue_deadline_ns: self.config.duration_ns,
                phase,
                totals,
                groups,
                sample_count: window.latency_samples_ns.len(),
                latency_samples_ns: window.latency_samples_ns,
            };
            s.last_end = end;
            s.sealed = final_window;
            Ok(snapshot)
        })
    }
    pub(crate) fn published_final(&self, index: u64) -> Result<(), Error> {
        self.change(|s, _| {
            if !s.sealed || s.published || index != s.index {
                return Err("invalid publication");
            }
            s.published = true;
            Ok(())
        })
    }
    pub(crate) fn group_guard(self: &Arc<Self>, group: usize) -> Result<GroupGuard<C>, Error> {
        self.change(|s, _| {
            let claimed = s.guards.get_mut(group).ok_or("unknown group")?;
            if *claimed || s.ready[group] {
                return Err("guard already claimed or late");
            }
            *claimed = true;
            Ok(GroupGuard {
                run: Arc::clone(self),
                finished: false,
            })
        })
    }
}
pub(crate) struct GroupGuard<C: Clock> {
    run: Arc<PacedRun<C>>,
    finished: bool,
}
impl<C: Clock> GroupGuard<C> {
    pub(crate) fn finish(mut self) -> Result<(), Error> {
        if !self.run.status().postflight_allowed {
            return Err("postflight not allowed");
        }
        self.finished = true;
        Ok(())
    }
}
impl<C: Clock> Drop for GroupGuard<C> {
    fn drop(&mut self) {
        if !self.finished {
            self.run.fail();
        }
    }
}
