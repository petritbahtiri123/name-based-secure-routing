use nbsr_transport::{
    ServiceChannelContext, ServiceChannelExporterError, canonical_service_channel_context,
    derive_service_channel_exporter_fixture,
};
use sha2::{Digest, Sha256};

fn tcp_context<'a>(service_id: &'a str) -> ServiceChannelContext<'a> {
    ServiceChannelContext {
        session_id: [
            0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd,
            0xee, 0xff,
        ],
        source_edge_id: "edge.source.alpha",
        destination_edge_id: "edge.destination.beta",
        channel_id: [
            0x10, 0x21, 0x32, 0x43, 0x54, 0x65, 0x76, 0x87, 0x98, 0xa9, 0xba, 0xcb, 0xdc, 0xed,
            0xfe, 0x0f,
        ],
        route_id: [
            0xff, 0xee, 0xdd, 0xcc, 0xbb, 0xaa, 0x99, 0x88, 0x77, 0x66, 0x55, 0x44, 0x33, 0x22,
            0x11, 0x00,
        ],
        route_grant_digest: [0x00; 32],
        service_id,
        transport: "tcp",
        port: 443,
        policy_hash: [0x11; 32],
        client_nonce: [0x22; 32],
        edge_nonce: [0x33; 32],
    }
}

fn udp_context() -> ServiceChannelContext<'static> {
    ServiceChannelContext {
        session_id: [
            0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10, 0x01, 0x23, 0x45, 0x67, 0x89, 0xab,
            0xcd, 0xef,
        ],
        source_edge_id: "edge.source.gamma",
        destination_edge_id: "edge.destination.delta",
        channel_id: [
            0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55,
            0x66, 0x77,
        ],
        route_id: [
            0x77, 0x66, 0x55, 0x44, 0x33, 0x22, 0x11, 0x00, 0xff, 0xee, 0xdd, 0xcc, 0xbb, 0xaa,
            0x99, 0x88,
        ],
        route_grant_digest: [0x44; 32],
        service_id: "service.example.dns",
        transport: "udp",
        port: 5353,
        policy_hash: [0x55; 32],
        client_nonce: [0x66; 32],
        edge_nonce: [0x77; 32],
    }
}

#[test]
fn checked_in_vectors_match_canonical_context_and_exporter_derivation() {
    let vectors = [
        (
            tcp_context("service.example.web"),
            &include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/context.cbor"
            ))[..],
            include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/context-hash.bin"
            )),
            include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/exporter-master-secret.bin"
            )),
            include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/exporter-value.bin"
            )),
        ),
        (
            udp_context(),
            &include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-udp-02/context.cbor"
            ))[..],
            include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-udp-02/context-hash.bin"
            )),
            include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-udp-02/exporter-master-secret.bin"
            )),
            include_bytes!(concat!(
                "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-udp-02/exporter-value.bin"
            )),
        ),
    ];

    for (context, expected_cbor, expected_hash, master_secret, expected_exporter) in vectors {
        let canonical = canonical_service_channel_context(&context).expect("valid context");
        assert_eq!(canonical.as_slice(), expected_cbor);
        assert_eq!(Sha256::digest(&canonical).as_slice(), expected_hash);
        let binding = derive_service_channel_exporter_fixture(master_secret, &context)
            .expect("valid fixture derivation");
        assert_eq!(binding.as_bytes(), expected_exporter);
        assert_eq!(format!("{binding:?}"), "ServiceChannelBinding([REDACTED])");
    }
}

#[test]
fn one_field_mutation_separates_context_and_exporter() {
    let master_secret = include_bytes!(concat!(
        "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/exporter-master-secret.bin"
    ));
    let original = tcp_context("service.example.web");
    let mutated = tcp_context("service.example.api");
    let original_context = canonical_service_channel_context(&original).expect("valid context");
    let mutated_context = canonical_service_channel_context(&mutated).expect("valid context");
    assert_ne!(original_context, mutated_context);

    let original_binding = derive_service_channel_exporter_fixture(master_secret, &original)
        .expect("valid fixture derivation");
    let mutated_binding = derive_service_channel_exporter_fixture(master_secret, &mutated)
        .expect("valid fixture derivation");
    assert_ne!(original_binding.as_bytes(), mutated_binding.as_bytes());
}

#[test]
fn invalid_context_is_rejected_before_derivation() {
    let master_secret = include_bytes!(concat!(
        "../../../vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/exporter-master-secret.bin"
    ));
    let invalid = tcp_context("");
    assert_eq!(
        derive_service_channel_exporter_fixture(master_secret, &invalid),
        Err(ServiceChannelExporterError::InvalidServiceId)
    );
}
