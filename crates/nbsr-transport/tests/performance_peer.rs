use std::net::{Ipv4Addr, SocketAddr};
use std::time::Duration;

use nbsr_transport::{
    EdgeIdentity, EdgeRole, PeerPolicy, TlsMaterial, TransportListener, build_client_config,
    build_server_config, connect,
};
use rcgen::{BasicConstraints, CertificateParams, CertifiedIssuer, IsCa, KeyPair};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).unwrap()
}

fn materials() -> (TlsMaterial, TlsMaterial) {
    let mut ca_params = CertificateParams::new(Vec::<String>::new()).unwrap();
    ca_params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
    let ca_key = KeyPair::generate().unwrap();
    let issuer = CertifiedIssuer::self_signed(ca_params, ca_key).unwrap();
    let ca = CertificateDer::from(issuer.der().to_vec());
    let issue = |name: &str| {
        let key = KeyPair::generate().unwrap();
        let certificate = CertificateParams::new(vec![name.to_string()])
            .unwrap()
            .signed_by(&key, &issuer)
            .unwrap();
        let mut roots = RootCertStore::empty();
        roots.add(ca.clone()).unwrap();
        TlsMaterial::new(
            vec![CertificateDer::from(certificate.der().to_vec())],
            PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(key.serialize_der())),
            roots,
        )
        .unwrap()
    };
    (issue("source.edge"), issue("destination.edge"))
}

#[tokio::test]
async fn direct_benchmark_echo_uses_authenticated_quic_without_control_processing() {
    let (source_tls, destination_tls) = materials();
    let listener = TransportListener::bind(
        build_server_config(
            PeerPolicy::new(
                EdgeRole::Destination,
                EdgeRole::Source,
                identity("source.edge"),
                Duration::from_secs(2),
                Duration::from_secs(5),
            )
            .unwrap(),
            destination_tls,
        )
        .unwrap(),
        SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
    )
    .unwrap();
    let address = listener.local_addr().unwrap();
    let (completed_send, completed_receive) = tokio::sync::oneshot::channel();
    let server = tokio::spawn(async move {
        let connection = listener.accept_one().await.unwrap();
        let bytes = connection.accept_direct_benchmark_echo().await.unwrap();
        completed_receive.await.unwrap();
        connection.close().await.unwrap();
        listener.close().await.unwrap();
        bytes
    });
    let connection = connect(
        build_client_config(
            PeerPolicy::new(
                EdgeRole::Source,
                EdgeRole::Destination,
                identity("destination.edge"),
                Duration::from_secs(2),
                Duration::from_secs(5),
            )
            .unwrap(),
            source_tls,
        )
        .unwrap(),
        address,
    )
    .await
    .unwrap();
    assert_eq!(connection.negotiated_alpn(), b"nbsr-quic-1");
    let response = connection
        .direct_benchmark_request(&vec![0x5a; 1024])
        .await
        .unwrap();
    assert_eq!(response, vec![0x5a; 1024]);
    completed_send.send(()).unwrap();
    connection.close().await.unwrap();
    assert_eq!(server.await.unwrap(), 1024);
}
