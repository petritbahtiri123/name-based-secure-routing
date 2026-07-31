use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Duration;

use nbsr_transport::{
    EdgeIdentity, EdgeRole, PeerPolicy, ServiceChannelContext, TransportListener,
    build_client_config, build_server_config, connect,
};

mod support;

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).expect("test identity")
}

fn context() -> ServiceChannelContext<'static> {
    ServiceChannelContext {
        session_id: [0x10; 16],
        source_edge_id: "source.edge",
        destination_edge_id: "destination.edge",
        channel_id: [0x40; 16],
        route_id: [0x20; 16],
        route_grant_digest: [0x50; 32],
        service_id: "service.example",
        transport: "tcp",
        port: 8443,
        policy_hash: [0x60; 32],
        client_nonce: [0x70; 32],
        edge_nonce: [0x80; 32],
    }
}

async fn connection_pair() -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    connection_pair_with_pki(&pki).await
}

async fn connection_pair_with_pki(
    pki: &support::TestPki,
) -> (
    TransportListener,
    nbsr_transport::AuthenticatedConnection,
    nbsr_transport::AuthenticatedConnection,
) {
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
    (
        listener,
        source.expect("source connection"),
        destination.expect("destination connection"),
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn both_authenticated_peers_derive_the_same_live_binding() {
    let (listener, source, destination) = connection_pair().await;
    let context = context();

    let source_binding = source
        .export_channel_binding(&context)
        .expect("source exporter binding");
    let destination_binding = destination
        .export_channel_binding(&context)
        .expect("destination exporter binding");

    assert_eq!(source_binding, destination_binding);
    source.close().await.expect("close source");
    destination.close().await.expect("close destination");
    listener.close().await.expect("close listener");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn fresh_tls_handshake_changes_the_binding_for_identical_nbsr_context() {
    let pki = support::TestPki::generate_for("source.edge", "destination.edge");
    let (first_listener, first_source, first_destination) = connection_pair_with_pki(&pki).await;
    let first = first_source
        .export_channel_binding(&context())
        .expect("first live binding");
    first_source.close().await.expect("close first source");
    first_destination
        .close()
        .await
        .expect("close first destination");
    first_listener.close().await.expect("close first listener");

    let (second_listener, second_source, second_destination) = connection_pair_with_pki(&pki).await;
    let second = second_source
        .export_channel_binding(&context())
        .expect("second live binding");

    assert_ne!(first, second);
    second_source.close().await.expect("close second source");
    second_destination
        .close()
        .await
        .expect("close second destination");
    second_listener
        .close()
        .await
        .expect("close second listener");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn every_verified_context_input_separates_the_live_binding() {
    let (listener, source, destination) = connection_pair().await;
    let baseline = source
        .export_channel_binding(&context())
        .expect("baseline live binding");
    let mut mutations = Vec::new();

    let mut mutated = context();
    mutated.session_id[0] ^= 1;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.source_edge_id = "source-other.edge";
    mutations.push(mutated);
    let mut mutated = context();
    mutated.destination_edge_id = "destination-other.edge";
    mutations.push(mutated);
    let mut mutated = context();
    mutated.channel_id[0] ^= 1;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.route_id[0] ^= 1;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.route_grant_digest[0] ^= 1;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.service_id = "service.other";
    mutations.push(mutated);
    let mut mutated = context();
    mutated.transport = "udp";
    mutations.push(mutated);
    let mut mutated = context();
    mutated.port = 8444;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.policy_hash[0] ^= 1;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.client_nonce[0] ^= 1;
    mutations.push(mutated);
    let mut mutated = context();
    mutated.edge_nonce[0] ^= 1;
    mutations.push(mutated);

    for mutated in mutations {
        let binding = source
            .export_channel_binding(&mutated)
            .expect("valid mutated live context");
        assert_ne!(baseline, binding);
    }

    source.close().await.expect("close source");
    destination.close().await.expect("close destination");
    listener.close().await.expect("close listener");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn live_binding_debug_is_redacted() {
    let (listener, source, destination) = connection_pair().await;
    let binding = source
        .export_channel_binding(&context())
        .expect("live binding");

    assert_eq!(format!("{binding:?}"), "ChannelBinding([REDACTED])");
    source.close().await.expect("close source");
    destination.close().await.expect("close destination");
    listener.close().await.expect("close listener");
}
