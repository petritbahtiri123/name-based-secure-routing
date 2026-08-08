use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use nbsr_transport::{
    ActiveChannel, AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Envelope,
    CoreV02Limits, DestinationAdmission, EdgeIdentity, EdgeRole,
    LocalFederationAdmissionAttestations, LocalFederationAdmissionAuthorities, PeerPolicy,
    RouteGrantIssuer, TransportError, TransportListener, TrustProfileId, build_client_config,
    build_server_config, connect, decode_control_envelope,
};
use sha2::{Digest, Sha256};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn vector(relative: &str) -> Vec<u8> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::fs::read(root.join("vectors/core-v0.2").join(relative)).expect("Core v0.2 fixture")
}

fn channel() -> ActiveChannel {
    let grant = vector("artifacts/valid/objects/route-grant-sign1.cose");
    let digest: [u8; 32] = Sha256::digest(grant).into();
    let channel_id: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    let route_id: [u8; 16] = (0x20..0x30).collect::<Vec<_>>().try_into().unwrap();
    ActiveChannel {
        channel_id,
        route_id,
        service_id: "service.example".into(),
        route_grant_digest: digest,
        transport: "tcp".into(),
        port: 8443,
    }
}

fn control_session(connection: &nbsr_transport::AuthenticatedConnection) -> ControlSession {
    let policy = AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "service.example".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: [
                    0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2,
                    0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2,
                    0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                ],
            },
        )]),
        now: 1_893_456_000,
        client_session_public_key: [
            0x3d, 0x40, 0x17, 0xc3, 0xe8, 0x43, 0x89, 0x5a, 0x92, 0xb7, 0x0a, 0xa7, 0x4d, 0x1b,
            0x7e, 0xbc, 0x9c, 0x98, 0x2c, 0xcf, 0x2e, 0xc4, 0x96, 0x8c, 0xc0, 0xcd, 0x55, 0xf1,
            0x2a, 0xf4, 0x66, 0x0c,
        ],
        edge_nonce: [
            0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d,
            0x8e, 0x8f, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b,
            0x9c, 0x9d, 0x9e, 0x9f,
        ],
    };
    let issuer = RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    };
    ControlSession::new(
        connection,
        DestinationAdmission::new(policy).expect("valid admission policy"),
        vec![issuer],
        TrustProfileId::new("test-profile").expect("trust profile"),
    )
}

async fn connection_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let listen_port = std::env::var("NBSR_WP8_CAPTURE_PORT")
        .ok()
        .map(|value| {
            value
                .parse::<u16>()
                .expect("NBSR_WP8_CAPTURE_PORT must be a nonzero u16")
        })
        .unwrap_or(0);
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("destination policy");
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        identity("destination.edge"),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .expect("source policy");
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).expect("server config"),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), listen_port),
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
    (
        listener,
        source.expect("source connection"),
        destination.expect("destination connection"),
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn accepted_stream_id_four_echoes_only_the_bounded_in_memory_payload() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.expect("source control");
    let mut session = control_session(&destination);

    let client_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .expect("CLIENT_HELLO fixture");
    source_control
        .send_envelope(&client_hello)
        .await
        .expect("send CLIENT_HELLO");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    let received_hello = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive CLIENT_HELLO");
    session
        .accept_client_hello(&received_hello)
        .expect("accept CLIENT_HELLO");

    let edge_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/edge-hello.cbor"),
        CoreV02Limits::default(),
    )
    .expect("EDGE_HELLO fixture");
    destination_control
        .send_envelope(&edge_hello)
        .await
        .expect("send EDGE_HELLO");
    let received_edge_hello = source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive EDGE_HELLO");
    session
        .confirm_edge_hello(&received_edge_hello)
        .expect("confirm EDGE_HELLO");

    let route_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("ROUTE_OPEN fixture");
    source_control
        .send_envelope(&route_open)
        .await
        .expect("send ROUTE_OPEN");
    let received_route_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive ROUTE_OPEN");
    session
        .accept_route_open(&received_route_open)
        .expect("admit received ROUTE_OPEN");
    assert!(!session.has_active_channel(channel().channel_id));

    let route_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("ROUTE_ACCEPT fixture");
    destination_control
        .send_envelope(&route_accept)
        .await
        .expect("send ROUTE_ACCEPT");
    let received_route_accept = source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive ROUTE_ACCEPT");
    session
        .confirm_route_accept(&received_route_accept)
        .expect("confirm admitted ROUTE_ACCEPT");
    let channel_id = channel().channel_id;
    destination
        .bind_channel(&mut session, channel_id)
        .expect("derive live channel binding");

    let stream_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_OPEN fixture");
    let stream_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_ACCEPT fixture");
    source_control
        .send_envelope(&stream_open)
        .await
        .expect("send STREAM_OPEN");
    let received_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_OPEN");
    session
        .authorize_stream_open(channel_id, &received_open)
        .expect("authorize received STREAM_OPEN");
    session
        .confirm_stream_accept(channel_id, &stream_accept)
        .expect("bind matching STREAM_ACCEPT");
    destination_control
        .send_envelope(&stream_accept)
        .await
        .expect("send STREAM_ACCEPT");
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_ACCEPT");

    let payload = vec![0x5a; 1_048_576];
    let mut source_session = control_session(&source);
    source_session.accept_client_hello(&client_hello).unwrap();
    source_session.confirm_edge_hello(&edge_hello).unwrap();
    source_session.accept_route_open(&route_open).unwrap();
    source_session.confirm_route_accept(&route_accept).unwrap();
    source
        .bind_channel(&mut source_session, channel_id)
        .unwrap();
    source_session
        .authorize_stream_open(channel_id, &stream_open)
        .unwrap();
    source_session
        .confirm_stream_accept(channel_id, &stream_accept)
        .unwrap();
    let permit = source_session
        .application_stream_permit(channel_id, 4)
        .expect("confirmed stream permit");
    let (echoed_at_destination, echoed_at_source) = tokio::join!(
        async {
            let mut stream = destination
                .accept_session_stream(&mut session, channel_id)
                .await
                .expect("accept application stream");
            assert_eq!(stream.id(), 4);
            stream.echo_once().await.expect("bounded echo")
        },
        async {
            let mut stream = source
                .open_session_stream(&permit)
                .await
                .expect("open application stream");
            assert_eq!(stream.id(), 4);
            stream
                .send_and_receive(&payload)
                .await
                .expect("receive bounded echo")
        }
    );
    assert_eq!(echoed_at_destination, payload);
    assert_eq!(echoed_at_source, payload);

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn payload_before_stream_accept_is_reset_without_delivery() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.expect("source control");
    let client_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .expect("CLIENT_HELLO fixture");
    source_control
        .send_envelope(&client_hello)
        .await
        .expect("send CLIENT_HELLO");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive CLIENT_HELLO");

    let (rejected, source_result) = tokio::join!(
        async {
            destination
                .reject_next_application_stream()
                .await
                .expect("reset unauthorized stream")
        },
        async {
            let mut stream = source
                .open_control_stream()
                .await
                .expect("open unadmitted stream");
            stream
                .send_envelope(&client_hello)
                .await
                .expect("send early payload");
            stream.receive_envelope(CoreV02Limits::default()).await
        }
    );
    assert_eq!(rejected, 4);
    assert_eq!(source_result, Err(TransportError::ControlStreamFailed));

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn outbound_payload_over_one_mib_is_rejected_before_delivery() {
    let (listener, source, destination) = connection_pair().await;
    let mut session = control_session(&destination);
    session
        .accept_client_hello(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/client-hello.cbor"),
                CoreV02Limits::default(),
            )
            .expect("CLIENT_HELLO fixture"),
        )
        .expect("accept CLIENT_HELLO");
    session
        .confirm_edge_hello(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/edge-hello.cbor"),
                CoreV02Limits::default(),
            )
            .expect("EDGE_HELLO fixture"),
        )
        .expect("confirm EDGE_HELLO");
    session
        .accept_route_open(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/route-open.cbor"),
                CoreV02Limits::default(),
            )
            .expect("ROUTE_OPEN fixture"),
        )
        .expect("accept ROUTE_OPEN");
    session
        .confirm_route_accept(
            &decode_control_envelope(
                &vector("artifacts/valid/envelopes/route-accept.cbor"),
                CoreV02Limits::default(),
            )
            .expect("ROUTE_ACCEPT fixture"),
        )
        .expect("confirm ROUTE_ACCEPT");
    let channel_id = channel().channel_id;
    destination
        .bind_channel(&mut session, channel_id)
        .expect("derive live channel binding");
    let mut source_control = source.open_control_stream().await.expect("source control");
    let stream_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-open.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_OPEN fixture");
    source_control
        .send_envelope(&stream_open)
        .await
        .expect("send STREAM_OPEN");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    let received_open = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_OPEN");
    let stream_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .expect("STREAM_ACCEPT fixture");
    session
        .authorize_stream_open(channel_id, &received_open)
        .expect("authorize received STREAM_OPEN");
    destination_control
        .send_envelope(&stream_accept)
        .await
        .expect("send STREAM_ACCEPT");
    let received_accept = source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .expect("receive STREAM_ACCEPT");
    session
        .confirm_stream_accept(channel_id, &received_accept)
        .expect("bind matching STREAM_ACCEPT");

    let payload = vec![0x5a; 1_048_577];
    let mut source_session = control_session(&source);
    let client_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let edge_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/edge-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let route_open = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-open.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    let route_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/route-accept.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    source_session.accept_client_hello(&client_hello).unwrap();
    source_session.confirm_edge_hello(&edge_hello).unwrap();
    source_session.accept_route_open(&route_open).unwrap();
    source_session.confirm_route_accept(&route_accept).unwrap();
    source
        .bind_channel(&mut source_session, channel_id)
        .unwrap();
    source_session
        .authorize_stream_open(channel_id, &stream_open)
        .unwrap();
    source_session
        .confirm_stream_accept(channel_id, &stream_accept)
        .unwrap();
    let permit = source_session
        .application_stream_permit(channel_id, 4)
        .expect("confirmed stream permit");
    let (destination_result, source_result) = tokio::join!(
        async {
            let mut stream = destination
                .accept_session_stream(&mut session, channel_id)
                .await
                .expect("accept application stream");
            stream.echo_once().await
        },
        async {
            let mut stream = source
                .open_session_stream(&permit)
                .await
                .expect("open application stream");
            stream.send_and_receive(&payload).await
        }
    );
    assert_eq!(destination_result, Ok(Vec::new()));
    assert_eq!(
        source_result,
        Err(TransportError::ApplicationPayloadTooLarge)
    );

    source.close().await.expect("source close");
    destination.close().await.expect("destination close");
    listener.close().await.expect("listener close");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn federated_two_operator_route_transfers_only_after_f75_admission() {
    let (listener, source, destination) = connection_pair().await;
    let mut source_control = source.open_control_stream().await.expect("source control");
    let mut destination_session = federated_control_session(&destination);
    let client_hello = task10_client_hello();
    source_control
        .send_envelope(&client_hello)
        .await
        .expect("send CLIENT_HELLO");
    let mut destination_control = destination
        .accept_control_stream()
        .await
        .expect("destination control");
    destination_session
        .accept_client_hello(
            &destination_control
                .receive_envelope(CoreV02Limits::default())
                .await
                .expect("receive CLIENT_HELLO"),
        )
        .expect("source admission");
    let edge_hello = decode_control_envelope(
        &vector("artifacts/valid/envelopes/edge-hello.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    destination_control
        .send_envelope(&edge_hello)
        .await
        .unwrap();
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .confirm_edge_hello(&edge_hello)
        .expect("transport session");

    let route_open = task10_f75_route_open();
    let attestations = task10_federation_attestations();
    let mut source_session = federated_control_session(&source);
    source_session.accept_client_hello(&client_hello).unwrap();
    source_session.confirm_edge_hello(&edge_hello).unwrap();
    source_session
        .accept_federated_route_open(&route_open, &attestations)
        .expect("source F75 admission before transmission");
    source_control.send_envelope(&route_open).await.unwrap();
    let received = destination_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .accept_federated_route_open(&received, &attestations)
        .expect("destination F75 admission");
    let route_accept = task10_route_accept();
    destination_control
        .send_envelope(&route_accept)
        .await
        .unwrap();
    source_control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .confirm_route_accept(&route_accept)
        .unwrap();
    let channel_id: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    destination
        .bind_channel(&mut destination_session, channel_id)
        .unwrap();

    let stream_open = task10_stream_open();
    let stream_accept = decode_control_envelope(
        &vector("artifacts/valid/envelopes/stream-accept.cbor"),
        CoreV02Limits::default(),
    )
    .unwrap();
    destination_session
        .authorize_stream_open(channel_id, &stream_open)
        .unwrap();
    destination_session
        .confirm_stream_accept(channel_id, &stream_accept)
        .unwrap();

    source_session.confirm_route_accept(&route_accept).unwrap();
    source
        .bind_channel(&mut source_session, channel_id)
        .unwrap();
    source_session
        .authorize_stream_open(channel_id, &stream_open)
        .unwrap();
    source_session
        .confirm_stream_accept(channel_id, &stream_accept)
        .unwrap();
    let permit = source_session
        .application_stream_permit(channel_id, 4)
        .unwrap();
    let payload = b"NBSR-WP8-TASK10-LIVE-v1".to_vec();
    let (at_destination, at_source) = tokio::join!(
        async {
            destination
                .accept_session_stream(&mut destination_session, channel_id)
                .await
                .unwrap()
                .echo_once()
                .await
                .unwrap()
        },
        async {
            source
                .open_session_stream(&permit)
                .await
                .unwrap()
                .send_and_receive(&payload)
                .await
                .unwrap()
        }
    );
    assert_eq!(at_destination, payload);
    assert_eq!(at_source, payload);
    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

fn federated_control_session(
    connection: &nbsr_transport::AuthenticatedConnection,
) -> ControlSession {
    let mut policy = control_session_policy();
    policy.source_operator_id =
        "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r".into();
    policy.destination_operator_id =
        "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg".into();
    ControlSession::new(
        connection,
        DestinationAdmission::new_federated(policy, task10_federation_authorities()).unwrap(),
        vec![route_grant_issuer()],
        TrustProfileId::new("federation-dev-v1").unwrap(),
    )
}

fn control_session_policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "service.example".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: [
                    0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2,
                    0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2,
                    0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                ],
            },
        )]),
        now: 1_893_456_000,
        client_session_public_key: [
            0x3d, 0x40, 0x17, 0xc3, 0xe8, 0x43, 0x89, 0x5a, 0x92, 0xb7, 0x0a, 0xa7, 0x4d, 0x1b,
            0x7e, 0xbc, 0x9c, 0x98, 0x2c, 0xcf, 0x2e, 0xc4, 0x96, 0x8c, 0xc0, 0xcd, 0x55, 0xf1,
            0x2a, 0xf4, 0x66, 0x0c,
        ],
        edge_nonce: (0x80..0xa0).collect::<Vec<_>>().try_into().unwrap(),
    }
}

fn route_grant_issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    }
}

fn task10_federation_attestations() -> LocalFederationAdmissionAttestations {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    LocalFederationAdmissionAttestations {
        source: std::fs::read(root.join("vectors/wp8-local-admission/source.cose")).unwrap(),
        destination: std::fs::read(root.join("vectors/wp8-local-admission/destination.cose"))
            .unwrap(),
    }
}

fn task10_federation_authorities() -> LocalFederationAdmissionAuthorities {
    LocalFederationAdmissionAuthorities::new(
        b"local-source".to_vec(),
        [
            0xf8, 0x0c, 0xcc, 0xdc, 0xe4, 0xae, 0x1c, 0x07, 0xae, 0x20, 0x8a, 0x2a, 0xdf, 0x99,
            0xa3, 0x10, 0xae, 0x42, 0x07, 0xe0, 0x30, 0x6f, 0xa0, 0x23, 0x61, 0x10, 0xb0, 0x68,
            0x27, 0xbb, 0xb8, 0xd0,
        ],
        b"local-destination".to_vec(),
        [
            0xd7, 0x59, 0x79, 0x3b, 0xbc, 0x13, 0xa2, 0x81, 0x9a, 0x82, 0x7c, 0x76, 0xad, 0xb6,
            0xfb, 0xa8, 0xa4, 0x9a, 0xee, 0x00, 0x7f, 0x49, 0xf2, 0xd0, 0x99, 0x2d, 0x99, 0xb8,
            0x25, 0xad, 0x2c, 0x48,
        ],
    )
    .unwrap()
}

fn task10_route_grant_digest() -> [u8; 32] {
    [
        0xf6, 0x09, 0x00, 0x54, 0xa8, 0x32, 0xc5, 0x59, 0xb2, 0x8b, 0xba, 0x38, 0x6f, 0x78, 0x61,
        0x65, 0x57, 0xce, 0x13, 0xaf, 0x39, 0xe1, 0xa9, 0x5d, 0x3d, 0xff, 0x9e, 0x1f, 0x7b, 0xa9,
        0x68, 0x60,
    ]
}

fn task10_client_hello() -> CoreV02Envelope {
    let mut body = Vec::new();
    map_cbor(&mut body, 8);
    field_uint_cbor(&mut body, 0, 1);
    field_text_cbor(
        &mut body,
        1,
        "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r",
    );
    field_text_cbor(&mut body, 2, "source.edge");
    field_text_cbor(
        &mut body,
        3,
        "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg",
    );
    field_text_cbor(&mut body, 4, "destination.edge");
    field_bytes_cbor(&mut body, 5, &(0x60..0x80).collect::<Vec<_>>());
    field_bytes_cbor(
        &mut body,
        6,
        &control_session_policy().client_session_public_key,
    );
    field_uint_cbor(&mut body, 7, 1_893_456_000);
    task10_envelope(
        1,
        (0x00..0x10).collect::<Vec<_>>().try_into().unwrap(),
        1,
        body,
    )
}

fn task10_f75_route_open() -> CoreV02Envelope {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let body = std::fs::read(root.join("vectors/wp8-f75-route-open/route-open-body.cbor")).unwrap();
    task10_envelope(
        3,
        [
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
            0x0e, 0x10,
        ],
        2,
        body,
    )
}

fn task10_route_accept() -> CoreV02Envelope {
    let mut body = Vec::new();
    map_cbor(&mut body, 5);
    field_uint_cbor(&mut body, 0, 1);
    field_bytes_cbor(&mut body, 1, &(0x40..0x50).collect::<Vec<_>>());
    field_bytes_cbor(&mut body, 2, &(0x20..0x30).collect::<Vec<_>>());
    field_bytes_cbor(&mut body, 3, &task10_route_grant_digest());
    field_uint_cbor(&mut body, 4, 1_893_456_000);
    task10_envelope(
        4,
        [
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
            0x0e, 0x10,
        ],
        2,
        body,
    )
}

fn task10_stream_open() -> CoreV02Envelope {
    let mut body = Vec::new();
    map_cbor(&mut body, 7);
    field_uint_cbor(&mut body, 0, 1);
    field_uint_cbor(&mut body, 1, 4);
    field_bytes_cbor(&mut body, 2, &(0x40..0x50).collect::<Vec<_>>());
    field_bytes_cbor(&mut body, 3, &(0x20..0x30).collect::<Vec<_>>());
    field_bytes_cbor(&mut body, 4, &task10_route_grant_digest());
    field_text_cbor(&mut body, 5, "tcp");
    field_uint_cbor(&mut body, 6, 8443);
    task10_envelope(
        6,
        [
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
            0x0e, 0x11,
        ],
        3,
        body,
    )
}

fn task10_envelope(
    message: u64,
    request: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> CoreV02Envelope {
    let mut wire = Vec::new();
    map_cbor(&mut wire, 6);
    field_uint_cbor(&mut wire, 0, 2);
    field_uint_cbor(&mut wire, 1, message);
    field_bytes_cbor(&mut wire, 2, &request);
    field_bytes_cbor(&mut wire, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint_cbor(&mut wire, 4, sequence);
    uint_cbor(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, CoreV02Limits::default()).unwrap()
}

fn field_uint_cbor(target: &mut Vec<u8>, key: u64, value: u64) {
    uint_cbor(target, key);
    uint_cbor(target, value);
}
fn field_bytes_cbor(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint_cbor(target, key);
    argument_cbor(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}
fn field_text_cbor(target: &mut Vec<u8>, key: u64, value: &str) {
    uint_cbor(target, key);
    argument_cbor(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}
fn uint_cbor(target: &mut Vec<u8>, value: u64) {
    argument_cbor(target, 0, value);
}
fn map_cbor(target: &mut Vec<u8>, value: u64) {
    argument_cbor(target, 5, value);
}
fn argument_cbor(target: &mut Vec<u8>, major: u8, value: u64) {
    let initial = major << 5;
    match value {
        0..=23 => target.push(initial | value as u8),
        24..=0xff => target.extend_from_slice(&[initial | 24, value as u8]),
        0x100..=0xffff => {
            target.push(initial | 25);
            target.extend_from_slice(&(value as u16).to_be_bytes());
        }
        0x1_0000..=0xffff_ffff => {
            target.push(initial | 26);
            target.extend_from_slice(&(value as u32).to_be_bytes());
        }
        _ => {
            target.push(initial | 27);
            target.extend_from_slice(&value.to_be_bytes());
        }
    }
}
