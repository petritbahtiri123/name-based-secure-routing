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
    pub async fn drive(&mut self) -> Result<(), TransportError> {
        let shared = &self.stream.shared;
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
