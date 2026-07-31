use std::path::PathBuf;

use nbsr_transport::{
    ActiveChannel, CoreV02Limits, StreamGate, StreamReject, decode_control_envelope,
};
use sha2::{Digest, Sha256};

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

fn channel() -> ActiveChannel {
    let grant = vector("artifacts/valid/objects/route-grant-sign1.cose");
    ActiveChannel {
        channel_id: (0x40..0x50).collect::<Vec<_>>().try_into().unwrap(),
        route_id: (0x20..0x30).collect::<Vec<_>>().try_into().unwrap(),
        service_id: "service.example".into(),
        route_grant_digest: Sha256::digest(grant).into(),
        transport: "tcp".into(),
        port: 8443,
    }
}

fn stream_open() -> nbsr_transport::CoreV02Envelope {
    decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_OPEN fixture")
}

fn stream_accept() -> nbsr_transport::CoreV02Envelope {
    decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_ACCEPT fixture")
}

#[test]
fn one_stream_is_bound_to_only_the_accepted_service_channel() {
    let mut gate = StreamGate::new(channel());
    gate.authorize_open(&stream_open())
        .expect("fixture STREAM_OPEN is bound");
    gate.accept(&stream_accept())
        .expect("matching STREAM_ACCEPT is bound");
    assert_eq!(
        gate.authorize_open(&stream_open()),
        Err(StreamReject::DuplicateStream)
    );

    let mut other_channel = channel();
    other_channel.channel_id = [9; 16];
    let mut other_gate = StreamGate::new(other_channel);
    assert_eq!(
        other_gate.authorize_open(&stream_open()),
        Err(StreamReject::ChannelMismatch)
    );

    let mut wrong_port = channel();
    wrong_port.port = 443;
    let mut port_gate = StreamGate::new(wrong_port);
    assert_eq!(
        port_gate.authorize_open(&stream_open()),
        Err(StreamReject::UnsupportedTransport)
    );
}
