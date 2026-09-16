//! THROWAWAY local regular-file notification experiment; not integrated.
#[path = "gate.rs"]
mod gate;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};
use tokio::task::JoinHandle;

struct Request {
    path: PathBuf,
    ready: oneshot::Sender<()>,
}

#[derive(Clone)]
pub(crate) struct MarkerWaiter(mpsc::UnboundedSender<Request>);

tokio::task_local! {
    static WAITER: MarkerWaiter;
}

pub(crate) async fn scope<F: Future>(waiter: Option<MarkerWaiter>, future: F) -> F::Output {
    match waiter {
        Some(waiter) => WAITER.scope(waiter, future).await,
        None => future.await,
    }
}

pub(crate) async fn wait_if_scoped(
    path: &Path,
    timeout: Duration,
) -> Option<Result<(), &'static str>> {
    let waiter = WAITER.try_with(Clone::clone).ok()?;
    Some(waiter.wait(path, timeout).await)
}

/// One scanner per lifecycle runtime, with explicit joining on normal shutdown.
/// The owner aborts it on unwind; cloned wait handles never own its lifetime.
pub(crate) struct MarkerMonitor {
    waiter: MarkerWaiter,
    task: Option<JoinHandle<()>>,
}

impl MarkerMonitor {
    pub(crate) fn new() -> Self {
        let (sender, receiver) = mpsc::unbounded_channel();
        Self {
            waiter: MarkerWaiter(sender),
            task: Some(tokio::spawn(scan(receiver))),
        }
    }

    pub(crate) fn waiter(&self) -> MarkerWaiter {
        self.waiter.clone()
    }

    pub(crate) async fn shutdown(mut self) {
        if let Some(task) = self.task.take() {
            task.abort();
            let result = task.await;
            assert!(result.is_ok() || result.is_err_and(|error| error.is_cancelled()));
        }
    }
}

impl Drop for MarkerMonitor {
    fn drop(&mut self) {
        if let Some(task) = &self.task {
            task.abort();
        }
    }
}

impl MarkerWaiter {
    pub(crate) async fn wait(&self, path: &Path, timeout: Duration) -> Result<(), &'static str> {
        let deadline = tokio::time::Instant::now() + timeout;
        if path.is_file() {
            return Ok(());
        }
        let (ready, receiver) = oneshot::channel();
        self.0
            .send(Request {
                path: path.to_owned(),
                ready,
            })
            .map_err(|_| "marker monitor stopped")?;
        match tokio::time::timeout_at(deadline, receiver).await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(_)) => Err("marker monitor stopped"),
            // Preserve file-before-timeout precedence from the original waiter.
            Err(_) if path.is_file() => Ok(()),
            Err(_) => Err("marker timeout"),
        }
    }
}

fn poll_pending(pending: &mut Vec<Request>) {
    poll_selected(pending, None);
}
fn poll_selected(pending: &mut Vec<Request>, changed: Option<&std::collections::HashSet<PathBuf>>) -> usize {
    let mut index=0;
    let mut checked=0;
    while index<pending.len() {
        if pending[index].ready.is_closed() { pending.swap_remove(index); continue; }
        if changed.is_none_or(|paths|paths.contains(&pending[index].path)) {
            checked+=1;
            if pending[index].path.is_file() {
                let request=pending.swap_remove(index);
                let _=request.ready.send(());
                continue;
            }
        }
        index+=1;
    }
    checked
}

async fn scan(mut receiver: mpsc::UnboundedReceiver<Request>) {
    let mut pending = Vec::new();
    let mut gate: Option<gate::Gate> = None;
    let mut initialized = false;
    loop {
        let mut added = false;
        if pending.is_empty() {
            match receiver.recv().await {
                Some(request) => { pending.push(request); added = true; },
                None => return,
            }
        }
        while let Ok(request) = receiver.try_recv() {
            pending.push(request);
            added = true;
        }
        if !initialized {
            gate = pending.first().and_then(|r|r.path.parent()).and_then(|p|gate::Gate::new(p).ok());
            initialized = true;
        }
        // Prototype contract: one fixed native directory, regular marker paths.
        // Watch is installed before first registration scan.
        let changed = gate.as_mut().and_then(|g|g.changes());
        if added { poll_pending(&mut pending); }
        else { poll_selected(&mut pending, changed.as_ref()); }
        if !pending.is_empty() {
            // Same polling interval as the per-client implementation. Sharing
            // this timer avoids waking every absent-marker waiter each tick.
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_changed_paths_are_statted_and_cancellation_is_still_removed() {
        let (a, mut a_rx)=oneshot::channel();
        let (b, mut b_rx)=oneshot::channel();
        let (cancelled, cancelled_rx)=oneshot::channel();
        drop(cancelled_rx);
        let mut pending=vec![Request {path:PathBuf::from("missing-a"),ready:a},
                             Request {path:PathBuf::from("missing-b"),ready:b},
                             Request {path:PathBuf::from("cancelled"),ready:cancelled}];
        let names=std::collections::HashSet::from([PathBuf::from("missing-a")]);
        assert_eq!(poll_selected(&mut pending,Some(&names)),1);
        assert_eq!(pending.len(),2);
        assert!(a_rx.try_recv().is_err()); assert!(b_rx.try_recv().is_err());
        assert_eq!(poll_selected(&mut pending,None),2);
    }

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let serial = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let root = std::env::temp_dir().join(format!(
                "nbsr-marker-monitor-{}-{serial}",
                std::process::id()
            ));
            std::fs::create_dir(&root).unwrap();
            Self(root)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[tokio::test(flavor = "current_thread")]
    async fn published_marker_releases_only_its_waiter() {
        let root = Fixture::new();
        let first = root.0.join("connection-1.start");
        let second = root.0.join("connection-2.start");
        let monitor = MarkerMonitor::new();
        let waiter = monitor.waiter();
        let (first_result, second_result, ()) = tokio::join!(
            waiter.wait(&first, Duration::from_millis(100)),
            waiter.wait(&second, Duration::from_millis(40)),
            async {
                tokio::time::sleep(Duration::from_millis(1)).await;
                std::fs::write(&first, b"start\n").unwrap();
            },
        );
        assert_eq!(
            first_result,
            Ok(()),
            "the matching file must release a waiting client"
        );
        assert_eq!(
            second_result,
            Err("marker timeout"),
            "an unrelated marker must never release this client"
        );
        monitor.shutdown().await;
    }

    #[tokio::test(flavor = "current_thread")]
    async fn existing_file_wins_even_with_zero_timeout_but_directory_does_not() {
        let root = Fixture::new();
        let marker = root.0.join("release");
        std::fs::write(&marker, b"release\n").unwrap();
        let monitor = MarkerMonitor::new();
        assert_eq!(monitor.waiter().wait(&marker, Duration::ZERO).await, Ok(()));
        assert_eq!(
            monitor.waiter().wait(&root.0, Duration::ZERO).await,
            Err("marker timeout")
        );
        monitor.shutdown().await;
    }

    #[tokio::test(flavor = "current_thread")]
    async fn shutdown_closes_pending_and_future_waits_without_success() {
        let root = Fixture::new();
        let marker = root.0.join("missing");
        let monitor = MarkerMonitor::new();
        let waiter = monitor.waiter();
        let (result, ()) = tokio::join!(waiter.wait(&marker, Duration::from_secs(1)), async {
            tokio::task::yield_now().await;
            monitor.shutdown().await;
        },);
        assert_eq!(result, Err("marker monitor stopped"));
        assert_eq!(
            waiter.wait(&marker, Duration::from_secs(1)).await,
            Err("marker monitor stopped")
        );
    }

    #[test]
    fn cancelled_requests_are_removed_on_next_scan() {
        let mut pending = Vec::new();
        for _ in 0..2048 {
            let (ready, receiver) = oneshot::channel();
            drop(receiver);
            pending.push(Request {
                path: PathBuf::from("absent-marker"),
                ready,
            });
        }
        poll_pending(&mut pending);
        assert!(
            pending.is_empty(),
            "cancelled clients must not accumulate in the scanner"
        );
    }

}
