use std::collections::BTreeMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use ed25519_dalek::{Signer, SigningKey};
use nbsr_transport::{
    AdmissionPolicy, AdmissionReject, AuditAction, AuditOutcome, AuditReason,
    AuthorizedServicePolicy, DatagramFrame, DatagramReceive, DatagramReject, DestinationAdmission,
    EdgeIdentity, EdgeRole, MAX_DATAGRAM_PAYLOAD, PeerPolicy, RouteGrantClaims, RouteGrantIssuer,
    RouteOpenRequest, TransportListener, TrustProfileId, build_client_config, build_server_config,
    connect, decode_control_envelope, decode_datagram_frame, encode_datagram_frame,
    max_datagram_payload,
};
use sha2::{Digest, Sha256};
use tokio::time::timeout;

mod support;

const CHANNEL: [u8; 16] = [0x11; 16];
const NOW: u64 = 1_893_456_000;
const SESSION_ID: [u8; 16] = [
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f,
];
const EDGE_NONCE: [u8; 32] = [
    0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f,
    0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f,
];
const ROUTE_GRANT_SEED: [u8; 32] = [0x5a; 32];
const SESSION_SEED: [u8; 32] = [
    0x4c, 0xcd, 0x08, 0x9b, 0x28, 0xff, 0x96, 0xda, 0x9d, 0xb6, 0xc3, 0x46, 0xec, 0x11, 0x4e, 0x0f,
    0x5b, 0x8a, 0x31, 0x9f, 0x35, 0xab, 0xa6, 0x24, 0xda, 0x8c, 0xf6, 0xed, 0x4f, 0xb8, 0xa6, 0xfb,
];
const KID: &[u8] = b"nbsr-task9-route-grant";

#[test]
fn empty_payload_has_the_exact_preferred_core_v02_udp_encoding() {
    let expected = [
        0xa4, 0x00, 0x01, 0x01, 0x50, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
        0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x02, 0x01, 0x03, 0x40,
    ];

    let encoded = encode_datagram_frame(CHANNEL, 1, &[], expected.len())
        .expect("an exact-sized peer limit permits the complete empty frame");
    assert_eq!(encoded, expected);
    assert_eq!(
        decode_datagram_frame(&expected, expected.len()),
        Ok(DatagramFrame::new(CHANNEL, 1, Vec::new()).expect("valid frame fields"))
    );
    assert_eq!(max_datagram_payload(expected.len(), CHANNEL, 1), Some(0));
    assert_eq!(
        encode_datagram_frame(CHANNEL, 1, &[], expected.len() - 1),
        Err(DatagramReject::PeerMaximum)
    );
}

#[test]
fn codec_rejects_every_non_profile_shape_without_exposing_payload() {
    let valid = encode_datagram_frame(CHANNEL, 1, b"private-marker", 1_500).unwrap();
    let mut invalid = Vec::new();

    let mut unknown_key = valid.clone();
    unknown_key[23] = 0x04;
    invalid.push(unknown_key);

    let mut zero_channel = valid.clone();
    zero_channel[5..21].fill(0);
    invalid.push(zero_channel);

    let prefix = &valid[..22];
    let payload_field = &valid[23..];
    for sequence in [
        vec![0x00],
        vec![0x18, 0x01],
        vec![0xf5],
        vec![0xc0, 0x01],
        vec![0xf9, 0x00, 0x00],
        vec![0x9f, 0x01, 0xff],
    ] {
        let mut wire = prefix.to_vec();
        wire.extend_from_slice(&sequence);
        wire.extend_from_slice(payload_field);
        invalid.push(wire);
    }

    let mut wrong_channel_type = valid.clone();
    wrong_channel_type[4] = 0x70;
    invalid.push(wrong_channel_type);

    let mut wrong_channel_length = valid.clone();
    wrong_channel_length[4] = 0x4f;
    invalid.push(wrong_channel_length);

    let mut wrong_payload_type = valid.clone();
    wrong_payload_type[24] = 0x6e;
    invalid.push(wrong_payload_type);

    let mut non_preferred_payload_length = valid.clone();
    non_preferred_payload_length.splice(24..25, [0x58, 0x0e]);
    invalid.push(non_preferred_payload_length);

    let mut trailing = valid.clone();
    trailing.push(0);
    invalid.push(trailing);

    let mut missing_key = valid.clone();
    missing_key[0] = 0xa3;
    invalid.push(missing_key);

    let mut duplicate_key = valid.clone();
    duplicate_key[21] = 0x01;
    invalid.push(duplicate_key);

    for wire in invalid {
        assert_eq!(
            decode_datagram_frame(&wire, 1_500),
            Err(DatagramReject::InvalidFrame),
            "mutation should be rejected"
        );
    }

    let debug = format!(
        "{:?}",
        DatagramFrame::new(CHANNEL, 1, b"private-marker".to_vec()).unwrap()
    );
    assert!(!debug.contains("private-marker"));
}

#[test]
fn payload_and_peer_caps_use_the_exact_encoded_size() {
    let payload = vec![0x5a; MAX_DATAGRAM_PAYLOAD];
    let encoded = encode_datagram_frame(CHANNEL, 1, &payload, 1_227).unwrap();
    assert_eq!(encoded.len(), 1_227);
    assert_eq!(
        decode_datagram_frame(&encoded, 1_227).unwrap().payload(),
        payload
    );
    assert_eq!(max_datagram_payload(1_227, CHANNEL, 1), Some(1_200));
    assert_eq!(max_datagram_payload(49, CHANNEL, 1), Some(23));
    assert_eq!(max_datagram_payload(24, CHANNEL, 1), None);
    assert_eq!(
        encode_datagram_frame(CHANNEL, 1, &vec![0; 1_201], usize::MAX),
        Err(DatagramReject::PayloadTooLarge)
    );
    assert_eq!(
        encode_datagram_frame(CHANNEL, 1, &[0; 24], 49),
        Err(DatagramReject::PeerMaximum)
    );
    assert_eq!(
        decode_datagram_frame(&encoded, encoded.len() - 1),
        Err(DatagramReject::PeerMaximum)
    );
}

#[test]
fn udp_admission_requires_udp_in_the_grants_allowed_transports() {
    let mut admission = DestinationAdmission::new(datagram_policy()).unwrap();
    let mut denied = datagram_request([0x31; 16], [0x41; 16], vec!["tcp".into()], "udp");
    assert_eq!(
        admission.admit(denied.clone()),
        Err(AdmissionReject::RouteDenied)
    );
    assert_eq!(admission.candidate_channels(), 0);

    denied.grant.allowed_transports.push("udp".into());
    let udp = admission
        .admit(denied)
        .expect("grant explicitly permits UDP");
    assert_eq!(udp.transport, "udp");

    let tcp = admission
        .admit(datagram_request(
            [0x32; 16],
            [0x42; 16],
            vec!["tcp".into()],
            "tcp",
        ))
        .expect("existing TCP admission remains valid");
    assert_eq!(tcp.transport, "tcp");
}

fn datagram_policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "udp.service".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 7,
                policy_hash: [0x77; 32],
            },
        )]),
        now: NOW,
        client_session_public_key: [0x88; 32],
        edge_nonce: [0x99; 32],
    }
}

fn datagram_request(
    channel_id: [u8; 16],
    unique_nonce: [u8; 16],
    allowed_transports: Vec<String>,
    requested_transport: &str,
) -> RouteOpenRequest {
    RouteOpenRequest {
        channel_id,
        grant: RouteGrantClaims {
            route_id: [0x21; 16],
            service_id: "udp.service".into(),
            source_operator_id: "source.operator".into(),
            source_edge_id: "source.edge".into(),
            destination_operator_id: "destination.operator".into(),
            destination_edge_ids: vec!["destination.edge".into()],
            allowed_transports,
            allowed_ports: vec![53],
            client_session_key_thumbprint: [0x88; 32],
            not_before: NOW - 60,
            expires_at: NOW + 300,
            record_sequence: 7,
            policy_hash: [0x77; 32],
            unique_nonce,
        },
        requested_transport: requested_transport.into(),
        requested_port: 53,
        opened_at: NOW,
        route_grant_digest: [0x66; 32],
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn native_quinn_loopback_isolates_two_udp_channels_and_a_tcp_sibling() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (listener, source, destination) = datagram_connection_pair(&pki).await;
    let issuer = RouteGrantIssuer {
        kid: KID.to_vec(),
        public_key: SigningKey::from_bytes(&ROUTE_GRANT_SEED)
            .verifying_key()
            .to_bytes(),
    };
    let mut source_session = loopback_session(&source, issuer.clone());
    let mut destination_session = loopback_session(&destination, issuer);
    establish_loopback_session(&mut source_session);
    establish_loopback_session(&mut destination_session);

    let (denied_udp_open, _) = signed_loopback_route_with_allowed_transport(
        9,
        "udp-a",
        41,
        [0xa1; 32],
        RouteTransports {
            requested: "udp",
            allowed: "tcp",
        },
        5301,
        2,
    );
    assert_eq!(
        source_session.accept_route_open(&denied_udp_open),
        Err(nbsr_transport::SessionReject::Admission(
            AdmissionReject::RouteDenied
        ))
    );
    assert_eq!(source_session.candidate_channels(), 0);

    let (udp_a_open, udp_a_accept) =
        signed_loopback_route(1, "udp-a", 41, [0xa1; 32], "udp", 5301, 2);
    let (udp_b_open, udp_b_accept) =
        signed_loopback_route(2, "udp-b", 42, [0xb2; 32], "udp", 5302, 3);
    let (tcp_open, tcp_accept) = signed_loopback_route(3, "tcp-c", 43, [0xc3; 32], "tcp", 8443, 4);
    let mut channels = Vec::new();
    for (open, accept) in [
        (&udp_a_open, &udp_a_accept),
        (&udp_b_open, &udp_b_accept),
        (&tcp_open, &tcp_accept),
    ] {
        let source_channel = source_session.accept_route_open(open).unwrap();
        let destination_channel = destination_session.accept_route_open(open).unwrap();
        assert_eq!(source_channel, destination_channel);
        source_session.confirm_route_accept(accept).unwrap();
        destination_session.confirm_route_accept(accept).unwrap();
        source
            .bind_channel(&mut source_session, source_channel.channel_id)
            .unwrap();
        destination
            .bind_channel(&mut destination_session, destination_channel.channel_id)
            .unwrap();
        channels.push(source_channel);
    }
    let udp_a = &channels[0];
    let udp_b = &channels[1];
    let tcp = &channels[2];

    let cap = source
        .udp_payload_capacity(&source_session, udp_a.channel_id)
        .expect("negotiated DATAGRAM capacity");
    assert!(cap <= MAX_DATAGRAM_PAYLOAD);
    let cap_payload = vec![0x5a; cap];
    source
        .send_udp_datagram(&mut source_session, udp_a.channel_id, &cap_payload, 0)
        .expect("exact computed payload cap");
    let expected_cap_reject = if cap == MAX_DATAGRAM_PAYLOAD {
        DatagramReject::PayloadTooLarge
    } else {
        DatagramReject::PeerMaximum
    };
    assert_eq!(
        source.send_udp_datagram(
            &mut source_session,
            udp_a.channel_id,
            &vec![0x5a; cap + 1],
            0,
        ),
        Err(expected_cap_reject)
    );
    timeout(
        Duration::from_secs(2),
        destination.receive_udp_datagram(&mut destination_session, 0),
    )
    .await
    .expect("bounded loopback receive timeout")
    .expect("complete native QUIC DATAGRAM");
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_a.channel_id)
            .unwrap(),
        Some(cap_payload)
    );

    source
        .send_udp_datagram(&mut source_session, udp_a.channel_id, b"alpha", 0)
        .unwrap();
    source
        .send_udp_datagram(&mut source_session, udp_b.channel_id, b"bravo", 0)
        .unwrap();
    for _ in 0..2 {
        timeout(
            Duration::from_secs(2),
            destination.receive_udp_datagram(&mut destination_session, 0),
        )
        .await
        .expect("bounded loopback receive timeout")
        .unwrap();
    }
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_a.channel_id)
            .unwrap(),
        Some(b"alpha".to_vec())
    );
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_b.channel_id)
            .unwrap(),
        Some(b"bravo".to_vec())
    );

    while source_session.pop_audit_event().is_some() {}
    while destination_session.pop_audit_event().is_some() {}
    for sequence in 0..65_u8 {
        source
            .send_udp_datagram(&mut source_session, udp_a.channel_id, &[sequence], 0)
            .unwrap();
        while source_session.pop_audit_event().is_some() {}
    }
    let mut quota_audit = None;
    for _ in 0..65 {
        let outcome = timeout(
            Duration::from_secs(2),
            destination.receive_udp_datagram(&mut destination_session, 0),
        )
        .await
        .expect("bounded loopback receive timeout")
        .unwrap();
        if outcome == DatagramReceive::DroppedQueueFull {
            quota_audit = destination_session
                .audit_events()
                .filter(|event| event.action == AuditAction::DatagramDropped)
                .last()
                .cloned();
        }
        while destination_session.pop_audit_event().is_some() {}
    }
    let quota_audit = quota_audit.expect("typed queue quota audit");
    assert_eq!(quota_audit.channel_id, Some(udp_a.channel_id));
    assert_eq!(quota_audit.service_id.as_str(), "udp-a");
    assert_eq!(quota_audit.outcome, AuditOutcome::Denied);
    assert_eq!(quota_audit.reason, AuditReason::DatagramQueueFull);
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_b.channel_id)
            .unwrap(),
        None
    );

    let revoke_a = route_revoke_control(udp_a, [0xe1; 16], 5);
    destination
        .accept_route_revoke(&mut destination_session, udp_a.channel_id, &revoke_a)
        .unwrap();
    assert_eq!(
        destination.pop_udp_datagram(&mut destination_session, udp_a.channel_id),
        Err(DatagramReject::InvalidState)
    );

    source
        .send_udp_datagram(&mut source_session, udp_b.channel_id, b"survives", 10)
        .unwrap();
    timeout(
        Duration::from_secs(2),
        destination.receive_udp_datagram(&mut destination_session, 10),
    )
    .await
    .expect("bounded sibling receive timeout")
    .unwrap();
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_b.channel_id)
            .unwrap(),
        Some(b"survives".to_vec())
    );

    let mut source_control = source.open_control_stream().await.unwrap();
    let tcp_open = stream_control(tcp, 4, 6, 10);
    source_control.send_envelope(&tcp_open).await.unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    let received_open = destination_control
        .receive_envelope(nbsr_transport::CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .authorize_stream_open(tcp.channel_id, &received_open)
        .unwrap();
    let tcp_accept = stream_control(tcp, 4, 7, 10);
    destination_control
        .send_envelope(&tcp_accept)
        .await
        .unwrap();
    let received_accept = source_control
        .receive_envelope(nbsr_transport::CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .confirm_stream_accept(tcp.channel_id, &received_accept)
        .unwrap();
    let (echoed, received) = tokio::join!(
        async {
            let mut stream = destination
                .accept_session_stream(&mut destination_session, tcp.channel_id)
                .await
                .unwrap();
            stream.echo_once().await.unwrap()
        },
        async {
            source
                .open_application_stream()
                .await
                .unwrap()
                .send_and_receive(b"tcp-sibling")
                .await
                .unwrap()
        }
    );
    assert_eq!(echoed, b"tcp-sibling");
    assert_eq!(received, b"tcp-sibling");

    source_session.begin_session_drain(100, NOW, 5).unwrap();
    assert_eq!(
        source.send_udp_datagram(&mut source_session, udp_b.channel_id, b"draining", 100,),
        Err(DatagramReject::InvalidState)
    );

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn channel_a_audit_exhaustion_preserves_udp_b_tcp_c_and_session_lifecycle() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (listener, source, destination) = datagram_connection_pair(&pki).await;
    let issuer = RouteGrantIssuer {
        kid: KID.to_vec(),
        public_key: SigningKey::from_bytes(&ROUTE_GRANT_SEED)
            .verifying_key()
            .to_bytes(),
    };
    let mut source_session = loopback_session(&source, issuer.clone());
    let mut destination_session = loopback_session(&destination, issuer);
    establish_loopback_session(&mut source_session);
    establish_loopback_session(&mut destination_session);

    let (udp_a_open, udp_a_accept) =
        signed_loopback_route(11, "udp-a", 41, [0xa1; 32], "udp", 5301, 2);
    let (udp_b_open, udp_b_accept) =
        signed_loopback_route(12, "udp-b", 42, [0xb2; 32], "udp", 5302, 3);
    let (tcp_open, tcp_accept) = signed_loopback_route(13, "tcp-c", 43, [0xc3; 32], "tcp", 8443, 4);
    let mut channels = Vec::new();
    for (open, accept) in [
        (&udp_a_open, &udp_a_accept),
        (&udp_b_open, &udp_b_accept),
        (&tcp_open, &tcp_accept),
    ] {
        let source_channel = source_session.accept_route_open(open).unwrap();
        let destination_channel = destination_session.accept_route_open(open).unwrap();
        assert_eq!(source_channel, destination_channel);
        source_session.confirm_route_accept(accept).unwrap();
        destination_session.confirm_route_accept(accept).unwrap();
        source
            .bind_channel(&mut source_session, source_channel.channel_id)
            .unwrap();
        destination
            .bind_channel(&mut destination_session, destination_channel.channel_id)
            .unwrap();
        channels.push(source_channel);
    }
    let udp_a = &channels[0];
    let udp_b = &channels[1];
    let tcp = &channels[2];

    while source_session.pop_audit_event().is_some() {}
    while destination_session.pop_audit_event().is_some() {}
    for _ in 0..1_024 {
        assert_eq!(
            source.send_udp_datagram(
                &mut source_session,
                udp_a.channel_id,
                &[0x5a; MAX_DATAGRAM_PAYLOAD + 1],
                0,
            ),
            Err(DatagramReject::PayloadTooLarge)
        );
    }
    assert_eq!(
        source_session
            .audit_events()
            .filter(|event| event.channel_id == Some(udp_a.channel_id))
            .count(),
        1_024
    );
    assert_eq!(
        source.send_udp_datagram(&mut source_session, udp_a.channel_id, b"blocked-a", 0),
        Err(DatagramReject::AuditUnavailable)
    );
    assert_eq!(source_session.audit_events().len(), 1_024);

    assert_eq!(
        source.send_udp_datagram(&mut source_session, udp_b.channel_id, b"udp-b-survives", 0),
        Err(DatagramReject::AuditUnavailable)
    );
    source_session
        .pop_audit_event()
        .expect("one global audit slot is released");

    source
        .send_udp_datagram(&mut source_session, udp_b.channel_id, b"udp-b-survives", 0)
        .unwrap();
    timeout(
        Duration::from_secs(2),
        destination.receive_udp_datagram(&mut destination_session, 0),
    )
    .await
    .expect("bounded sibling receive timeout")
    .unwrap();
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_b.channel_id)
            .unwrap(),
        Some(b"udp-b-survives".to_vec())
    );

    let mut source_control = source.open_control_stream().await.unwrap();
    source_control
        .send_envelope(&stream_control(tcp, 4, 6, 10))
        .await
        .unwrap();
    let mut destination_control = destination.accept_control_stream().await.unwrap();
    let received_open = destination_control
        .receive_envelope(nbsr_transport::CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .authorize_stream_open(tcp.channel_id, &received_open)
        .unwrap();
    destination_control
        .send_envelope(&stream_control(tcp, 4, 7, 10))
        .await
        .unwrap();
    let received_accept = source_control
        .receive_envelope(nbsr_transport::CoreV02Limits::default())
        .await
        .unwrap();
    destination_session
        .confirm_stream_accept(tcp.channel_id, &received_accept)
        .unwrap();
    let (echoed, received) = tokio::join!(
        async {
            destination
                .accept_session_stream(&mut destination_session, tcp.channel_id)
                .await
                .unwrap()
                .echo_once()
                .await
                .unwrap()
        },
        async {
            source
                .open_application_stream()
                .await
                .unwrap()
                .send_and_receive(b"tcp-c-survives")
                .await
                .unwrap()
        }
    );
    assert_eq!(echoed, b"tcp-c-survives");
    assert_eq!(received, b"tcp-c-survives");
    assert_eq!(
        source_session
            .audit_events()
            .filter(|event| event.channel_id == Some(udp_a.channel_id))
            .count(),
        1_023
    );

    while source_session.pop_audit_event().is_some() {}
    source
        .send_udp_datagram(&mut source_session, udp_a.channel_id, b"a-after-release", 0)
        .expect("failed reservation did not mutate the target gate");
    timeout(
        Duration::from_secs(2),
        destination.receive_udp_datagram(&mut destination_session, 0),
    )
    .await
    .expect("bounded target receive timeout")
    .unwrap();
    assert_eq!(
        destination
            .pop_udp_datagram(&mut destination_session, udp_a.channel_id)
            .unwrap(),
        Some(b"a-after-release".to_vec())
    );

    source_session.begin_session_drain(100, NOW, 5).unwrap();
    let session_event = source_session.audit_events().last().unwrap();
    assert_eq!(session_event.channel_id, None);
    assert_eq!(session_event.action, AuditAction::SessionDrainStarted);

    source.close().await.unwrap();
    destination.close().await.unwrap();
    listener.close().await.unwrap();
}

fn loopback_session(
    connection: &nbsr_transport::AuthenticatedConnection,
    issuer: RouteGrantIssuer,
) -> nbsr_transport::ControlSession {
    nbsr_transport::ControlSession::new(
        connection,
        DestinationAdmission::new(loopback_policy()).unwrap(),
        vec![issuer],
        TrustProfileId::new("task9-loopback").unwrap(),
    )
}

fn loopback_policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "source.operator".into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "destination.operator".into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([
            (
                "udp-a".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 41,
                    policy_hash: [0xa1; 32],
                },
            ),
            (
                "udp-b".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: [0xb2; 32],
                },
            ),
            (
                "tcp-c".into(),
                AuthorizedServicePolicy {
                    accepted_record_sequence: 43,
                    policy_hash: [0xc3; 32],
                },
            ),
        ]),
        now: NOW,
        client_session_public_key: SigningKey::from_bytes(&SESSION_SEED)
            .verifying_key()
            .to_bytes(),
        edge_nonce: EDGE_NONCE,
    }
}

fn establish_loopback_session(session: &mut nbsr_transport::ControlSession) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    for relative in [
        "artifacts/valid/envelopes/client-hello.cbor",
        "artifacts/valid/envelopes/edge-hello.cbor",
    ] {
        let wire = std::fs::read(root.join("vectors/core-v0.2").join(relative)).unwrap();
        let envelope =
            decode_control_envelope(&wire, nbsr_transport::CoreV02Limits::default()).unwrap();
        if relative.contains("client") {
            session.accept_client_hello(&envelope).unwrap();
        } else {
            session.confirm_edge_hello(&envelope).unwrap();
        }
    }
}

async fn datagram_connection_pair(
    pki: &support::TestPki,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let destination_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        EdgeIdentity::from_dns_name("source.edge").unwrap(),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let source_policy = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Destination,
        EdgeIdentity::from_dns_name("destination.edge").unwrap(),
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap();
    let listener = TransportListener::bind(
        build_server_config(destination_policy, pki.destination_material()).unwrap(),
        SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
    )
    .unwrap();
    let remote = listener.local_addr().unwrap();
    let (destination, source) = tokio::join!(
        listener.accept_one(),
        connect(
            build_client_config(source_policy, pki.source_material()).unwrap(),
            remote
        )
    );
    (listener, source.unwrap(), destination.unwrap())
}

fn signed_loopback_route(
    id: u8,
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
    transport: &str,
    port: u16,
    sequence: u64,
) -> (
    nbsr_transport::CoreV02Envelope,
    nbsr_transport::CoreV02Envelope,
) {
    signed_loopback_route_with_allowed_transport(
        id,
        service_id,
        record_sequence,
        policy_hash,
        RouteTransports {
            requested: transport,
            allowed: transport,
        },
        port,
        sequence,
    )
}

#[derive(Clone, Copy)]
struct RouteTransports<'a> {
    requested: &'a str,
    allowed: &'a str,
}

fn signed_loopback_route_with_allowed_transport(
    id: u8,
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
    transports: RouteTransports<'_>,
    port: u16,
    sequence: u64,
) -> (
    nbsr_transport::CoreV02Envelope,
    nbsr_transport::CoreV02Envelope,
) {
    let request_id = [id.wrapping_add(0x20); 16];
    let channel_id = [id; 16];
    let route_id = [id.wrapping_add(0x40); 16];
    let grant_wire = signed_loopback_grant(
        route_id,
        [id.wrapping_add(0x80); 16],
        service_id,
        record_sequence,
        policy_hash,
        transports.allowed,
        port,
    );
    let grant_digest: [u8; 32] = Sha256::digest(&grant_wire).into();
    let proof = SigningKey::from_bytes(&SESSION_SEED).sign(&route_transcript(
        request_id,
        channel_id,
        route_id,
        service_id,
        transports.requested,
        port,
        grant_digest,
    ));
    let mut open = Vec::new();
    map(&mut open, 8);
    field_uint(&mut open, 0, 1);
    field_bytes(&mut open, 1, &channel_id);
    field_bytes(&mut open, 2, &grant_wire);
    field_bytes(&mut open, 3, &EDGE_NONCE);
    field_text(&mut open, 4, transports.requested);
    field_uint(&mut open, 5, u64::from(port));
    field_uint(&mut open, 6, NOW);
    field_bytes(&mut open, 7, &proof.to_bytes());
    let mut accept = Vec::new();
    map(&mut accept, 5);
    field_uint(&mut accept, 0, 1);
    field_bytes(&mut accept, 1, &channel_id);
    field_bytes(&mut accept, 2, &route_id);
    field_bytes(&mut accept, 3, &grant_digest);
    field_uint(&mut accept, 4, NOW);
    (
        control_envelope(3, request_id, sequence, open),
        control_envelope(4, request_id, sequence, accept),
    )
}

fn route_revoke_control(
    channel: &nbsr_transport::ActiveChannel,
    request_id: [u8; 16],
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &channel.channel_id);
    field_bytes(&mut body, 2, &channel.route_id);
    field_bytes(&mut body, 3, &channel.route_grant_digest);
    field_uint(&mut body, 4, NOW);
    control_envelope(13, request_id, sequence, body)
}

fn signed_loopback_grant(
    route_id: [u8; 16],
    unique_nonce: [u8; 16],
    service_id: &str,
    record_sequence: u64,
    policy_hash: [u8; 32],
    transport: &str,
    port: u16,
) -> Vec<u8> {
    let thumbprint: [u8; 32] = Sha256::digest(
        SigningKey::from_bytes(&SESSION_SEED)
            .verifying_key()
            .to_bytes(),
    )
    .into();
    let mut payload = Vec::new();
    map(&mut payload, 17);
    field_uint(&mut payload, 0, 1);
    field_bytes(&mut payload, 1, &route_id);
    field_bytes(&mut payload, 2, &[0x11; 32]);
    field_text(&mut payload, 3, service_id);
    field_text(&mut payload, 4, "source.operator");
    field_text(&mut payload, 5, "source.edge");
    field_text(&mut payload, 6, "destination.operator");
    uint(&mut payload, 7);
    array(&mut payload, 1);
    text(&mut payload, "destination.edge");
    uint(&mut payload, 8);
    array(&mut payload, 1);
    text(&mut payload, transport);
    uint(&mut payload, 9);
    array(&mut payload, 1);
    uint(&mut payload, u64::from(port));
    field_bytes(&mut payload, 10, &thumbprint);
    field_uint(&mut payload, 11, NOW - 60);
    field_uint(&mut payload, 12, NOW + 300);
    field_bytes(&mut payload, 13, &[0x33; 16]);
    field_uint(&mut payload, 14, record_sequence);
    field_bytes(&mut payload, 15, &policy_hash);
    field_bytes(&mut payload, 16, &unique_nonce);
    let mut protected = Vec::new();
    map(&mut protected, 2);
    uint(&mut protected, 1);
    nint(&mut protected, -8);
    field_bytes(&mut protected, 4, KID);
    let mut structure = Vec::new();
    array(&mut structure, 4);
    text(&mut structure, "Signature1");
    bytes(&mut structure, &protected);
    bytes(&mut structure, &[]);
    bytes(&mut structure, &payload);
    let signature = SigningKey::from_bytes(&ROUTE_GRANT_SEED).sign(&structure);
    let mut wire = vec![0xd2];
    array(&mut wire, 4);
    bytes(&mut wire, &protected);
    map(&mut wire, 0);
    bytes(&mut wire, &payload);
    bytes(&mut wire, &signature.to_bytes());
    wire
}

fn route_transcript(
    request_id: [u8; 16],
    channel_id: [u8; 16],
    route_id: [u8; 16],
    service_id: &str,
    transport: &str,
    port: u16,
    grant_digest: [u8; 32],
) -> Vec<u8> {
    let mut wire = Vec::new();
    array(&mut wire, 13);
    text(&mut wire, "NBSR-ROUTE-OPEN-v2");
    uint(&mut wire, 2);
    bytes(&mut wire, &SESSION_ID);
    bytes(&mut wire, &request_id);
    bytes(&mut wire, &channel_id);
    bytes(&mut wire, &route_id);
    text(&mut wire, service_id);
    text(&mut wire, "destination.edge");
    bytes(&mut wire, &EDGE_NONCE);
    text(&mut wire, transport);
    uint(&mut wire, u64::from(port));
    bytes(&mut wire, &grant_digest);
    uint(&mut wire, NOW);
    wire
}

fn stream_control(
    channel: &nbsr_transport::ActiveChannel,
    stream_id: u64,
    message_type: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    if message_type == 6 {
        map(&mut body, 7);
        field_uint(&mut body, 0, 1);
        field_uint(&mut body, 1, stream_id);
        field_bytes(&mut body, 2, &channel.channel_id);
        field_bytes(&mut body, 3, &channel.route_id);
        field_bytes(&mut body, 4, &channel.route_grant_digest);
        field_text(&mut body, 5, "tcp");
        field_uint(&mut body, 6, u64::from(channel.port));
    } else {
        map(&mut body, 5);
        field_uint(&mut body, 0, 1);
        field_uint(&mut body, 1, stream_id);
        field_bytes(&mut body, 2, &channel.channel_id);
        field_bytes(&mut body, 3, &channel.route_id);
        field_uint(&mut body, 4, NOW);
    }
    control_envelope(message_type, [stream_id as u8; 16], sequence, body)
}

fn control_envelope(
    message_type: u64,
    request_id: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> nbsr_transport::CoreV02Envelope {
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message_type);
    field_bytes(&mut wire, 2, &request_id);
    field_bytes(&mut wire, 3, &SESSION_ID);
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend_from_slice(&body);
    decode_control_envelope(&wire, nbsr_transport::CoreV02Limits::default()).unwrap()
}

fn field_uint(target: &mut Vec<u8>, key: u64, value: u64) {
    uint(target, key);
    uint(target, value);
}

fn field_bytes(target: &mut Vec<u8>, key: u64, value: &[u8]) {
    uint(target, key);
    bytes(target, value);
}

fn field_text(target: &mut Vec<u8>, key: u64, value: &str) {
    uint(target, key);
    text(target, value);
}

fn uint(target: &mut Vec<u8>, value: u64) {
    argument(target, 0, value);
}

fn nint(target: &mut Vec<u8>, value: i64) {
    argument(target, 1, (-1 - value) as u64);
}

fn bytes(target: &mut Vec<u8>, value: &[u8]) {
    argument(target, 2, value.len() as u64);
    target.extend_from_slice(value);
}

fn text(target: &mut Vec<u8>, value: &str) {
    argument(target, 3, value.len() as u64);
    target.extend_from_slice(value.as_bytes());
}

fn array(target: &mut Vec<u8>, len: u64) {
    argument(target, 4, len);
}

fn map(target: &mut Vec<u8>, len: u64) {
    argument(target, 5, len);
}

fn argument(target: &mut Vec<u8>, major: u8, value: u64) {
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
