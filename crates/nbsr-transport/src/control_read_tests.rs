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
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .expect("listener");
    let remote = listener.local_addr().expect("address");
    let (destination, source) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy, pki.source_material()).expect("client config"),
            remote,
        )
    );
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
