//! Synthetic asynchronous close confirmation; no worker, transport or deadline policy.
#![cfg(test)]
use crate::{codec::Result, owner::Owner};
use std::sync::{Arc, Mutex};
use tokio::sync::Notify;

struct Completion {
    result: Mutex<Option<Result<()>>>,
    notify: Notify,
}

// Private attempt identity is retained by the exact connection. A callback
// records only a result; the serialized gateway validates ownership and releases.
#[derive(Clone)]
pub struct CleanupTicket {
    pub(crate) connection: u64,
    pub(crate) session: [u8; 16],
    pub(crate) owner: Option<Owner>,
    state: Arc<Completion>,
}

impl CleanupTicket {
    pub(crate) fn new(connection: u64, session: [u8; 16], owner: Option<Owner>) -> Self {
        Self {
            connection,
            session,
            owner,
            state: Arc::new(Completion {
                result: Mutex::new(None),
                notify: Notify::new(),
            }),
        }
    }
    pub(crate) fn same_attempt(&self, other: &Self) -> bool {
        Arc::ptr_eq(&self.state, &other.state)
    }
    pub(crate) fn outcome(&self) -> Option<Result<()>> {
        *self.state.result.lock().unwrap_or_else(|e| e.into_inner())
    }
    // Explicit fixture callback, not an authenticated receipt producer. The
    // first result wins; stale tickets can never mutate gateway state.
    pub fn complete(&self, result: Result<()>) {
        let mut current = self.state.result.lock().unwrap_or_else(|e| e.into_inner());
        if current.is_some() {
            return;
        }
        *current = Some(result);
        drop(current);
        self.state.notify.notify_waiters();
    }
    // Dropping this future removes only its notification wait. The connection
    // retains the ticket and quota until explicit successful finish_cleanup.
    pub async fn wait(&self) -> Result<()> {
        let notified = self.state.notify.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        if let Some(result) = self.outcome() {
            return result;
        }
        notified.await;
        self.outcome()
            .ok_or("cleanup notification without result")?
    }
}
