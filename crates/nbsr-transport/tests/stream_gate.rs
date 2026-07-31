use nbsr_transport::{ActiveChannel, StreamGate, StreamOpenRequest, StreamReject};

fn channel() -> ActiveChannel {
    ActiveChannel {
        channel_id: [1; 16],
        route_id: [2; 16],
        service_id: "service.example".into(),
        route_grant_digest: [3; 32],
        transport: "tcp".into(),
        port: 8443,
    }
}

fn request() -> StreamOpenRequest {
    StreamOpenRequest {
        quic_stream_id: 4,
        channel_id: [1; 16],
        route_id: [2; 16],
        route_grant_digest: [3; 32],
        transport: "tcp".into(),
        port: 8443,
    }
}

#[test]
fn one_stream_is_bound_to_only_the_accepted_service_channel() {
    let mut gate = StreamGate::new(channel());
    gate.authorize(&request()).expect("first stream is bound");
    assert_eq!(
        gate.authorize(&request()),
        Err(StreamReject::DuplicateStream)
    );

    let mut other = request();
    other.channel_id = [9; 16];
    let mut new_gate = StreamGate::new(channel());
    assert_eq!(
        new_gate.authorize(&other),
        Err(StreamReject::ChannelMismatch)
    );

    let mut wrong_port = request();
    wrong_port.port = 443;
    let mut port_gate = StreamGate::new(channel());
    assert_eq!(
        port_gate.authorize(&wrong_port),
        Err(StreamReject::UnsupportedTransport)
    );
}
