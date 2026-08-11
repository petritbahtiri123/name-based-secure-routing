#![cfg(feature = "benchmark-harness")]

use nbsr_transport::p2a_benchmark::{FrameError, decode_frame, encode_frame};

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
