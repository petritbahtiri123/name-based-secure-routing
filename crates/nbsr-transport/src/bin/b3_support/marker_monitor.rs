//! Runtime-owned benchmark marker waiting; never protocol or admission authority.
use std::collections::HashSet;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};
use tokio::task::JoinHandle;
#[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
#[path = "marker_notifications.rs"]
mod marker_notifications;

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

fn poll_selected(pending: &mut Vec<Request>, selected: Option<&HashSet<PathBuf>>) {
    let mut index = 0;
    while index < pending.len() {
        if pending[index].ready.is_closed() {
            pending.swap_remove(index);
        } else if selected.is_none_or(|paths| paths.contains(&pending[index].path))
            && pending[index].path.is_file()
        {
            let request = pending.swap_remove(index);
            let _ = request.ready.send(());
        } else {
            index += 1;
        }
    }
}

async fn scan(mut receiver: mpsc::UnboundedReceiver<Request>) {
    let mut pending = Vec::new();
    #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
    let mut notifications = marker_notifications::Notifications::default();
    loop {
        let mut added = false;
        if pending.is_empty() {
            match receiver.recv().await {
                Some(request) => {
                    #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
                    notifications.observe(&request.path);
                    pending.push(request);
                    added = true;
                }
                None => return,
            }
        }
        while let Ok(request) = receiver.try_recv() {
            #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
            notifications.observe(&request.path);
            pending.push(request);
            added = true;
        }
        #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
        let changed = notifications.changed();
        #[cfg(not(all(target_os = "linux", feature = "benchmark-harness")))]
        let changed: Option<HashSet<PathBuf>> = None;
        if added {
            poll_pending(&mut pending);
        } else {
            poll_selected(&mut pending, changed.as_ref());
        }
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

    #[tokio::test(flavor = "current_thread")]
    async fn scoped_release_publishes_active_and_still_requires_its_release() {
        let root = Fixture::new();
        let active = root.0.join("active");
        let release = root.0.join("release");
        let monitor = MarkerMonitor::new();
        let result = scope(
            Some(monitor.waiter()),
            super::super::wait_for_lifecycle_release(&active, &release, Duration::from_millis(20)),
        )
        .await;
        assert_eq!(std::fs::read(&active).unwrap(), b"active\n");
        assert_eq!(result, Err("lifecycle release marker timeout"));
        monitor.shutdown().await;
    }

    #[cfg(all(target_os = "linux", feature = "benchmark-harness"))]
    #[tokio::test(flavor = "current_thread")]
    async fn symlink_target_outside_watch_still_releases_waiter() {
        let root = Fixture::new();
        let external = Fixture::new();
        let target = external.0.join("target");
        let link = root.0.join("marker");
        let monitor = MarkerMonitor::new();
        let waiter = monitor.waiter();
        let (result, ()) = tokio::join!(waiter.wait(&link, Duration::from_secs(1)), async {
            tokio::time::sleep(Duration::from_millis(20)).await;
            std::os::unix::fs::symlink(&target, &link).unwrap();
            tokio::time::sleep(Duration::from_millis(20)).await;
            std::fs::write(&target, b"ready").unwrap();
        });
        assert_eq!(result, Ok(()));
        monitor.shutdown().await;
    }

    #[tokio::test(flavor = "current_thread")]
    async fn late_registration_and_multiple_directories_preserve_readiness() {
        let first = Fixture::new();
        let second = Fixture::new();
        let monitor = MarkerMonitor::new();
        let waiter = monitor.waiter();
        let a = first.0.join("a");
        let b = second.0.join("b");
        let (a_result, b_result, ()) = tokio::join!(
            waiter.wait(&a, Duration::from_secs(1)),
            async {
                tokio::time::sleep(Duration::from_millis(20)).await;
                waiter.wait(&b, Duration::from_secs(1)).await
            },
            async {
                tokio::time::sleep(Duration::from_millis(40)).await;
                std::fs::write(&a, b"ready").unwrap();
                std::fs::write(&b, b"ready").unwrap();
            }
        );
        assert_eq!(a_result, Ok(()));
        assert_eq!(b_result, Ok(()));
        monitor.shutdown().await;
    }
}
