use std::path::PathBuf;

use nbsr_transport::{CoreV02Limits, CoreV02MessageType, decode_control_envelope};

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

#[test]
fn public_stream_controls_remain_deterministically_decodable() {
    let open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_OPEN fixture");
    let accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_ACCEPT fixture");

    assert_eq!(open.message_type(), CoreV02MessageType::StreamOpen);
    assert_eq!(accept.message_type(), CoreV02MessageType::StreamAccept);
}
