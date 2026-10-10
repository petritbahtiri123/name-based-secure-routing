use super::*;
use crate::session_tests::support;
use crate::{EdgeIdentity, EdgeRole, PeerPolicy, build_client_config, build_server_config};
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Duration;
fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).unwrap()
}

async fn connection_pair() -> (
    TransportListener,
    AuthenticatedConnection,
    AuthenticatedConnection,
) {
    connection_pair_with_window(None).await
}

pub(super) async fn connection_pair_with_window(
    window: Option<u32>,
) -> (
    TransportListener,
    AuthenticatedConnection,
    AuthenticatedConnection,
) {
    let pki = support::TestPki::generate();
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination-edge.test"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy");
    let mut server =
        build_server_config(destination_policy, pki.destination_material()).expect("server config");
    let mut client =
        build_client_config(source_policy, pki.source_material()).expect("client config");
    if let Some(window) = window {
        Arc::get_mut(&mut server.quinn.transport)
            .expect("fresh test transport")
            .stream_receive_window(VarInt::from_u32(window))
            .receive_window(VarInt::from_u32(window));
        let mut transport = quinn::TransportConfig::default();
        transport.send_window(u64::from(window));
        transport.max_idle_timeout(Some(Duration::from_secs(5).try_into().unwrap()));
        client.quinn.transport_config(Arc::new(transport));
    }
    let listener =
        TransportListener::bind(server, SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0))
            .expect("listener");
    let remote = listener.local_addr().expect("address");
    let (destination, source) = tokio::join!(listener.accept_one(), connect(client, remote));
    let destination = destination.expect("destination connection");
    let source = source.expect("source connection");
    (listener, source, destination)
}

// Drive and cancel only receive futures until the exact byte checkpoint is
// observed. Yielding handles delayed delivery without sleeps or a first-poll race.
async fn cancel_at_progress(
    receiver: &mut ControlStream,
    envelope: bool,
    prefix: usize,
    body: usize,
) -> bool {
    timeout(Duration::from_secs(2), async {
        loop {
            let pending = if envelope {
                let mut read = Box::pin(receiver.receive_envelope(crate::CoreV02Limits::default()));
                std::future::poll_fn(|cx| {
                    std::task::Poll::Ready(
                        std::future::Future::poll(read.as_mut(), cx).is_pending(),
                    )
                })
                .await
            } else {
                let mut read = Box::pin(receiver.receive_stream_credit_refill_request());
                std::future::poll_fn(|cx| {
                    std::task::Poll::Ready(
                        std::future::Future::poll(read.as_mut(), cx).is_pending(),
                    )
                })
                .await
            };
            if !pending {
                return false;
            }
            if receiver.receive_prefix.len() == prefix && receiver.receive_body_read == body {
                return true;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("bounded partial-consumption checkpoint")
}

async fn refill_case(body_bytes: usize) {
    let (listener, source, destination) = connection_pair().await;
    let mut sender = source.open_control_stream().await.unwrap();
    let refill = StreamCreditRefill {
        channel_id: [0x40; 16],
        epoch: 2,
    };
    let wire = encode_stream_credit_refill_control(STREAM_CREDIT_REFILL_REQUEST, refill).unwrap();
    // Only this partial frame announces stream 0; acceptance synchronizes delivery.
    // No remaining body bytes are sent until the pending read is cancelled.
    let mut initial = vec![30];
    initial.extend_from_slice(&wire[..body_bytes]);
    sender.send.write_all(&initial).await.unwrap();
    let mut receiver = timeout(Duration::from_secs(2), destination.accept_control_stream())
        .await
        .unwrap()
        .unwrap();
    let was_pending = cancel_at_progress(&mut receiver, false, 1, body_bytes).await;
    let consumed_partial =
        receiver.receive_prefix == [30] && receiver.receive_body_read == body_bytes;
    // A mismatched operation must neither consume bytes nor destroy resumability.
    let mut wrong = Box::pin(receiver.receive_stream_credit_refill_grant());
    let mismatch_rejected = std::future::poll_fn(|cx| {
        std::task::Poll::Ready(matches!(
            std::future::Future::poll(wrong.as_mut(), cx),
            std::task::Poll::Ready(Err(TransportError::ControlStreamFailed))
        ))
    })
    .await;
    drop(wrong);
    for _ in 0..2 {
        let mut repeat = Box::pin(receiver.receive_stream_credit_refill_request());
        let pending = std::future::poll_fn(|cx| {
            std::task::Poll::Ready(std::future::Future::poll(repeat.as_mut(), cx).is_pending())
        })
        .await;
        drop(repeat);
        assert!(pending);
    }
    sender.send.write_all(&wire[body_bytes..]).await.unwrap();
    let result = timeout(
        Duration::from_secs(2),
        receiver.receive_stream_credit_refill_request(),
    )
    .await;
    sender
        .send_stream_credit_refill_request(refill)
        .await
        .unwrap();
    let next = timeout(
        Duration::from_secs(2),
        receiver.receive_stream_credit_refill_request(),
    )
    .await;
    drop(sender);
    drop(receiver);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded cleanup");
    assert_eq!(next.expect("bounded next frame"), Ok(refill));
    assert!(was_pending);
    assert_eq!(result.expect("bounded receive"), Ok(refill));
    assert!(
        consumed_partial,
        "cancellation must occur after consuming the supplied partial frame"
    );
    assert!(
        mismatch_rejected,
        "changing refill kind must fail without consuming progress"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn partial_refill_body_receive_resumes_after_cancellation() {
    refill_case(0).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn consumed_refill_body_bytes_survive_cancellation() {
    refill_case(3).await;
}

async fn envelope_case(partial_prefix: bool) {
    let (listener, source, destination) = connection_pair().await;
    let fixture = std::fs::read(
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/core-v0.2/artifacts/valid/envelopes/client-hello.cbor"),
    )
    .unwrap();
    let envelope =
        crate::decode_control_envelope(&fixture, crate::CoreV02Limits::default()).unwrap();
    let wire = envelope.encode();
    let prefix = encode_frame_length(wire.len()).unwrap();
    assert!(
        prefix.len() > 1,
        "fixture must exercise a multi-byte prefix"
    );
    let mut frame = prefix.clone();
    frame.extend_from_slice(&wire);
    let split = if partial_prefix { 1 } else { prefix.len() + 3 };
    let mut sender = source.open_control_stream().await.unwrap();
    sender.send.write_all(&frame[..split]).await.unwrap();
    let mut receiver = timeout(Duration::from_secs(2), destination.accept_control_stream())
        .await
        .unwrap()
        .unwrap();
    let was_pending = cancel_at_progress(
        &mut receiver,
        true,
        split.min(prefix.len()),
        split.saturating_sub(prefix.len()),
    )
    .await;
    let consumed_partial = receiver.receive_prefix.len() == split.min(prefix.len())
        && receiver.receive_body_read == split.saturating_sub(prefix.len());
    let mut changed = crate::CoreV02Limits::default();
    changed.max_depth += 1;
    let mut wrong = Box::pin(receiver.receive_envelope(changed));
    let mismatch_rejected = std::future::poll_fn(|cx| {
        std::task::Poll::Ready(matches!(
            std::future::Future::poll(wrong.as_mut(), cx),
            std::task::Poll::Ready(Err(TransportError::ControlStreamFailed))
        ))
    })
    .await;
    drop(wrong);
    sender.send.write_all(&frame[split..]).await.unwrap();
    let resumed = timeout(
        Duration::from_secs(2),
        receiver.receive_envelope(crate::CoreV02Limits::default()),
    )
    .await;
    sender.send_envelope(&envelope).await.unwrap();
    let next = timeout(
        Duration::from_secs(2),
        receiver.receive_envelope(crate::CoreV02Limits::default()),
    )
    .await;
    drop(sender);
    drop(receiver);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded cleanup");
    assert!(was_pending);
    assert!(
        consumed_partial,
        "cancellation must follow consumption of the supplied prefix/body"
    );
    assert!(
        mismatch_rejected,
        "changed limits must fail without consuming progress"
    );
    assert_eq!(
        resumed
            .expect("bounded resumed frame")
            .expect("valid resumed frame")
            .encode(),
        wire
    );
    assert_eq!(
        next.expect("bounded next frame")
            .expect("valid next frame")
            .encode(),
        wire
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn partial_envelope_prefix_survives_cancellation() {
    envelope_case(true).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn partial_envelope_body_survives_cancellation() {
    envelope_case(false).await;
}

#[test]
fn retained_frame_prefix_preserves_canonical_length_validation() {
    for length in [1, 63, 64, 16_383, 16_384, 65_536] {
        assert_eq!(
            decode_frame_length(&encode_frame_length(length).unwrap()),
            Ok(length)
        );
    }
    for prefix in [
        &[0x40, 0x01][..],
        &[0x80, 0, 0, 64][..],
        &[0xc0, 0, 0, 0, 0, 0, 0, 1][..],
    ] {
        assert_eq!(
            decode_frame_length(prefix),
            Err(TransportError::ControlFrameInvalid)
        );
    }
    assert_eq!(
        encode_frame_length(0),
        Err(TransportError::ControlFrameTooLarge)
    );
    assert_eq!(
        encode_frame_length(65_537),
        Err(TransportError::ControlFrameTooLarge)
    );
}

async fn close_pair(
    listener: TransportListener,
    source: AuthenticatedConnection,
    destination: AuthenticatedConnection,
) {
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded cleanup");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cancellation_before_bytes_does_not_lock_receive_operation() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.unwrap();
    source_control.send.write_all(&[30]).await.unwrap();
    let mut destination_control =
        timeout(Duration::from_secs(2), destination.accept_control_stream())
            .await
            .unwrap()
            .unwrap();
    let mut waiting = Box::pin(source_control.receive_envelope(crate::CoreV02Limits::default()));
    let was_pending = std::future::poll_fn(|cx| {
        std::task::Poll::Ready(std::future::Future::poll(waiting.as_mut(), cx).is_pending())
    })
    .await;
    drop(waiting);
    let untouched =
        source_control.receive_prefix.is_empty() && source_control.receive_operation.is_none();
    let refill = StreamCreditRefill {
        channel_id: [0x40; 16],
        epoch: 2,
    };
    destination_control
        .send_stream_credit_refill_grant(refill)
        .await
        .unwrap();
    let received = timeout(
        Duration::from_secs(2),
        source_control.receive_stream_credit_refill_grant(),
    )
    .await;
    drop(source_control);
    drop(destination_control);
    close_pair(listener, source, destination).await;
    assert!(was_pending && untouched);
    assert_eq!(received.unwrap(), Ok(refill));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn partial_prefix_body_eof_and_reset_remain_bounded_errors() {
    for (initial, reset) in [
        (&[0x40][..], false),
        (&[30, 0x4e][..], false),
        (&[30, 0x4e][..], true),
    ] {
        let (listener, source, destination) = connection_pair().await;
        let mut sender = source.open_control_stream().await.unwrap();
        sender.send.write_all(initial).await.unwrap();
        let mut receiver = timeout(Duration::from_secs(2), destination.accept_control_stream())
            .await
            .unwrap()
            .unwrap();
        let was_pending = cancel_at_progress(&mut receiver, false, 1, initial.len() - 1).await;
        let consumed =
            receiver.receive_prefix.len() == 1 && receiver.receive_body_read == initial.len() - 1;
        if reset {
            sender.send.reset(VarInt::from_u32(0)).unwrap();
        } else {
            sender.send.finish().unwrap();
        }
        let first = timeout(
            Duration::from_secs(2),
            receiver.receive_stream_credit_refill_request(),
        )
        .await;
        let second = timeout(
            Duration::from_secs(2),
            receiver.receive_stream_credit_refill_request(),
        )
        .await;
        let bounded = receiver.receive_prefix.len() <= 8 && receiver.receive_body.len() <= 30;
        drop(sender);
        drop(receiver);
        close_pair(listener, source, destination).await;
        assert!(was_pending && consumed && bounded);
        assert_eq!(first.unwrap(), Err(TransportError::ControlStreamFailed));
        assert_eq!(second.unwrap(), Err(TransportError::ControlStreamFailed));
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn complete_invalid_body_clears_framing_but_invalid_prefix_does_not() {
    let (listener, source, destination) = connection_pair().await;
    let mut sender = source.open_control_stream().await.unwrap();
    let mut invalid_body = vec![30];
    invalid_body.extend_from_slice(&[0; 30]);
    sender.send.write_all(&invalid_body).await.unwrap();
    let mut receiver = timeout(Duration::from_secs(2), destination.accept_control_stream())
        .await
        .unwrap()
        .unwrap();
    let invalid = timeout(
        Duration::from_secs(2),
        receiver.receive_stream_credit_refill_request(),
    )
    .await;
    let cleared = receiver.receive_operation.is_none()
        && receiver.receive_prefix.is_empty()
        && receiver.receive_body.is_empty();
    let refill = StreamCreditRefill {
        channel_id: [0x40; 16],
        epoch: 2,
    };
    sender
        .send_stream_credit_refill_request(refill)
        .await
        .unwrap();
    let valid = timeout(
        Duration::from_secs(2),
        receiver.receive_stream_credit_refill_request(),
    )
    .await;
    sender.send.write_all(&[0x40, 0x01]).await.unwrap();
    let bad_prefix = timeout(
        Duration::from_secs(2),
        receiver.receive_stream_credit_refill_request(),
    )
    .await;
    let retry = timeout(
        Duration::from_secs(2),
        receiver.receive_stream_credit_refill_request(),
    )
    .await;
    let no_body_allocated = receiver.receive_body.is_empty();
    drop(sender);
    drop(receiver);
    close_pair(listener, source, destination).await;
    assert_eq!(invalid.unwrap(), Err(TransportError::ControlFrameInvalid));
    assert!(cleared && no_body_allocated);
    assert_eq!(valid.unwrap(), Ok(refill));
    assert_eq!(
        bad_prefix.unwrap(),
        Err(TransportError::ControlFrameInvalid)
    );
    assert_eq!(retry.unwrap(), Err(TransportError::ControlFrameInvalid));
}

// Raw authenticated streams isolate the receive API from admission.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn application_payload_prefix_survives_caller_cancellation() {
    let (listener, source, destination) = connection_pair().await;
    let (mut sending, source_receive) = source.connection.open_bi().await.unwrap();
    let prefix = b"prefix-";
    let suffix = b"suffix";
    sending.write_all(prefix).await.unwrap();
    let (send, receive) = timeout(Duration::from_secs(2), destination.connection.accept_bi())
        .await
        .unwrap()
        .unwrap();
    let mut application = application_stream(send, receive);
    let quota = Arc::new(ChannelByteQuota::default());
    *application.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let mut pending = Box::pin(application.receive_payload());
    let checkpoint = timeout(
        Duration::from_secs(2),
        std::future::poll_fn(|cx| match std::future::Future::poll(pending.as_mut(), cx) {
            std::task::Poll::Ready(_) => std::task::Poll::Ready(false),
            std::task::Poll::Pending if *quota.buffered.lock().unwrap() == prefix.len() => {
                std::task::Poll::Ready(true)
            }
            std::task::Poll::Pending => std::task::Poll::Pending,
        }),
    )
    .await;
    drop(pending);
    let retained_after_cancel = *quota.buffered.lock().unwrap();
    let result = if matches!(checkpoint, Ok(true)) {
        sending.write_all(suffix).await.unwrap();
        sending.finish().unwrap();
        timeout(Duration::from_secs(2), application.receive_payload()).await
    } else {
        Err(
            tokio::time::timeout(Duration::ZERO, std::future::pending::<()>())
                .await
                .unwrap_err(),
        )
    };
    drop(application);
    drop(sending);
    drop(source_receive);
    let released_after_drop = *quota.buffered.lock().unwrap();
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded reproduction cleanup");
    assert!(
        matches!(checkpoint, Ok(true)),
        "prefix consumption checkpoint: {checkpoint:?}"
    );
    assert_eq!(
        released_after_drop, 0,
        "stream drop releases all reservations"
    );
    assert_eq!(
        result.unwrap().unwrap(),
        [prefix.as_slice(), suffix.as_slice()].concat(),
        "retry must return complete payload; quota after cancellation={retained_after_cancel}"
    );
}

struct PayloadFixture {
    listener: TransportListener,
    source: AuthenticatedConnection,
    destination: AuthenticatedConnection,
    sending: SendStream,
    peer_receive: RecvStream,
    application: ApplicationStream,
    quota: Arc<ChannelByteQuota>,
}

impl PayloadFixture {
    async fn new() -> Self {
        Self::with_window(None).await
    }

    async fn with_window(window: Option<u32>) -> Self {
        let (listener, source, destination) = connection_pair_with_window(window).await;
        let (mut send, receive) = source.connection.open_bi().await.unwrap();
        send.write_all(b"a").await.unwrap();
        let (sending, mut peer_receive) =
            timeout(Duration::from_secs(2), destination.connection.accept_bi())
                .await
                .unwrap()
                .unwrap();
        let mut announcement = [0];
        peer_receive.read_exact(&mut announcement).await.unwrap();
        let application = application_stream(send, receive);
        let quota = Arc::new(ChannelByteQuota::default());
        *application.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
        Self {
            listener,
            source,
            destination,
            sending,
            peer_receive,
            application,
            quota,
        }
    }

    fn buffered(&self) -> usize {
        *self.quota.buffered.lock().unwrap()
    }

    async fn close(self) {
        let Self {
            listener,
            source,
            destination,
            sending,
            peer_receive,
            application,
            quota,
        } = self;
        drop(application);
        drop(sending);
        drop(peer_receive);
        assert_eq!(
            *quota.buffered.lock().unwrap(),
            0,
            "drop releases receive ownership"
        );
        timeout(Duration::from_secs(8), async {
            let (a, b) = tokio::join!(source.close(), destination.close());
            let c = listener.close().await;
            a.unwrap();
            b.unwrap();
            c.unwrap();
        })
        .await
        .expect("bounded payload fixture cleanup");
    }
}

async fn cancel_payload_at(
    application: &mut ApplicationStream,
    quota: &ChannelByteQuota,
    bytes: usize,
    echo: bool,
) {
    let mut pending = Box::pin(async {
        if echo {
            application.echo_once().await
        } else {
            application.receive_payload().await
        }
    });
    let checkpoint = timeout(
        Duration::from_secs(2),
        std::future::poll_fn(|cx| match std::future::Future::poll(pending.as_mut(), cx) {
            std::task::Poll::Ready(result) => panic!("receive unexpectedly completed: {result:?}"),
            std::task::Poll::Pending if *quota.buffered.lock().unwrap() == bytes => {
                std::task::Poll::Ready(())
            }
            std::task::Poll::Pending => std::task::Poll::Pending,
        }),
    )
    .await;
    drop(pending);
    checkpoint.expect("exact bounded payload progress checkpoint");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_repeated_cancellation_preserves_quota_and_rejects_operation_mismatch() {
    for echo in [false, true] {
        let mut f = PayloadFixture::new().await;
        f.sending.write_all(b"prefix-").await.unwrap();
        cancel_payload_at(&mut f.application, &f.quota, 7, echo).await;
        f.application.release_buffered_payloads();
        assert_eq!(f.buffered(), 7, "handoff cannot release incomplete bytes");
        let mismatch = if echo {
            f.application.receive_payload().await
        } else {
            f.application.echo_once().await
        };
        assert_eq!(mismatch, Err(TransportError::ApplicationStreamFailed));
        assert_eq!(f.buffered(), 7);
        #[cfg(feature = "benchmark-harness")]
        assert_eq!(
            f.application.benchmark_read_frame().await,
            Err(TransportError::ApplicationStreamFailed)
        );
        f.sending.write_all(b"middle-").await.unwrap();
        cancel_payload_at(&mut f.application, &f.quota, 14, echo).await;
        cancel_payload_at(&mut f.application, &f.quota, 14, echo).await;
        f.sending.write_all(b"suffix").await.unwrap();
        f.sending.finish().unwrap();
        let result = timeout(Duration::from_secs(2), async {
            if echo {
                f.application.echo_once().await
            } else {
                f.application.receive_payload().await
            }
        })
        .await
        .unwrap()
        .unwrap();
        assert_eq!(result, b"prefix-middle-suffix");
        assert_eq!(f.buffered(), result.len() * if echo { 2 } else { 1 });
        if echo {
            let echoed = timeout(Duration::from_secs(2), f.peer_receive.read_to_end(64))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(echoed, result);
        }
        f.application.release_buffered_payloads();
        assert_eq!(f.buffered(), 0);
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_before_bytes_cancellation_allows_switch_and_empty_fin() {
    for echo in [false, true] {
        let mut f = PayloadFixture::new().await;
        cancel_payload_at(&mut f.application, &f.quota, 0, echo).await;
        assert!(
            f.application
                .shared
                .payload_receive
                .lock()
                .unwrap()
                .operation
                .is_none()
        );
        f.sending.finish().unwrap();
        let result = timeout(Duration::from_secs(2), async {
            if echo {
                f.application.receive_payload().await
            } else {
                f.application.echo_once().await
            }
        })
        .await
        .unwrap()
        .unwrap();
        assert!(result.is_empty());
        assert_eq!(f.buffered(), 0);
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_reset_discards_partial_state_and_fails_closed() {
    let mut f = PayloadFixture::new().await;
    f.sending.write_all(b"prefix").await.unwrap();
    cancel_payload_at(&mut f.application, &f.quota, 6, false).await;
    f.sending.reset(VarInt::from_u32(1)).unwrap();
    assert_eq!(
        timeout(Duration::from_secs(2), f.application.receive_payload())
            .await
            .unwrap(),
        Err(TransportError::ApplicationStreamRejected)
    );
    assert_eq!(f.buffered(), 0);
    assert!(
        f.application
            .shared
            .payload_receive
            .lock()
            .unwrap()
            .payload
            .is_empty()
    );
    assert_eq!(
        f.application.receive_payload().await,
        Err(TransportError::ApplicationStreamRejected)
    );
    f.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_revocation_releases_idle_and_pending_cancelled_receive() {
    for waiting in [false, true] {
        let mut f = PayloadFixture::new().await;
        f.sending.write_all(b"prefix").await.unwrap();
        cancel_payload_at(&mut f.application, &f.quota, 6, false).await;
        let shared = Arc::clone(&f.application.shared);
        if waiting {
            let mut pending = Box::pin(f.application.receive_payload());
            let is_pending = std::future::poll_fn(|cx| {
                std::task::Poll::Ready(std::future::Future::poll(pending.as_mut(), cx).is_pending())
            })
            .await;
            assert!(is_pending);
            assert!(shared.inner.try_lock().is_err());
            shared.force_reset();
            // Cleanup cannot depend on the waiting future being polled again.
            assert_eq!(*f.quota.buffered.lock().unwrap(), 0);
            drop(pending);
        } else {
            shared.force_reset();
        }
        assert_eq!(f.buffered(), 0);
        assert!(shared.payload_receive.lock().unwrap().payload.is_empty());
        assert_eq!(
            f.application.receive_payload().await,
            Err(TransportError::ApplicationStreamRejected)
        );
        drop(shared);
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_stream_and_channel_limits_remain_cumulative_after_cancellation() {
    for channel_limit in [false, true] {
        let mut f = PayloadFixture::new().await;
        f.sending.write_all(b"prefix").await.unwrap();
        cancel_payload_at(&mut f.application, &f.quota, 6, false).await;
        let held = if channel_limit {
            Some(
                f.quota
                    .reserve(MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL - 6)
                    .unwrap(),
            )
        } else {
            let rest = vec![0x5a; MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM - 6];
            timeout(Duration::from_secs(2), async {
                let (sent, ()) = tokio::join!(
                    f.sending.write_all(&rest),
                    cancel_payload_at(
                        &mut f.application,
                        &f.quota,
                        MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM,
                        false
                    )
                );
                sent.unwrap();
            })
            .await
            .unwrap();
            None
        };
        f.sending.write_all(b"x").await.unwrap();
        f.sending.finish().unwrap();
        assert_eq!(
            timeout(Duration::from_secs(2), f.application.receive_payload())
                .await
                .unwrap(),
            Err(TransportError::ApplicationPayloadTooLarge)
        );
        assert_eq!(
            f.buffered(),
            if channel_limit {
                MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL - 6
            } else {
                0
            }
        );
        drop(held);
        assert_eq!(f.buffered(), 0);
        assert_eq!(
            f.application.receive_payload().await,
            Err(TransportError::ApplicationStreamRejected)
        );
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_stream_drop_releases_unfinished_reservations() {
    let mut f = PayloadFixture::new().await;
    f.sending.write_all(b"prefix").await.unwrap();
    cancel_payload_at(&mut f.application, &f.quota, 6, false).await;
    let quota = Arc::clone(&f.quota);
    f.close().await;
    assert_eq!(*quota.buffered.lock().unwrap(), 0);
}

// Diagnostic only: cancellation must be distinguished from normal graceful completion.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cancelled_partial_send_abandonment_does_not_report_clean_truncated_eof() {
    let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
    let mut application = source.open_application_stream().await.unwrap();
    let payload = vec![0x5a; 4096];
    let mut sending = Box::pin(application.send_payload(&payload));
    let initially_pending = std::future::poll_fn(|cx| {
        std::task::Poll::Ready(std::future::Future::poll(sending.as_mut(), cx).is_pending())
    })
    .await;
    let (peer_send, mut peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let mut observed_prefix = [0_u8; 1];
    timeout(
        Duration::from_secs(2),
        peer_receive.read_exact(&mut observed_prefix),
    )
    .await
    .unwrap()
    .unwrap();
    let still_pending = std::future::poll_fn(|cx| {
        std::task::Poll::Ready(std::future::Future::poll(sending.as_mut(), cx).is_pending())
    })
    .await;
    drop(sending);
    drop(application); // Follow the documented abandon-stream contract.
    let observed = timeout(
        Duration::from_secs(2),
        peer_receive.read_to_end(payload.len()),
    )
    .await;
    let outcome = match &observed {
        Ok(Ok(tail)) => format!(
            "clean EOF after {} of {} bytes",
            1 + tail.len(),
            payload.len()
        ),
        Ok(Err(error)) => format!("stream error: {error:?}"),
        Err(error) => format!("deadline: {error:?}"),
    };
    // Same authenticated connection: successful sends still finish gracefully.
    let mut normal = source.open_application_stream().await.unwrap();
    let sent = timeout(Duration::from_secs(2), normal.send_payload(b"complete")).await;
    let (normal_peer_send, mut normal_peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let normal_received =
        timeout(Duration::from_secs(2), normal_peer_receive.read_to_end(64)).await;
    drop(normal);
    drop(normal_peer_send);
    drop(normal_peer_receive);
    drop(peer_send);
    drop(peer_receive);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded partial-send reproduction cleanup");
    assert!(
        initially_pending && still_pending,
        "write was pending both before and after proven peer delivery"
    );
    assert_eq!(
        observed_prefix,
        [0x5a],
        "peer delivery proves nonzero send progress"
    );
    assert_eq!(sent.unwrap(), Ok(()));
    assert_eq!(normal_received.unwrap().unwrap(), b"complete");
    assert!(
        matches!(observed, Ok(Err(_))),
        "cancelled incomplete send must not become a successful payload: {outcome}"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_resume_delivers_exact_payload_and_retains_quota() {
    let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
    let mut application = source.open_application_stream().await.unwrap();
    let quota = Arc::new(ChannelByteQuota::default());
    *application.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let expected: Vec<u8> = (0..1024).map(|i| (i % 251) as u8).collect();
    let mut operation = application.begin_owned_send(expected.clone()).unwrap();
    assert_eq!(*quota.buffered.lock().unwrap(), expected.len());
    let mut first = Box::pin(operation.drive());
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(first.as_mut(), cx).is_pending()
        ))
        .await
    );
    let (peer_send, mut peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let mut delivered = vec![0; 64];
    timeout(
        Duration::from_secs(2),
        peer_receive.read_exact(&mut delivered),
    )
    .await
    .unwrap()
    .unwrap();
    drop(first);
    for _ in 0..2 {
        let mut progress = [0; 64];
        let mut driving = Box::pin(operation.drive());
        timeout(Duration::from_secs(2), async {
            tokio::select! {
                result = &mut driving => panic!("tiny-window send completed prematurely: {result:?}"),
                result = peer_receive.read_exact(&mut progress) => { result.unwrap(); }
            }
        }).await.unwrap();
        drop(driving);
        delivered.extend_from_slice(&progress);
        assert_eq!(*quota.buffered.lock().unwrap(), expected.len());
    }
    let mut tail = Vec::new();
    let completion = timeout(Duration::from_secs(2), async {
        tokio::join!(operation.drive(), async {
            let mut chunk = [0; 64];
            loop {
                match peer_receive.read(&mut chunk).await {
                    Ok(Some(count)) => tail.extend_from_slice(&chunk[..count]),
                    Ok(None) => return Ok(()),
                    Err(error) => return Err(error),
                }
            }
        })
    })
    .await;
    let (sent, received) = completion.unwrap_or_else(|error| {
        panic!(
            "{error:?}; delivered {} bytes after resume",
            192 + tail.len()
        )
    });
    sent.unwrap();
    received.unwrap();
    delivered.extend(tail);
    operation.drive().await.unwrap();
    drop(operation);
    assert_eq!(delivered, expected);
    assert_eq!(*quota.buffered.lock().unwrap(), expected.len());
    assert!(matches!(
        application.begin_owned_send(vec![1]),
        Err(TransportError::ApplicationStreamFailed)
    ));
    application.release_buffered_payloads();
    assert_eq!(*quota.buffered.lock().unwrap(), 0);
    drop(application);
    drop(peer_send);
    drop(peer_receive);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_abort_drop_and_revocation_release_partial_send() {
    for terminal in 0..3 {
        let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
        let mut application = source.open_application_stream().await.unwrap();
        let shared = Arc::clone(&application.shared);
        let quota = Arc::new(ChannelByteQuota::default());
        *shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
        let mut operation = application.begin_owned_send(vec![0x5a; 4096]).unwrap();
        let mut driving = Box::pin(operation.drive());
        assert!(
            std::future::poll_fn(|cx| std::task::Poll::Ready(
                std::future::Future::poll(driving.as_mut(), cx).is_pending()
            ))
            .await
        );
        let (peer_send, mut peer_receive) =
            timeout(Duration::from_secs(2), destination.connection.accept_bi())
                .await
                .unwrap()
                .unwrap();
        let mut prefix = [0; 1];
        timeout(Duration::from_secs(2), peer_receive.read_exact(&mut prefix))
            .await
            .unwrap()
            .unwrap();
        if terminal == 2 {
            shared.force_reset();
            assert_eq!(
                *quota.buffered.lock().unwrap(),
                0,
                "revocation must release without repolling drive"
            );
        }
        drop(driving);
        if terminal == 0 {
            operation.abort();
        } else {
            drop(operation);
        }
        assert_eq!(*quota.buffered.lock().unwrap(), 0);
        let outcome = timeout(Duration::from_secs(2), peer_receive.read_to_end(8192)).await;
        drop(application);
        drop(shared);
        drop(peer_send);
        drop(peer_receive);
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
            matches!(outcome, Ok(Err(_))),
            "unfinished owned send must reset: {outcome:?}"
        );
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_begin_checks_bounds_and_preserves_unwritten_abort() {
    let mut f = PayloadFixture::new().await;
    assert!(matches!(
        f.application
            .begin_owned_send(vec![0; MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM + 1]),
        Err(TransportError::ApplicationPayloadTooLarge)
    ));
    assert_eq!(f.buffered(), 0);
    let held = f
        .quota
        .reserve(MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL)
        .unwrap();
    assert!(matches!(
        f.application.begin_owned_send(vec![1]),
        Err(TransportError::ApplicationPayloadTooLarge)
    ));
    drop(held);
    let operation = f
        .application
        .begin_owned_send(vec![1; MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM])
        .unwrap();
    assert_eq!(
        *f.quota.buffered.lock().unwrap(),
        MAX_BUFFERED_APPLICATION_BYTES_PER_STREAM
    );
    operation.abort();
    assert_eq!(f.buffered(), 0);
    f.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_empty_completion_and_legacy_write_mismatch() {
    for owned in [false, true] {
        let mut f = PayloadFixture::new().await;
        if owned {
            let mut operation = f.application.begin_owned_send(Vec::new()).unwrap();
            operation.drive().await.unwrap();
            drop(operation);
        } else {
            f.application.send_payload(b"legacy").await.unwrap();
        }
        assert!(matches!(
            f.application.begin_owned_send(vec![1]),
            Err(TransportError::ApplicationStreamFailed)
        ));
        let received = timeout(Duration::from_secs(2), f.peer_receive.read_to_end(64))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            received,
            if owned {
                b"".as_slice()
            } else {
                b"legacy".as_slice()
            }
        );
        f.application.release_buffered_payloads();
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_rejects_unfinished_receive_and_prior_echo_or_framing() {
    for echo in [false, true] {
        let mut f = PayloadFixture::new().await;
        f.sending.write_all(b"prefix").await.unwrap();
        cancel_payload_at(&mut f.application, &f.quota, 6, echo).await;
        assert!(matches!(
            f.application.begin_owned_send(vec![1]),
            Err(TransportError::ApplicationStreamFailed)
        ));
        assert_eq!(f.buffered(), 6);
        f.sending.finish().unwrap();
        if echo {
            assert_eq!(f.application.echo_once().await.unwrap(), b"prefix");
            assert!(matches!(
                f.application.begin_owned_send(vec![1]),
                Err(TransportError::ApplicationStreamFailed)
            ));
        } else {
            assert_eq!(f.application.receive_payload().await.unwrap(), b"prefix");
            f.application.begin_owned_send(vec![1]).unwrap().abort();
        }
        f.application.release_buffered_payloads();
        f.close().await;
    }
    #[cfg(feature = "benchmark-harness")]
    {
        let mut f = PayloadFixture::new().await;
        f.application.benchmark_write_frame(b"frame").await.unwrap();
        assert!(matches!(
            f.application.begin_owned_send(vec![1]),
            Err(TransportError::ApplicationStreamFailed)
        ));
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_peer_close_releases_paused_ownership() {
    let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
    let mut application = source.open_application_stream().await.unwrap();
    let quota = Arc::new(ChannelByteQuota::default());
    *application.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let mut operation = application.begin_owned_send(vec![0x5a; 4096]).unwrap();
    let mut driving = Box::pin(operation.drive());
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(driving.as_mut(), cx).is_pending()
        ))
        .await
    );
    let (peer_send, mut peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let mut prefix = [0; 1];
    timeout(Duration::from_secs(2), peer_receive.read_exact(&mut prefix))
        .await
        .unwrap()
        .unwrap();
    drop(driving);
    destination.connection.close(VarInt::from_u32(1), b"");
    let outcome = timeout(Duration::from_secs(2), operation.drive()).await;
    let remaining = *quota.buffered.lock().unwrap();
    drop(operation);
    drop(application);
    drop(peer_send);
    drop(peer_receive);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .unwrap();
    assert!(matches!(outcome, Ok(Err(_))));
    assert_eq!(remaining, 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_completion_racing_revocation_cannot_resurrect_quota() {
    let mut f = PayloadFixture::new().await;
    let shared = Arc::clone(&f.application.shared);
    let quota = Arc::clone(&f.quota);
    let terminal_shared = Arc::clone(&shared);
    let terminal_quota = Arc::clone(&quota);
    let (handle_tx, handle_rx) = std::sync::mpsc::channel();
    let mut operation = f
        .application
        .begin_owned_send(b"complete".to_vec())
        .unwrap();
    operation.completion_hook = Some(Box::new(move || {
        // FIN has been queued, but quota still belongs to the operation under
        // its state lock. Force revocation to start at precisely this boundary.
        let state = shared.owned_send.lock().unwrap().upgrade().unwrap();
        let reset_shared = Arc::clone(&shared);
        let handle = std::thread::spawn(move || reset_shared.force_reset());
        handle_tx.send(handle).unwrap();
        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        while !shared.cancelled.load(Ordering::Acquire) {
            assert!(
                std::time::Instant::now() < deadline,
                "revocation did not start"
            );
            std::thread::yield_now();
        }
        assert!(matches!(
            state.try_lock(),
            Err(std::sync::TryLockError::WouldBlock)
        ));
        assert_eq!(*quota.buffered.lock().unwrap(), 8);
        assert!(
            shared
                .outbound_bytes
                .reservations
                .lock()
                .unwrap()
                .is_empty()
        );
    }));
    assert_eq!(
        operation.drive().await,
        Err(TransportError::ApplicationStreamRejected)
    );
    handle_rx
        .recv_timeout(Duration::from_secs(2))
        .unwrap()
        .join()
        .unwrap();
    assert_eq!(*terminal_quota.buffered.lock().unwrap(), 0);
    assert!(
        terminal_shared
            .outbound_bytes
            .reservations
            .lock()
            .unwrap()
            .is_empty()
    );
    drop(operation);
    assert_eq!(f.buffered(), 0);
    assert!(
        f.application
            .shared
            .outbound_bytes
            .reservations
            .lock()
            .unwrap()
            .is_empty()
    );
    f.application.shared.force_reset();
    assert_eq!(f.buffered(), 0, "repeated terminal cleanup is idempotent");
    f.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn owned_send_completed_fin_ack_and_terminal_quota_ownership() {
    for revoke in [false, true] {
        let mut f = PayloadFixture::new().await;
        let mut operation = f
            .application
            .begin_owned_send(b"complete".to_vec())
            .unwrap();
        operation.drive().await.unwrap();
        operation.drive().await.unwrap();
        drop(operation);
        assert_eq!(f.buffered(), 8);
        assert_eq!(
            f.application
                .shared
                .outbound_bytes
                .reservations
                .lock()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            timeout(Duration::from_secs(2), f.peer_receive.read_to_end(64))
                .await
                .unwrap()
                .unwrap(),
            b"complete"
        );
        timeout(Duration::from_secs(2), f.application.wait_for_send_ack())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            f.buffered(),
            8,
            "transport ACK does not release application-owned quota"
        );
        if revoke {
            f.application.shared.force_reset();
        } else {
            f.application.release_buffered_payloads();
        }
        assert_eq!(f.buffered(), 0);
        f.application.release_buffered_payloads();
        assert_eq!(f.buffered(), 0);
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn borrowed_send_cancel_before_progress_preserves_stream_and_quota() {
    for poll in [false, true] {
        let mut f = PayloadFixture::new().await;
        let shared = Arc::clone(&f.application.shared);
        // Hold the stream lock to make the polled case deterministically wait
        // before any transport write; the unpolled case does not reserve at all.
        let inner = shared.inner.lock().await;
        let mut sending = Box::pin(f.application.send_payload(b"abandoned"));
        if poll {
            assert!(
                std::future::poll_fn(|cx| std::task::Poll::Ready(
                    std::future::Future::poll(sending.as_mut(), cx).is_pending()
                ))
                .await
            );
            assert_eq!(*f.quota.buffered.lock().unwrap(), 9);
        }
        drop(sending);
        drop(inner);
        assert_eq!(f.buffered(), 0);
        assert!(!shared.cancelled.load(Ordering::Acquire));
        assert!(!shared.application_write_started.load(Ordering::Acquire));
        let mut operation = f
            .application
            .begin_owned_send(b"replacement".to_vec())
            .unwrap();
        operation.drive().await.unwrap();
        drop(operation);
        assert_eq!(
            timeout(Duration::from_secs(2), f.peer_receive.read_to_end(64))
                .await
                .unwrap()
                .unwrap(),
            b"replacement"
        );
        f.application.release_buffered_payloads();
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn borrowed_send_partial_cancellation_is_terminal_and_sibling_survives() {
    let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
    let mut sibling = source.open_application_stream().await.unwrap();
    sibling.send_payload(b"sibling").await.unwrap();
    let (sibling_peer_send, mut sibling_peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let mut application = source.open_application_stream().await.unwrap();
    let quota = Arc::new(ChannelByteQuota::default());
    *application.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let shared = Arc::clone(&application.shared);
    let payload = vec![0x5a; 4096];
    let mut sending = Box::pin(application.send_payload(&payload));
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(sending.as_mut(), cx).is_pending()
        ))
        .await
    );
    let (peer_send, mut peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let mut prefix = [0; 1];
    timeout(Duration::from_secs(2), peer_receive.read_exact(&mut prefix))
        .await
        .unwrap()
        .unwrap();
    drop(sending);
    assert!(
        shared.cancelled.load(Ordering::Acquire),
        "partial cancellation must mark terminal even if the stream object is retained"
    );
    assert_eq!(*quota.buffered.lock().unwrap(), 0);
    assert_eq!(
        application.send_payload(b"retry").await,
        Err(TransportError::ApplicationStreamRejected)
    );
    assert!(matches!(
        timeout(Duration::from_secs(2), peer_receive.read_to_end(8192)).await,
        Ok(Err(_))
    ));
    assert_eq!(
        timeout(Duration::from_secs(2), sibling_peer_receive.read_to_end(64))
            .await
            .unwrap()
            .unwrap(),
        b"sibling"
    );
    timeout(Duration::from_secs(2), sibling.wait_for_send_ack())
        .await
        .unwrap()
        .unwrap();
    drop(application);
    drop(sibling);
    drop(peer_send);
    drop(peer_receive);
    drop(sibling_peer_send);
    drop(sibling_peer_receive);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn borrowed_send_revocation_while_waiting_for_lock_is_not_lost() {
    let mut f = PayloadFixture::new().await;
    let shared = Arc::clone(&f.application.shared);
    let inner = shared.inner.lock().await;
    let mut sending = Box::pin(f.application.send_payload(b"pending"));
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(sending.as_mut(), cx).is_pending()
        ))
        .await
    );
    shared.force_reset();
    drop(inner);
    assert_eq!(
        timeout(Duration::from_secs(2), &mut sending).await.unwrap(),
        Err(TransportError::ApplicationStreamRejected)
    );
    drop(sending);
    assert_eq!(f.buffered(), 0);
    assert_eq!(
        f.application.send_payload(b"retry").await,
        Err(TransportError::ApplicationStreamRejected)
    );
    f.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn borrowed_send_success_preserves_fin_ack_and_completed_quota() {
    for payload in [b"".as_slice(), b"complete".as_slice()] {
        let mut f = PayloadFixture::new().await;
        f.application.send_payload(payload).await.unwrap();
        assert!(!f.application.shared.cancelled.load(Ordering::Acquire));
        assert_eq!(f.buffered(), payload.len());
        assert_eq!(
            timeout(Duration::from_secs(2), f.peer_receive.read_to_end(64))
                .await
                .unwrap()
                .unwrap(),
            payload
        );
        timeout(Duration::from_secs(2), f.application.wait_for_send_ack())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(f.buffered(), payload.len());
        f.application.release_buffered_payloads();
        assert_eq!(f.buffered(), 0);
        f.close().await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn borrowed_send_zero_progress_revocation_then_drop_still_resets() {
    let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
    let (mut send, receive) = source.connection.open_bi().await.unwrap();
    // Exhaust transport credit with fixture preface bytes, before constructing
    // the application wrapper. Its first payload write must accept zero bytes.
    send.write_all(&[0xaa; 64]).await.unwrap();
    let (peer_send, mut peer_receive) =
        timeout(Duration::from_secs(2), destination.connection.accept_bi())
            .await
            .unwrap()
            .unwrap();
    let mut application = application_stream(send, receive);
    let shared = Arc::clone(&application.shared);
    let quota = Arc::new(ChannelByteQuota::default());
    *shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let mut sending = Box::pin(application.send_payload(b"blocked"));
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(sending.as_mut(), cx).is_pending()
        ))
        .await
    );
    assert!(!shared.application_write_started.load(Ordering::Acquire));
    assert!(
        shared.inner.try_lock().is_err(),
        "pending write holds inner"
    );
    shared.force_reset();
    drop(sending); // Deliberately never repoll the revocation notification.
    assert_eq!(*quota.buffered.lock().unwrap(), 0);
    drop(application);
    let outcome = timeout(Duration::from_secs(2), peer_receive.read_to_end(128)).await;
    drop(peer_send);
    drop(peer_receive);
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
        matches!(outcome, Ok(Err(_))),
        "revoked zero-progress send must reset rather than expose clean EOF: {outcome:?}"
    );
}

// Reproduction: exercise the documented terminal abandonment contract, not resume.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cancelled_partial_echo_abandonment_does_not_report_clean_truncated_eof() {
    let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
    // The destination opens the request stream so the existing source-to-
    // destination 64-byte window limits only the echo response direction.
    let (mut request_send, mut response_receive) = destination.connection.open_bi().await.unwrap();
    let payload = vec![0x5a; 4096];
    request_send.write_all(&payload).await.unwrap();
    request_send.finish().unwrap();
    let (send, receive) = timeout(Duration::from_secs(2), source.connection.accept_bi())
        .await
        .unwrap()
        .unwrap();
    let mut application = application_stream(send, receive);
    let quota = Arc::new(ChannelByteQuota::default());
    *application.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let mut echoing = Box::pin(application.echo_once());
    let mut prefix = [0_u8; 1];
    timeout(Duration::from_secs(2), async {
        tokio::select! {
            result = &mut echoing => panic!("echo completed before partial response checkpoint: {result:?}"),
            result = response_receive.read_exact(&mut prefix) => result.unwrap(),
        }
    }).await.unwrap();
    // Receiving a response proves read_live_payload consumed the complete request
    // through FIN. Check both quota directions before cancelling the pending echo.
    let retained_before_cancel = *quota.buffered.lock().unwrap();
    let still_pending = std::future::poll_fn(|cx| {
        std::task::Poll::Ready(std::future::Future::poll(echoing.as_mut(), cx).is_pending())
    })
    .await;
    drop(echoing);
    let retained_after_cancel = *quota.buffered.lock().unwrap();
    drop(application); // Follow echo_once's documented abandon-stream instruction.
    let outcome = timeout(Duration::from_secs(2), response_receive.read_to_end(8192)).await;
    let description = match &outcome {
        Ok(Ok(tail)) => format!(
            "clean EOF after {} of {} response bytes",
            1 + tail.len(),
            payload.len()
        ),
        Ok(Err(error)) => format!("stream error: {error:?}"),
        Err(error) => format!("deadline: {error:?}"),
    };
    // Normal echo on the same connection must retain FIN and bidirectional quota.
    let (mut normal_request, mut normal_response) = destination.connection.open_bi().await.unwrap();
    normal_request.write_all(b"complete").await.unwrap();
    normal_request.finish().unwrap();
    let (send, receive) = timeout(Duration::from_secs(2), source.connection.accept_bi())
        .await
        .unwrap()
        .unwrap();
    let mut normal = application_stream(send, receive);
    *normal.shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
    let normal_result = timeout(Duration::from_secs(2), normal.echo_once()).await;
    let normal_received = timeout(Duration::from_secs(2), normal_response.read_to_end(64)).await;
    let retained_after_normal = *quota.buffered.lock().unwrap();
    normal.release_buffered_payloads();
    let retained_after_release = *quota.buffered.lock().unwrap();
    drop(normal);
    drop(normal_request);
    drop(normal_response);
    drop(request_send);
    drop(response_receive);
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded echo reproduction cleanup");
    assert_eq!(prefix, [0x5a]);
    assert!(
        still_pending,
        "echo must remain pending after proven partial response"
    );
    assert_eq!(retained_before_cancel, 8192);
    assert_eq!(retained_after_cancel, 0);
    assert_eq!(normal_result.unwrap().unwrap(), b"complete");
    assert_eq!(normal_received.unwrap().unwrap(), b"complete");
    assert_eq!(retained_after_normal, 16);
    assert_eq!(retained_after_release, 0);
    assert!(
        matches!(outcome, Ok(Err(_))),
        "abandoned incomplete echo must not report a successful response: {description}"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn echo_response_zero_progress_cancel_and_revocation_are_terminal() {
    // 0: ordinary cancellation; 1: revoke then drop without repoll;
    // 2: revoke then drive to error; 3: peer STOP_SENDING during response.
    for terminal in 0..4 {
        let (listener, source, destination) = connection_pair_with_window(Some(64)).await;
        let (mut send, receive) = source.connection.open_bi().await.unwrap();
        send.write_all(&[0xaa; 64]).await.unwrap();
        let (mut request_send, mut response_receive) =
            timeout(Duration::from_secs(2), destination.connection.accept_bi())
                .await
                .unwrap()
                .unwrap();
        request_send.write_all(b"request").await.unwrap();
        request_send.finish().unwrap();
        let mut application = application_stream(send, receive);
        let shared = Arc::clone(&application.shared);
        let quota = Arc::new(ChannelByteQuota::default());
        *shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
        let mut echoing = Box::pin(application.echo_once());
        timeout(Duration::from_secs(2), async {
            loop {
                assert!(
                    std::future::poll_fn(|cx| std::task::Poll::Ready(
                        std::future::Future::poll(echoing.as_mut(), cx).is_pending()
                    ))
                    .await
                );
                if shared.application_write_started.load(Ordering::Acquire) {
                    break;
                }
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        // The unread 64-byte fixture preface exhausts response credit. Reception
        // is complete but none of the seven response bytes can have been accepted.
        assert_eq!(*quota.buffered.lock().unwrap(), 14);
        assert!(shared.inner.try_lock().is_err());
        if terminal == 1 || terminal == 2 {
            shared.force_reset();
        }
        if terminal == 2 {
            assert_eq!(
                timeout(Duration::from_secs(2), &mut echoing).await.unwrap(),
                Err(TransportError::ApplicationStreamRejected)
            );
        }
        if terminal == 3 {
            response_receive.stop(VarInt::from_u32(1)).unwrap();
            assert_eq!(
                timeout(Duration::from_secs(2), &mut echoing).await.unwrap(),
                Err(TransportError::ApplicationStreamFailed)
            );
        }
        drop(echoing);
        let cancelled = shared.cancelled.load(Ordering::Acquire);
        let retained = *quota.buffered.lock().unwrap();
        // A locally stopped receiver's later reads do not establish the sender's
        // reset. For STOP_SENDING, assert the sender error/terminal/quota above.
        let outcome = if terminal == 3 {
            None
        } else {
            Some(timeout(Duration::from_secs(2), response_receive.read_to_end(128)).await)
        };
        drop(application);
        drop(shared);
        drop(request_send);
        drop(response_receive);
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
            cancelled,
            "completed request makes response cancellation terminal even before its first byte"
        );
        assert_eq!(retained, 0);
        if let Some(outcome) = outcome {
            assert!(
                matches!(outcome, Ok(Err(_))),
                "response phase must reset without dropping the stream owner: {outcome:?}"
            );
        }
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn echo_response_quota_failure_is_terminal_and_releases_request() {
    let mut f = PayloadFixture::new().await;
    let held = f
        .quota
        .reserve(MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL - 7)
        .unwrap();
    f.sending.write_all(b"request").await.unwrap();
    f.sending.finish().unwrap();
    let result = timeout(Duration::from_secs(2), f.application.echo_once())
        .await
        .unwrap();
    let cancelled = f.application.shared.cancelled.load(Ordering::Acquire);
    let retained = f.buffered();
    drop(held);
    f.close().await;
    assert_eq!(result, Err(TransportError::ApplicationPayloadTooLarge));
    assert_eq!(retained, MAX_BUFFERED_APPLICATION_BYTES_PER_CHANNEL - 7);
    assert!(
        cancelled,
        "failed response reservation must invalidate the consumed request"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn echo_response_empty_success_keeps_fin_and_ack() {
    let mut f = PayloadFixture::new().await;
    f.sending.finish().unwrap();
    assert_eq!(f.application.echo_once().await.unwrap(), b"");
    assert_eq!(
        timeout(Duration::from_secs(2), f.peer_receive.read_to_end(64))
            .await
            .unwrap()
            .unwrap(),
        b""
    );
    timeout(Duration::from_secs(2), f.application.wait_for_send_ack())
        .await
        .unwrap()
        .unwrap();
    assert!(!f.application.shared.cancelled.load(Ordering::Acquire));
    assert_eq!(f.buffered(), 0);
    f.close().await;
}

// Characterization: whole-composite restart is documented as unsupported.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn composite_response_cancellation_retry_and_receive_only_characterization() {
    let (listener, source, destination) = connection_pair().await;
    let quota = Arc::new(ChannelByteQuota::default());
    // Retry the composite, resume only reception, then complete normally on a
    // fresh sibling: all three exchanges share one authenticated connection.
    for mode in 0..3 {
        let mut application = source.open_application_stream().await.unwrap();
        let shared = Arc::clone(&application.shared);
        *shared.channel_quota.lock().unwrap() = Some(Arc::clone(&quota));
        let mut exchange = Box::pin(application.send_and_receive(b"request"));
        assert!(
            std::future::poll_fn(|cx| std::task::Poll::Ready(
                std::future::Future::poll(exchange.as_mut(), cx).is_pending()
            ))
            .await
        );
        let (mut response_send, mut request_receive) =
            timeout(Duration::from_secs(2), destination.connection.accept_bi())
                .await
                .unwrap()
                .unwrap();
        assert_eq!(
            timeout(Duration::from_secs(2), request_receive.read_to_end(64))
                .await
                .unwrap()
                .unwrap(),
            b"request"
        );
        // Request FIN is observed before any cancellation; six response bytes
        // are then retained without response FIN, so the exact phase is known.
        response_send.write_all(b"prefix").await.unwrap();
        timeout(Duration::from_secs(2), async {
            loop {
                assert!(
                    std::future::poll_fn(|cx| std::task::Poll::Ready(
                        std::future::Future::poll(exchange.as_mut(), cx).is_pending()
                    ))
                    .await
                );
                if *quota.buffered.lock().unwrap() == 13 {
                    break;
                }
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        assert_eq!(shared.payload_receive.lock().unwrap().payload, b"prefix");
        if mode == 2 {
            response_send.write_all(b"-suffix").await.unwrap();
            response_send.finish().unwrap();
            assert_eq!(
                timeout(Duration::from_secs(2), &mut exchange)
                    .await
                    .unwrap()
                    .unwrap(),
                b"prefix-suffix"
            );
            drop(exchange);
            assert_eq!(*quota.buffered.lock().unwrap(), 20);
            assert!(!shared.cancelled.load(Ordering::Acquire));
        } else {
            drop(exchange);
            assert_eq!(
                *quota.buffered.lock().unwrap(),
                13,
                "cancelling receive wait retains completed request and response prefix"
            );
            assert!(!shared.cancelled.load(Ordering::Acquire));
            if mode == 0 {
                assert_eq!(
                    timeout(
                        Duration::from_secs(2),
                        application.send_and_receive(b"request")
                    )
                    .await
                    .unwrap(),
                    Err(TransportError::ApplicationStreamFailed)
                );
                assert!(shared.cancelled.load(Ordering::Acquire));
                assert!(shared.payload_receive.lock().unwrap().payload.is_empty());
                assert_eq!(*quota.buffered.lock().unwrap(), 0);
                assert_eq!(
                    application.receive_payload().await,
                    Err(TransportError::ApplicationStreamRejected)
                );
                // FIN already ended this direction. No duplicate request bytes
                // may appear; either the finished read or reset is acceptable.
                if let Ok(tail) = timeout(Duration::from_secs(2), request_receive.read_to_end(64))
                    .await
                    .unwrap()
                {
                    assert!(tail.is_empty(), "retry delivered duplicate request bytes");
                }
            } else {
                response_send.write_all(b"-suffix").await.unwrap();
                response_send.finish().unwrap();
                assert_eq!(
                    timeout(Duration::from_secs(2), application.receive_payload())
                        .await
                        .unwrap()
                        .unwrap(),
                    b"prefix-suffix"
                );
                assert_eq!(*quota.buffered.lock().unwrap(), 20);
                assert!(!shared.cancelled.load(Ordering::Acquire));
            }
        }
        application.release_buffered_payloads();
        assert_eq!(*quota.buffered.lock().unwrap(), 0);
        drop(application);
        drop(shared);
        drop(response_send);
        drop(request_receive);
    }
    timeout(Duration::from_secs(8), async {
        let (a, b) = tokio::join!(source.close(), destination.close());
        let c = listener.close().await;
        a.unwrap();
        b.unwrap();
        c.unwrap();
    })
    .await
    .expect("bounded composite characterization cleanup");
    assert_eq!(*quota.buffered.lock().unwrap(), 0);
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_frame_revocation_interrupts_pending_read_and_rejects_reuse() {
    let mut f = PayloadFixture::with_window(Some(64)).await;
    let shared = Arc::clone(&f.application.shared);
    f.sending.write_all(&[0, 0]).await.unwrap();
    let mut reading = Box::pin(f.application.benchmark_read_frame());
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(reading.as_mut(), cx).is_pending()
        ))
        .await
    );
    shared.force_reset();
    let result = timeout(Duration::from_millis(250), &mut reading).await;
    drop(reading);
    let cancelled = shared.cancelled.load(Ordering::Acquire);
    f.close().await;
    assert!(cancelled);
    assert!(
        matches!(result, Ok(Err(TransportError::ApplicationStreamRejected))),
        "revocation must wake pending benchmark frame read without more peer bytes: {result:?}"
    );
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_frame_body_pending_revocation_resets_and_releases_ownership() {
    let mut f = PayloadFixture::with_window(Some(64)).await;
    let shared = Arc::clone(&f.application.shared);
    let weak = Arc::downgrade(&shared);
    let quota = Arc::clone(&f.quota);
    // Complete length, one of eight body bytes, and no FIN. The rest is never sent.
    f.sending.write_all(&[0, 0, 0, 8, b'x']).await.unwrap();
    let mut reading = Box::pin(f.application.benchmark_read_frame());
    let checkpoint = timeout(
        Duration::from_secs(2),
        std::future::poll_fn(|cx| match std::future::Future::poll(reading.as_mut(), cx) {
            std::task::Poll::Ready(_) => std::task::Poll::Ready(false),
            std::task::Poll::Pending => {
                if shared
                    .benchmark_body_length_checkpoint
                    .load(Ordering::Acquire)
                    == 8
                {
                    std::task::Poll::Ready(true)
                } else {
                    std::task::Poll::Pending
                }
            }
        }),
    )
    .await;
    let body_pending = matches!(checkpoint, Ok(true));
    let held_lock = shared.inner.try_lock().is_err();
    shared.force_reset();
    // An unexpected Ready during checkpoint detection has already completed
    // this future. Do not repoll it: preserve the cleanup path before failing.
    let result = if body_pending {
        Some(timeout(Duration::from_millis(250), &mut reading).await)
    } else {
        None
    };
    drop(reading);
    let unlocked = shared.inner.try_lock().is_ok();
    let mut byte = [0];
    let peer_reset = timeout(Duration::from_secs(2), f.peer_receive.read(&mut byte)).await;
    let reuse = timeout(
        Duration::from_millis(250),
        f.application.benchmark_read_frame(),
    )
    .await;
    let retained = f.buffered();
    let empty_receive = shared.payload_receive.lock().unwrap().payload.is_empty();
    let empty_inbound = shared.inbound_bytes.reservations.lock().unwrap().is_empty();
    let empty_outbound = shared
        .outbound_bytes
        .reservations
        .lock()
        .unwrap()
        .is_empty();
    drop(shared);
    f.close().await;
    assert!(
        body_pending,
        "must reach incomplete body I/O: {checkpoint:?}"
    );
    assert!(held_lock && unlocked);
    assert!(matches!(
        result,
        Some(Ok(Err(TransportError::ApplicationStreamRejected)))
    ));
    assert!(
        matches!(peer_reset, Ok(Err(quinn::ReadError::Reset(_)))),
        "peer reset before connection cleanup: {peer_reset:?}"
    );
    assert!(matches!(
        reuse,
        Ok(Err(TransportError::ApplicationStreamRejected))
    ));
    assert_eq!(
        retained, 0,
        "benchmark body bytes create no payload reservation"
    );
    assert!(empty_receive && empty_inbound && empty_outbound);
    assert!(
        weak.upgrade().is_none(),
        "no shared stream owner survives fixture cleanup"
    );
    assert_eq!(*quota.buffered.lock().unwrap(), 0);
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_frame_revocation_interrupts_pending_write() {
    let mut f = PayloadFixture::with_window(Some(64)).await;
    let shared = Arc::clone(&f.application.shared);
    let wire = vec![0x5a; 4096];
    let mut writing = Box::pin(f.application.benchmark_write_frame(&wire));
    assert!(
        std::future::poll_fn(|cx| std::task::Poll::Ready(
            std::future::Future::poll(writing.as_mut(), cx).is_pending()
        ))
        .await
    );
    let mut prefix = [0; 4];
    timeout(
        Duration::from_secs(2),
        f.peer_receive.read_exact(&mut prefix),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(u32::from_be_bytes(prefix), 4096);
    shared.force_reset();
    let result = timeout(Duration::from_millis(250), &mut writing).await;
    drop(writing);
    f.close().await;
    assert!(
        matches!(result, Ok(Err(TransportError::ApplicationStreamRejected))),
        "revocation must wake a blocked frame write without peer credit: {result:?}"
    );
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_frame_normal_reuse_and_revoked_buffered_data() {
    let mut f = PayloadFixture::with_window(Some(64)).await;
    for wire in [b"first".as_slice(), b"".as_slice(), b"last".as_slice()] {
        f.sending
            .write_all(&(wire.len() as u32).to_be_bytes())
            .await
            .unwrap();
        f.sending.write_all(wire).await.unwrap();
        assert_eq!(
            timeout(Duration::from_secs(2), f.application.benchmark_read_frame())
                .await
                .unwrap()
                .unwrap(),
            wire
        );
        f.application.benchmark_write_frame(wire).await.unwrap();
        let mut length = [0; 4];
        timeout(
            Duration::from_secs(2),
            f.peer_receive.read_exact(&mut length),
        )
        .await
        .unwrap()
        .unwrap();
        let mut received = vec![0; u32::from_be_bytes(length) as usize];
        timeout(
            Duration::from_secs(2),
            f.peer_receive.read_exact(&mut received),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(received, wire);
        assert!(!f.application.shared.cancelled.load(Ordering::Acquire));
    }
    f.sending
        .write_all(&[0, 0, 0, 3, b'e', b'n', b'd'])
        .await
        .unwrap();
    f.application.shared.force_reset();
    let read = timeout(
        Duration::from_millis(250),
        f.application.benchmark_read_frame(),
    )
    .await;
    let write = timeout(
        Duration::from_millis(250),
        f.application.benchmark_write_frame(b"late"),
    )
    .await;
    assert_eq!(
        f.buffered(),
        0,
        "benchmark framing creates no payload reservations"
    );
    f.close().await;
    assert!(matches!(
        read,
        Ok(Err(TransportError::ApplicationStreamRejected))
    ));
    assert!(matches!(
        write,
        Ok(Err(TransportError::ApplicationStreamRejected))
    ));
}

#[cfg(feature = "benchmark-harness")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn benchmark_frame_revocation_then_future_drop_completes_reset() {
    for writing in [false, true] {
        let mut f = PayloadFixture::with_window(Some(64)).await;
        let shared = Arc::clone(&f.application.shared);
        if !writing {
            f.sending.write_all(&[0, 0]).await.unwrap();
        }
        let wire = vec![0x5a; 4096];
        let mut operation = Box::pin(async {
            if writing {
                f.application.benchmark_write_frame(&wire).await
            } else {
                f.application.benchmark_read_frame().await.map(|_| ())
            }
        });
        assert!(
            std::future::poll_fn(|cx| std::task::Poll::Ready(
                std::future::Future::poll(operation.as_mut(), cx).is_pending()
            ))
            .await
        );
        assert!(shared.inner.try_lock().is_err());
        shared.force_reset();
        drop(operation); // Do not repoll revocation; keep stream owner alive.
        let peer = timeout(Duration::from_secs(2), f.peer_receive.read_to_end(8192)).await;
        let read = timeout(
            Duration::from_millis(250),
            f.application.benchmark_read_frame(),
        )
        .await;
        let write = timeout(
            Duration::from_millis(250),
            f.application.benchmark_write_frame(b"late"),
        )
        .await;
        let retained = f.buffered();
        drop(shared);
        f.close().await;
        assert!(
            matches!(peer, Ok(Err(_))),
            "revoked frame future Drop must finish stream reset: {peer:?}"
        );
        assert!(matches!(
            read,
            Ok(Err(TransportError::ApplicationStreamRejected))
        ));
        assert!(matches!(
            write,
            Ok(Err(TransportError::ApplicationStreamRejected))
        ));
        assert_eq!(retained, 0);
    }
}
