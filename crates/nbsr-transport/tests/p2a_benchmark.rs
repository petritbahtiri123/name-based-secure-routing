#![cfg(feature = "benchmark-harness")]

use std::time::Instant;

use nbsr_transport::p2a_benchmark::{
    FrameError, OutstandingTracker, decode_frame, decode_measured_frame, encode_frame,
    encode_measured_frame,
};

#[test]
fn frame_round_trip_preserves_literal_sequence_and_payload() {
    let wire = encode_frame(0x0102_0304_0506_0708, &[0x00, 0x7f, 0xff]);
    let decoded = decode_frame(&wire, 0x0102_0304_0506_0708, 3).unwrap();
    assert_eq!(decoded, [0x00, 0x7f, 0xff]);
}

#[test]
fn frame_rejects_wrong_sequence() {
    let wire = encode_frame(7, b"payload");
    assert_eq!(decode_frame(&wire, 8, 7), Err(FrameError::WrongSequence));
}

#[test]
fn frame_rejects_corrupted_payload() {
    let mut wire = encode_frame(9, b"payload");
    wire[12] ^= 0x01;
    assert_eq!(decode_frame(&wire, 9, 7), Err(FrameError::Corrupt));
}

#[test]
fn frame_rejects_wrong_payload_length() {
    let wire = encode_frame(11, b"payload");
    assert_eq!(decode_frame(&wire, 11, 6), Err(FrameError::WrongLength));
}

#[test]
fn measured_frame_preserves_wire_size_without_reusing_full_sha_tag() {
    let payload = vec![0x5a; 16_384];
    let historical = encode_frame(1, &payload);
    let measured = encode_measured_frame(1, &payload);
    assert_eq!(measured.len(), historical.len());
    assert_ne!(
        &measured[measured.len() - 16..],
        &historical[historical.len() - 16..]
    );
    assert_eq!(
        decode_measured_frame(&measured, 1, &payload).unwrap(),
        payload
    );
}

#[test]
fn measured_frame_sample_detects_corruption_away_from_bounded_probes() {
    let payload = vec![0x5a; 16_384];
    let mut measured = encode_measured_frame(1024, &payload);
    measured[12 + 777] ^= 1;
    assert_eq!(
        decode_measured_frame(&measured, 1024, &payload),
        Err(FrameError::Corrupt)
    );
}

#[test]
fn outstanding_tracker_enforces_bound_fifo_and_conservation() {
    let now = Instant::now();
    let mut tracker = OutstandingTracker::new(2).unwrap();
    tracker.issue(10, now).unwrap();
    tracker.issue(11, now).unwrap();
    assert!(tracker.issue(12, now).is_err());
    assert_eq!(tracker.complete(10).unwrap(), now);
    tracker.issue(12, now).unwrap();
    assert!(tracker.complete(12).is_err());
    assert_eq!(tracker.complete(11).unwrap(), now);
    assert_eq!(tracker.complete(12).unwrap(), now);
    assert_eq!(tracker.sent(), 3);
    assert_eq!(tracker.completed(), 3);
    assert_eq!(tracker.in_flight(), 0);
    assert_eq!(tracker.max_in_flight(), 2);
}
