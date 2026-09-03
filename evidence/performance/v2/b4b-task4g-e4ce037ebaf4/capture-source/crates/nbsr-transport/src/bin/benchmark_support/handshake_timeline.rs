//! Benchmark-only observation. Never consulted by transport/control logic.
use std::future::Future;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

const MAGIC: u64 = 0x4e425352544c3031;
const GUARD: u64 = 0x719f250adb608ec3;
#[derive(Clone, Copy)]
#[repr(usize)]
pub enum Event {
    Requested,
    TaskStarted,
    ConnectFirstPoll,
    Connected,
    ControlHelloComplete,
    AdmissionStarted,
    RouteAccepted,
    Admitted,
    Failed,
    TimedOut,
    Cancelled,
    Cleaned,
}

#[repr(C)]
struct Record([AtomicU64; 32]);
impl Record {
    fn mark(&self, event: Event, now: u64) {
        let stage = event as usize;
        let has = |i: usize| self.0[i].load(Ordering::Relaxed) != 0;
        let terminal = (8..11).any(has);
        let permitted = match stage {
            0 => !has(0),
            1..=7 => has(stage - 1) && !terminal,
            8..=10 => has(0) && !terminal && !has(11),
            11 => has(7) || terminal,
            _ => false,
        };
        let reversed = self.0[..12].iter().any(|v| v.load(Ordering::Relaxed) > now);
        if now == 0
            || reversed
            || !permitted
            || self.0[stage]
                .compare_exchange(0, now, Ordering::Relaxed, Ordering::Relaxed)
                .is_err()
        {
            self.0[12].store(1, Ordering::Relaxed);
        }
    }
}

#[cfg(windows)]
#[link(name = "kernel32")]
unsafe extern "system" {
    fn OpenFileMappingW(access: u32, inherit: i32, name: *const u16) -> *mut std::ffi::c_void;
    fn MapViewOfFile(
        handle: *mut std::ffi::c_void,
        access: u32,
        high: u32,
        low: u32,
        bytes: usize,
    ) -> *mut std::ffi::c_void;
    fn UnmapViewOfFile(base: *const std::ffi::c_void) -> i32;
    fn CloseHandle(handle: *mut std::ffi::c_void) -> i32;
    fn QueryPerformanceCounter(value: *mut i64) -> i32;
}

fn qpc() -> u64 {
    #[cfg(windows)]
    {
        let mut value = 0_i64;
        // SAFETY: OS writes one live i64; no transport pointers involved.
        if unsafe { QueryPerformanceCounter(&mut value) } != 0 {
            return value as u64;
        }
    }
    0
}

pub struct Region {
    base: usize,
    handle: usize,
    count: usize,
}
impl Region {
    pub fn open(count: usize, role: u64) -> Option<Arc<Self>> {
        if !cfg!(feature = "benchmark-harness") || !(1..=1024).contains(&count) {
            return None;
        }
        let name = std::env::var("NBSR_BENCH_TIMELINE").ok()?;
        if name.is_empty() {
            return None;
        }
        #[cfg(windows)]
        {
            let name: Vec<u16> = name.encode_utf16().chain(Some(0)).collect();
            // SAFETY: terminated name; mapping is parent-owned and sized before child launch.
            let handle = unsafe { OpenFileMappingW(2, 0, name.as_ptr()) };
            if handle.is_null() {
                return None;
            }
            // SAFETY: Windows validates the requested fixed mapping extent.
            let base = unsafe { MapViewOfFile(handle, 2, 0, 0, 64 + count * 256) };
            if base.is_null() {
                unsafe {
                    CloseHandle(handle);
                }
                return None;
            }
            let region = Arc::new(Self {
                base: base as usize,
                handle: handle as usize,
                count,
            });
            if region.word(0).load(Ordering::Relaxed) != MAGIC
                || region.word(1).load(Ordering::Relaxed) != 1
                || region.word(2).load(Ordering::Relaxed) != count as u64
                || region.word(3).load(Ordering::Relaxed) != role
                || region.word(7).load(Ordering::Relaxed) != GUARD
            {
                return None;
            }
            Some(region)
        }
        #[cfg(not(windows))]
        {
            let _ = (name, role);
            None
        }
    }
    fn word(&self, index: usize) -> &AtomicU64 {
        assert!(index < 8 + self.count * 32);
        // SAFETY: view is page aligned, sized at open, and retained by self.
        unsafe { &*((self.base as *const AtomicU64).add(index)) }
    }
    fn record(&self, index: usize) -> &Record {
        assert!(index < self.count);
        // SAFETY: checked slot, 256-byte C-layout record, aligned atomic fields.
        unsafe { &*((self.base + 64 + index * 256) as *const Record) }
    }
    pub fn claim(self: &Arc<Self>, index: usize) -> Option<Slot> {
        if index >= self.count {
            self.word(5).store(1, Ordering::Relaxed);
            return None;
        }
        if self.record(index).0[13]
            .compare_exchange(0, 1, Ordering::Relaxed, Ordering::Relaxed)
            .is_err()
        {
            self.word(5).store(1, Ordering::Relaxed);
            return None;
        }
        let slot = Slot {
            region: self.clone(),
            index,
        };
        slot.mark(Event::Requested);
        Some(slot)
    }
}
impl Drop for Region {
    fn drop(&mut self) {
        #[cfg(windows)]
        unsafe {
            // SAFETY: this object owns exactly this view/handle; Arc keeps all slots alive.
            UnmapViewOfFile(self.base as *const std::ffi::c_void);
            CloseHandle(self.handle as *mut std::ffi::c_void);
        }
    }
}

#[derive(Clone)]
pub struct Slot {
    region: Arc<Region>,
    index: usize,
}
impl Slot {
    pub fn mark(&self, event: Event) {
        self.region.record(self.index).mark(event, qpc());
    }
    pub fn complete(&self) {
        self.region.record(self.index).0[20].store(1, Ordering::Relaxed);
    }
    fn poll(&self, start: u64, end: u64) {
        let r = self.region.record(self.index);
        if end < start
            || r.0[14]
                .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| v.checked_add(1))
                .is_err()
        {
            r.0[12].store(1, Ordering::Relaxed);
        }
        r.0[15].fetch_max(end.saturating_sub(start), Ordering::Relaxed);
        r.0[16].store(end, Ordering::Relaxed);
        if r.0[18]
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| {
                v.checked_add(end.saturating_sub(start))
            })
            .is_err()
        {
            r.0[12].store(1, Ordering::Relaxed);
        }
    }
}
tokio::task_local! { static CURRENT: Option<Slot>; }
pub async fn scope<F: Future>(slot: Option<Slot>, future: F) -> F::Output {
    if slot.is_some() {
        CURRENT.scope(slot, future).await
    } else {
        future.await
    }
}
pub fn mark(event: Event) {
    let _ = CURRENT.try_with(|s| {
        if let Some(s) = s {
            s.mark(event);
        }
    });
}
pub async fn observe<F: Future>(future: F) -> F::Output {
    let slot = CURRENT.try_with(Clone::clone).ok().flatten();
    let Some(slot) = slot else {
        return future.await;
    };
    let mut future = std::pin::pin!(future);
    let mut first = true;
    std::future::poll_fn(|cx| {
        if first {
            slot.mark(Event::ConnectFirstPoll);
            first = false;
        }
        let start = qpc();
        let result = future.as_mut().poll(cx);
        slot.poll(start, qpc());
        result
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;
    fn record() -> Record {
        Record(std::array::from_fn(|_| AtomicU64::new(0)))
    }
    #[test]
    fn timeline_order_and_duplicate_rejection() {
        let r = record();
        r.mark(Event::Requested, 10);
        r.mark(Event::TaskStarted, 11);
        assert_eq!(r.0[1].load(Ordering::Relaxed), 11);
        r.mark(Event::TaskStarted, 12);
        assert_ne!(r.0[12].load(Ordering::Relaxed), 0);
        assert_eq!(r.0[1].load(Ordering::Relaxed), 11);
    }
    #[test]
    fn timeline_cannot_skip_connected_or_cross_slots() {
        let a = record();
        let b = record();
        a.mark(Event::Admitted, 10);
        assert_ne!(a.0[12].load(Ordering::Relaxed), 0);
        assert_eq!(b.0[12].load(Ordering::Relaxed), 0);
        assert_eq!(std::mem::size_of::<Record>(), 256);
    }
    #[test]
    fn timeline_timeout_is_retained() {
        let r = record();
        r.mark(Event::Requested, 10);
        r.mark(Event::TaskStarted, 11);
        r.mark(Event::TimedOut, 12);
        r.mark(Event::Cleaned, 13);
        assert_eq!(r.0[9].load(Ordering::Relaxed), 12);
        assert_eq!(r.0[12].load(Ordering::Relaxed), 0);
    }
    #[test]
    fn timeline_rejects_clock_reversal() {
        let r = record();
        r.mark(Event::Requested, 10);
        r.mark(Event::TaskStarted, 9);
        assert_eq!(r.0[12].load(Ordering::Relaxed), 1);
    }
}
