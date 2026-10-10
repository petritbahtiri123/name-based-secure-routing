use super::*;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Phase {
    Pending,
    Completed,
    Aborted,
}

pub(super) struct OwnedSendState {
    payload: Box<[u8]>,
    offset: usize,
    reservation: Option<ChannelByteReservation>,
    phase: Phase,
}

impl OwnedSendState {
    pub(super) fn abort(&mut self) {
        self.payload = Box::default();
        self.reservation = None;
        self.phase = Phase::Aborted;
    }
}

/// An immutable owned payload bound exclusively to one application stream.
///
/// Dropping a `drive()` future pauses this operation. Dropping this operation
/// before completion, or calling `abort`, resets its stream. No background task
/// is created. A completed operation's Drop preserves normal FIN behavior.
#[must_use = "drive the operation to completion or explicitly abort it"]
pub struct OwnedSendOperation<'a> {
    stream: &'a mut ApplicationStream,
    state: Arc<Mutex<OwnedSendState>>,
    #[cfg(test)]
    pub(super) completion_hook: Option<Box<dyn FnOnce() + Send>>,
}

impl ApplicationStream {
    /// Takes ownership of one payload without sending any bytes.
    ///
    /// The operation is the non-Clone resume token and exclusively borrows this
    /// stream. It cannot be mixed with echo or other stream operations. Beginning
    /// after any prior application write/owned operation, or during an unfinished
    /// receive, returns `ApplicationStreamFailed`. Admission prefaces are not
    /// application writes. The existing 1 MiB/8 MiB byte limits remain in force.
    pub fn begin_owned_send(
        &mut self,
        payload: Vec<u8>,
    ) -> Result<OwnedSendOperation<'_>, TransportError> {
        if payload.len() > MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM {
            return Err(TransportError::ApplicationPayloadTooLarge);
        }
        if self.shared.cancelled.load(Ordering::Acquire) {
            return Err(TransportError::ApplicationStreamRejected);
        }
        {
            let receive = self
                .shared
                .payload_receive
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            if receive.failed || receive.operation.is_some() {
                return Err(TransportError::ApplicationStreamFailed);
            }
        }
        if self
            .shared
            .application_write_started
            .load(Ordering::Acquire)
        {
            return Err(TransportError::ApplicationStreamFailed);
        }
        let quota = self
            .shared
            .channel_quota
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone();
        let reservation = quota
            .as_ref()
            .map(|quota| quota.reserve(payload.len()))
            .transpose()?;
        self.shared
            .application_write_started
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| TransportError::ApplicationStreamFailed)?;
        let state = Arc::new(Mutex::new(OwnedSendState {
            payload: payload.into_boxed_slice(),
            offset: 0,
            reservation,
            phase: Phase::Pending,
        }));
        *self
            .shared
            .owned_send
            .lock()
            .unwrap_or_else(|e| e.into_inner()) = Arc::downgrade(&state);
        if self.shared.cancelled.load(Ordering::Acquire) {
            self.shared.force_reset();
            return Err(TransportError::ApplicationStreamRejected);
        }
        Ok(OwnedSendOperation {
            stream: self,
            state,
            #[cfg(test)]
            completion_hook: None,
        })
    }
}

impl OwnedSendOperation<'_> {
    /// Drives/resumes this exact payload, retaining offset and quota if this future
    /// is cancelled. Success means transport acceptance plus FIN, not peer ACK or
    /// application processing. Repeated drive after success is idempotent.
    ///
    /// A timeout around drive pauses it; the owner must abort/drop the operation
    /// to enforce an absolute deadline. Pausing does not extend a caller deadline
    /// and retains quota. Broken connections cannot guarantee delivery.
    /// If revoked while a drive is pending, dropping that future completes the
    /// stream's reset/stop after unlocking, even when this operation stays alive.
    /// Dropping a drive without revocation still preserves resumable progress.
    pub async fn drive(&mut self) -> Result<(), TransportError> {
        let shared = &self.stream.shared;
        // Drop after inner unlocks: revocation may have missed its try_lock
        // while this drive was pending. Ordinary cancellation still only pauses.
        let _revocation_cleanup = BorrowedSendCancellation {
            shared,
            armed: false,
        };
        let notified = shared.notify.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        let mut inner = shared.inner.lock().await;
        let mut chunk = [0_u8; 16_384];
        loop {
            let count = {
                let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
                if shared.cancelled.load(Ordering::Acquire) || state.phase == Phase::Aborted {
                    drop(state);
                    shared.force_reset();
                    reset_parts(&mut inner);
                    return Err(TransportError::ApplicationStreamRejected);
                }
                if state.phase == Phase::Completed {
                    return Ok(());
                }
                if state.offset == state.payload.len() {
                    if inner.send.finish().is_err() {
                        drop(state);
                        shared.force_reset();
                        reset_parts(&mut inner);
                        return Err(TransportError::ApplicationStreamFailed);
                    }
                    #[cfg(test)]
                    if let Some(hook) = self.completion_hook.take() {
                        hook();
                    }
                    if let Some(reservation) = state.reservation.take() {
                        shared.outbound_bytes.retain(reservation);
                    }
                    state.payload = Box::default();
                    state.phase = Phase::Completed;
                    drop(state);
                    if shared.cancelled.load(Ordering::Acquire) {
                        shared.force_reset();
                        reset_parts(&mut inner);
                        return Err(TransportError::ApplicationStreamRejected);
                    }
                    return Ok(());
                }
                let count = chunk.len().min(state.payload.len() - state.offset);
                chunk[..count].copy_from_slice(&state.payload[state.offset..state.offset + count]);
                count
            };
            let written = tokio::select! {
                _ = &mut notified => {
                    shared.force_reset();
                    reset_parts(&mut inner);
                    return Err(TransportError::ApplicationStreamRejected);
                }
                result = inner.send.write(&chunk[..count]) => result,
            };
            match written {
                Ok(written) if written != 0 => {
                    // No await between accepted progress and its retained offset.
                    let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
                    if state.phase == Phase::Pending {
                        state.offset += written;
                    }
                }
                _ => {
                    shared.force_reset();
                    reset_parts(&mut inner);
                    return Err(TransportError::ApplicationStreamFailed);
                }
            }
        }
    }

    /// Aborts an unfinished operation. It cannot undo a completed send or bytes
    /// already observed by the peer. Completed operations retain normal FIN.
    pub fn abort(self) {
        // Drop applies the same terminal ownership rule.
    }
}

impl Drop for OwnedSendOperation<'_> {
    fn drop(&mut self) {
        let unfinished =
            self.state.lock().unwrap_or_else(|e| e.into_inner()).phase != Phase::Completed;
        if unfinished {
            self.stream.shared.force_reset();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    async fn revoked_drive_drop_resets_while_owner_is_retained(zero_progress: bool) {
        let (listener, source, destination) =
            super::super::control_read_tests::connection_pair_with_window(Some(64)).await;
        let (mut send, receive) = source.connection.open_bi().await.unwrap();
        if zero_progress {
            // Fill the 64-byte window before wrapping the stream. The peer must
            // not read these fixture bytes until after the drive is dropped.
            send.write_all(&[0xaa; 64]).await.unwrap();
        }
        let mut application = application_stream(send, receive);
        let shared = Arc::clone(&application.shared);
        let quota = Arc::new(ChannelByteQuota::default());
        *shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
        let mut operation = application.begin_owned_send(vec![0x5a; 4096]).unwrap();
        let state = Arc::clone(&operation.state);
        let mut driving = Box::pin(operation.drive());
        let pending = std::future::poll_fn(|cx| {
            std::task::Poll::Ready(std::future::Future::poll(driving.as_mut(), cx).is_pending())
        })
        .await;
        let (peer_send, mut peer_receive) =
            timeout(Duration::from_secs(2), destination.connection.accept_bi())
                .await
                .unwrap()
                .unwrap();
        let offset = state.lock().unwrap().offset;
        let held_lock = shared.inner.try_lock().is_err();
        shared.force_reset();
        let cleared_before_drop = {
            let state = state.lock().unwrap();
            state.phase == Phase::Aborted && state.payload.is_empty() && state.reservation.is_none()
        };
        drop(driving); // Never repoll the revocation notification.
        let unlocked = shared.inner.try_lock().is_ok();
        let quota_after_drop = *quota.buffered.lock().unwrap();
        // Crucially, operation/application/connections remain alive. No follow-up
        // drive or owner Drop may provide the RESET/STOP being tested here.
        let (outcome, stopped) = tokio::join!(
            timeout(Duration::from_secs(2), async {
                let mut bytes = [0; 128];
                loop {
                    match peer_receive.read(&mut bytes).await {
                        Ok(Some(_)) => continue,
                        result => break result,
                    }
                }
            }),
            timeout(Duration::from_secs(2), peer_send.stopped())
        );
        // Exercise a sibling after the observed terminal outcome; doing so
        // earlier would consume this fixture's 64-byte connection window.
        let mut sibling = source.open_application_stream().await.unwrap();
        sibling.send_payload(b"sibling").await.unwrap();
        let (sibling_send, mut sibling_receive) =
            timeout(Duration::from_secs(2), destination.connection.accept_bi())
                .await
                .unwrap()
                .unwrap();
        let sibling_outcome =
            timeout(Duration::from_secs(2), sibling_receive.read_to_end(64)).await;
        // Repeated terminal actions must not resume payload or restore quota.
        let retry = if pending {
            Some(operation.drive().await)
        } else {
            None
        };
        shared.force_reset();
        drop(operation);
        let final_quota = *quota.buffered.lock().unwrap();
        let weak_state = Arc::downgrade(&state);
        drop(state);
        let state_released = weak_state.upgrade().is_none();
        drop(application);
        drop(shared);
        drop(sibling);
        drop(peer_send);
        drop(peer_receive);
        drop(sibling_send);
        drop(sibling_receive);
        timeout(Duration::from_secs(8), async {
            let (a, b) = tokio::join!(source.close(), destination.close());
            let c = listener.close().await;
            a.unwrap();
            b.unwrap();
            c.unwrap();
        })
        .await
        .unwrap();
        assert!(
            pending && held_lock && unlocked,
            "deterministic blocked-drive checkpoint"
        );
        assert!(
            if zero_progress {
                offset == 0
            } else {
                offset > 0 && offset < 4096
            },
            "unexpected accepted payload offset: {offset}"
        );
        assert!(
            cleared_before_drop && state_released,
            "payload ownership must be released"
        );
        assert_eq!((quota_after_drop, final_quota), (0, 0));
        assert!(
            matches!(outcome, Ok(Err(quinn::ReadError::Reset(code))) if code == VarInt::from_u32(1)),
            "revoked drive Drop must reset before owner Drop or repoll: {outcome:?}"
        );
        assert!(
            matches!(stopped, Ok(Ok(Some(code))) if code == VarInt::from_u32(1)),
            "revoked drive Drop must stop peer send: {stopped:?}"
        );
        assert_eq!(sibling_outcome.unwrap().unwrap(), b"sibling");
        assert_eq!(retry, Some(Err(TransportError::ApplicationStreamRejected)));
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn revoked_owned_drive_drop_resets_zero_progress_with_owner_retained() {
        revoked_drive_drop_resets_while_owner_is_retained(true).await;
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn revoked_owned_drive_drop_resets_partial_progress_with_owner_retained() {
        revoked_drive_drop_resets_while_owner_is_retained(false).await;
    }
}
