use std::fmt;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle, ThreadId};
use std::time::Duration;

use tokio::sync::{Notify, mpsc, oneshot};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum TerminalKind {
    Completed,
    Failed,
    TimedOut,
    Cancelled,
}

impl TerminalKind {
    #[allow(dead_code)] // Destination coordination intentionally has no evidence writer.
    fn evidence(self) -> (&'static str, &'static [u8]) {
        match self {
            Self::Completed => ("ack", b"complete\n"),
            Self::Failed => ("failed", b"failed\n"),
            Self::TimedOut => ("failed", b"timed_out\n"),
            Self::Cancelled => ("failed", b"cancelled\n"),
        }
    }
}

#[derive(Debug, Eq, PartialEq)]
pub(crate) enum RecordError {
    Duplicate(usize),
    Unknown(usize),
    WriterClosed,
}

impl fmt::Display for RecordError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{self:?}")
    }
}

#[derive(Debug)]
pub(crate) enum FinishError {
    MissingTerminals,
    WriterDeadline,
    WriterPanicked,
    Evidence(Vec<String>),
}

impl std::fmt::Display for FinishError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingTerminals => formatter.write_str("not all clients reached terminal state"),
            Self::WriterDeadline => formatter.write_str("evidence writer exceeded its deadline"),
            Self::WriterPanicked => formatter.write_str("evidence writer panicked"),
            Self::Evidence(errors) => write!(
                formatter,
                "evidence validation failed: {}",
                errors.join("; ")
            ),
        }
    }
}

impl std::error::Error for FinishError {}

#[derive(Debug)]
pub(crate) struct WriterSummary {
    pub(crate) recorded: usize,
    pub(crate) written: usize,
    pub(crate) writer_thread: Option<ThreadId>,
}

#[derive(Debug)]
struct State {
    terminals: Vec<Option<TerminalKind>>,
    writer_closed: bool,
}

#[derive(Clone)]
pub(crate) struct CompletionSender {
    state: Arc<Mutex<State>>,
    notify: Arc<Notify>,
    evidence: Option<mpsc::Sender<(usize, TerminalKind)>>,
}

impl CompletionSender {
    pub(crate) async fn record(
        &self,
        client_id: usize,
        terminal: TerminalKind,
    ) -> Result<(), RecordError> {
        {
            let mut state = self.state.lock().unwrap();
            let Some(slot) = state.terminals.get_mut(client_id) else {
                return Err(RecordError::Unknown(client_id));
            };
            if slot.is_some() {
                return Err(RecordError::Duplicate(client_id));
            }
            *slot = Some(terminal);
        }
        let evidence_result = if let Some(evidence) = &self.evidence {
            evidence
                .send((client_id, terminal))
                .await
                .map_err(|_| RecordError::WriterClosed)
        } else {
            Ok(())
        };
        if evidence_result.is_err() {
            self.state.lock().unwrap().writer_closed = true;
        }
        self.notify.notify_waiters();
        evidence_result
    }
}

pub(crate) struct CompletionCoordinator {
    state: Arc<Mutex<State>>,
    notify: Arc<Notify>,
    writer: Option<WriterHandle>,
}

struct WriterHandle {
    thread: JoinHandle<()>,
    completion: oneshot::Receiver<WriterResult>,
}

#[derive(Debug)]
struct WriterResult {
    written: usize,
    thread: ThreadId,
    errors: Vec<String>,
}

impl CompletionCoordinator {
    fn state(expected: usize) -> (Arc<Mutex<State>>, Arc<Notify>) {
        assert!(expected > 0);
        (
            Arc::new(Mutex::new(State {
                terminals: vec![None; expected],
                writer_closed: false,
            })),
            Arc::new(Notify::new()),
        )
    }

    #[allow(dead_code)] // Source-only constructor; this module is shared by two binaries.
    pub(crate) fn with_evidence(expected: usize, root: PathBuf) -> (Self, CompletionSender) {
        let (state, notify) = Self::state(expected);
        let (evidence, mut receiver) = mpsc::channel::<(usize, TerminalKind)>(expected.max(1));
        let (finished, completion) = oneshot::channel();
        let writer = thread::Builder::new()
            .name("nbsr-lifecycle-evidence".into())
            .spawn(move || {
                let writer_thread = thread::current().id();
                let mut written = 0;
                let mut errors = Vec::new();
                while let Some((client_id, terminal)) = receiver.blocking_recv() {
                    let (extension, contents) = terminal.evidence();
                    let path = root.join(format!("connection-{client_id}.{extension}"));
                    match OpenOptions::new().write(true).create_new(true).open(&path) {
                        Ok(mut file) => match file.write_all(contents) {
                            Ok(()) => written += 1,
                            Err(error) => errors.push(format!("{}: {error}", path.display())),
                        },
                        Err(error) => errors.push(format!("{}: {error}", path.display())),
                    }
                }
                for client_id in 0..expected {
                    let ack = root.join(format!("connection-{client_id}.ack")).is_file();
                    let failed = root
                        .join(format!("connection-{client_id}.failed"))
                        .is_file();
                    if ack == failed {
                        errors.push(format!(
                            "client {client_id} must have exactly one terminal evidence marker"
                        ));
                    }
                }
                let _ = finished.send(WriterResult {
                    written,
                    thread: writer_thread,
                    errors,
                });
            })
            .unwrap();
        (
            Self {
                state: state.clone(),
                notify: notify.clone(),
                writer: Some(WriterHandle {
                    thread: writer,
                    completion,
                }),
            },
            CompletionSender {
                state,
                notify,
                evidence: Some(evidence),
            },
        )
    }

    #[allow(dead_code)] // Destination-only constructor; this module is shared by two binaries.
    pub(crate) fn without_evidence(expected: usize) -> (Self, CompletionSender) {
        let (state, notify) = Self::state(expected);
        (
            Self {
                state: state.clone(),
                notify: notify.clone(),
                writer: None,
            },
            CompletionSender {
                state,
                notify,
                evidence: None,
            },
        )
    }

    pub(crate) async fn wait_all(&self, deadline: Duration) -> Result<(), FinishError> {
        tokio::time::timeout(deadline, async {
            loop {
                let notified = self.notify.notified();
                if self
                    .state
                    .lock()
                    .unwrap()
                    .terminals
                    .iter()
                    .all(Option::is_some)
                {
                    break;
                }
                notified.await;
            }
        })
        .await
        .map_err(|_| FinishError::MissingTerminals)
    }

    pub(crate) async fn finish(mut self, deadline: Duration) -> Result<WriterSummary, FinishError> {
        let expires = tokio::time::Instant::now() + deadline;
        self.wait_all(deadline).await?;
        let recorded = self
            .state
            .lock()
            .unwrap()
            .terminals
            .iter()
            .filter(|terminal| terminal.is_some())
            .count();
        if self.state.lock().unwrap().writer_closed {
            return Err(FinishError::Evidence(vec!["evidence writer closed".into()]));
        }
        let Some(writer) = self.writer.take() else {
            return Ok(WriterSummary {
                recorded,
                written: 0,
                writer_thread: None,
            });
        };
        let result = tokio::time::timeout_at(expires, writer.completion)
            .await
            .map_err(|_| FinishError::WriterDeadline)?
            .map_err(|_| FinishError::WriterPanicked)?;
        // The writer has finished all I/O before sending its result. Never put a
        // potentially blocked join on Tokio's blocking pool: runtime shutdown
        // would then outlive this deadline. On timeout the OS thread is detached
        // and the run is invalid, without delaying network-runtime shutdown.
        tokio::time::timeout_at(expires, async {
            while !writer.thread.is_finished() {
                tokio::task::yield_now().await;
            }
        })
        .await
        .map_err(|_| FinishError::WriterDeadline)?;
        writer
            .thread
            .join()
            .map_err(|_| FinishError::WriterPanicked)?;
        if !result.errors.is_empty() {
            return Err(FinishError::Evidence(result.errors));
        }
        Ok(WriterSummary {
            recorded,
            written: result.written,
            writer_thread: Some(result.thread),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{CompletionCoordinator, FinishError, RecordError, TerminalKind};
    use std::time::Duration;

    fn temporary_root(label: &str) -> std::path::PathBuf {
        let path = std::env::temp_dir().join(format!(
            "nbsr-lifecycle-coordinator-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&path).unwrap();
        path
    }

    #[test]
    fn writer_timeout_does_not_extend_runtime_shutdown_deadline() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let (mut coordinator, sender) = CompletionCoordinator::without_evidence(1);
        let (finished, completion) = tokio::sync::oneshot::channel();
        let thread = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(200));
            let _ = finished.send(super::WriterResult {
                written: 1,
                thread: std::thread::current().id(),
                errors: Vec::new(),
            });
        });
        coordinator.writer = Some(super::WriterHandle { thread, completion });
        let started = std::time::Instant::now();
        runtime.block_on(async {
            sender.record(0, TerminalKind::Completed).await.unwrap();
            drop(sender);
            assert!(matches!(
                coordinator.finish(Duration::from_millis(10)).await,
                Err(FinishError::WriterDeadline)
            ));
        });
        drop(runtime);
        assert!(started.elapsed() < Duration::from_millis(100));
    }

    #[tokio::test]
    async fn every_expected_client_needs_its_own_terminal_state() {
        let root = temporary_root("expected");
        let (coordinator, sender) = CompletionCoordinator::with_evidence(2, root.clone());
        sender.record(0, TerminalKind::Completed).await.unwrap();
        assert!(
            coordinator
                .wait_all(Duration::from_millis(10))
                .await
                .is_err()
        );
        sender.record(1, TerminalKind::Completed).await.unwrap();
        assert!(coordinator.wait_all(Duration::from_secs(1)).await.is_ok());
        drop(sender);
        coordinator.finish(Duration::from_secs(1)).await.unwrap();
        std::fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn duplicate_and_unknown_ids_never_advance_completion() {
        let root = temporary_root("duplicates");
        let (coordinator, sender) = CompletionCoordinator::with_evidence(2, root.clone());
        sender.record(0, TerminalKind::Completed).await.unwrap();
        assert_eq!(
            sender.record(0, TerminalKind::Failed).await,
            Err(RecordError::Duplicate(0))
        );
        assert_eq!(
            sender.record(2, TerminalKind::Completed).await,
            Err(RecordError::Unknown(2))
        );
        assert!(
            coordinator
                .wait_all(Duration::from_millis(10))
                .await
                .is_err()
        );
        sender.record(1, TerminalKind::TimedOut).await.unwrap();
        drop(sender);
        let summary = coordinator.finish(Duration::from_secs(1)).await.unwrap();
        assert_eq!(summary.recorded, 2);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn evidence_writer_creates_exactly_one_terminal_file_per_client() {
        let root = temporary_root("evidence");
        let runtime_thread = std::thread::current().id();
        let (coordinator, sender) = CompletionCoordinator::with_evidence(2, root.clone());
        sender.record(0, TerminalKind::Completed).await.unwrap();
        sender.record(1, TerminalKind::Cancelled).await.unwrap();
        drop(sender);
        let summary = coordinator.finish(Duration::from_secs(1)).await.unwrap();
        assert_ne!(summary.writer_thread, Some(runtime_thread));
        assert!(root.join("connection-0.ack").is_file());
        assert!(root.join("connection-1.failed").is_file());
        assert_eq!(std::fs::read_dir(&root).unwrap().count(), 2);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn cancellation_and_timeout_are_deterministic_terminal_failures() {
        let root = temporary_root("terminal-failures");
        let (coordinator, sender) = CompletionCoordinator::with_evidence(2, root.clone());
        sender.record(0, TerminalKind::Cancelled).await.unwrap();
        sender.record(1, TerminalKind::TimedOut).await.unwrap();
        drop(sender);
        coordinator.finish(Duration::from_secs(1)).await.unwrap();
        assert_eq!(
            std::fs::read(root.join("connection-0.failed")).unwrap(),
            b"cancelled\n"
        );
        assert_eq!(
            std::fs::read(root.join("connection-1.failed")).unwrap(),
            b"timed_out\n"
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn panicked_and_cancelled_tasks_each_record_their_own_failure() {
        let root = temporary_root("task-failures");
        let (coordinator, sender) = CompletionCoordinator::with_evidence(2, root.clone());
        let panicked = tokio::spawn(async { panic!("injected logical client panic") });
        let cancelled = tokio::spawn(std::future::pending::<()>());
        cancelled.abort();
        for (client_id, task) in [(0, panicked), (1, cancelled)] {
            let error = task.await.unwrap_err();
            let terminal = if error.is_cancelled() {
                TerminalKind::Cancelled
            } else {
                TerminalKind::Failed
            };
            sender.record(client_id, terminal).await.unwrap();
        }
        drop(sender);
        let summary = coordinator.finish(Duration::from_secs(1)).await.unwrap();
        assert_eq!(summary.recorded, 2);
        assert_eq!(summary.written, 2);
        assert_eq!(
            std::fs::read(root.join("connection-0.failed")).unwrap(),
            b"failed\n"
        );
        assert_eq!(
            std::fs::read(root.join("connection-1.failed")).unwrap(),
            b"cancelled\n"
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn evidence_failure_invalidates_run_without_changing_terminal_state() {
        let root = temporary_root("evidence-failure");
        std::fs::write(root.join("connection-0.ack"), b"preexisting\n").unwrap();
        let (coordinator, sender) = CompletionCoordinator::with_evidence(1, root.clone());
        sender.record(0, TerminalKind::Completed).await.unwrap();
        assert!(coordinator.wait_all(Duration::from_secs(1)).await.is_ok());
        drop(sender);
        assert!(matches!(
            coordinator.finish(Duration::from_secs(1)).await,
            Err(FinishError::Evidence(_))
        ));
        assert_eq!(
            std::fs::read(root.join("connection-0.ack")).unwrap(),
            b"preexisting\n"
        );
        std::fs::remove_dir_all(root).unwrap();
    }
}
