use quinn::crypto::rustls::{QuicClientConfig, QuicServerConfig};
use rcgen::{
    BasicConstraints, CertificateParams, CertifiedIssuer, ExtendedKeyUsagePurpose, IsCa, KeyPair,
    KeyUsagePurpose, date_time_ymd,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use rustls::server::WebPkiClientVerifier;
use rustls::version;
use std::sync::Arc;

#[allow(dead_code)]
pub struct TestPki {
    ca: CertificateDer<'static>,
    source_cert: CertificateDer<'static>,
    source_key: Vec<u8>,
    destination_cert: CertificateDer<'static>,
    destination_key: Vec<u8>,
}

#[allow(dead_code)]
impl TestPki {
    pub fn generate() -> Self {
        Self::generate_with_expired_leaf(None)
    }

    pub fn generate_for(source_dns_name: &str, destination_dns_name: &str) -> Self {
        Self::generate_with_names(source_dns_name, destination_dns_name, None)
    }

    pub fn generate_with_expired_source() -> Self {
        Self::generate_with_expired_leaf(Some("source-edge.test"))
    }

    pub fn generate_with_expired_destination() -> Self {
        Self::generate_with_expired_leaf(Some("destination-edge.test"))
    }

    fn generate_with_expired_leaf(expired_leaf: Option<&str>) -> Self {
        Self::generate_with_names("source-edge.test", "destination-edge.test", expired_leaf)
    }

    fn generate_with_names(
        source_dns_name: &str,
        destination_dns_name: &str,
        expired_leaf: Option<&str>,
    ) -> Self {
        let mut ca_params = CertificateParams::default();
        ca_params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
        ca_params.key_usages = vec![
            KeyUsagePurpose::KeyCertSign,
            KeyUsagePurpose::DigitalSignature,
            KeyUsagePurpose::CrlSign,
        ];
        let ca = CertifiedIssuer::self_signed(
            ca_params,
            KeyPair::generate().expect("generate test CA key"),
        )
        .expect("generate test CA certificate");

        let (source_cert, source_key) =
            issue_leaf(&ca, source_dns_name, expired_leaf == Some(source_dns_name));
        let (destination_cert, destination_key) = issue_leaf(
            &ca,
            destination_dns_name,
            expired_leaf == Some(destination_dns_name),
        );

        Self {
            ca: ca.der().clone(),
            source_cert,
            source_key,
            destination_cert,
            destination_key,
        }
    }

    pub fn source_material(&self) -> nbsr_transport::TlsMaterial {
        material(
            self.ca.clone(),
            self.source_cert.clone(),
            self.source_key.clone(),
        )
    }

    pub fn destination_material(&self) -> nbsr_transport::TlsMaterial {
        material(
            self.ca.clone(),
            self.destination_cert.clone(),
            self.destination_key.clone(),
        )
    }

    pub fn source_material_trusting(&self, trusted: &Self) -> nbsr_transport::TlsMaterial {
        material(
            trusted.ca.clone(),
            self.source_cert.clone(),
            self.source_key.clone(),
        )
    }

    pub fn destination_material_trusting(&self, trusted: &Self) -> nbsr_transport::TlsMaterial {
        material(
            trusted.ca.clone(),
            self.destination_cert.clone(),
            self.destination_key.clone(),
        )
    }

    pub fn roots(&self) -> RootCertStore {
        roots(self.ca.clone())
    }

    pub fn client_config_without_certificate(&self, alpn: &[u8]) -> quinn::ClientConfig {
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        let mut tls = rustls::ClientConfig::builder_with_provider(provider)
            .with_protocol_versions(&[&version::TLS13])
            .expect("TLS 1.3")
            .with_root_certificates(self.roots())
            .with_no_client_auth();
        tls.alpn_protocols = vec![alpn.to_vec()];
        quinn::ClientConfig::new(Arc::new(
            QuicClientConfig::try_from(tls).expect("test QUIC client config"),
        ))
    }

    pub fn server_config_with_alpn(&self, alpn: &[u8]) -> quinn::ServerConfig {
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        let verifier = WebPkiClientVerifier::builder_with_provider(
            Arc::new(self.roots()),
            Arc::clone(&provider),
        )
        .build()
        .expect("test client verifier");
        let mut tls = rustls::ServerConfig::builder_with_provider(provider)
            .with_protocol_versions(&[&version::TLS13])
            .expect("TLS 1.3")
            .with_client_cert_verifier(verifier)
            .with_single_cert(
                vec![self.destination_cert.clone()],
                PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(self.destination_key.clone())),
            )
            .expect("test server certificate");
        tls.alpn_protocols = vec![alpn.to_vec()];
        quinn::ServerConfig::with_crypto(Arc::new(
            QuicServerConfig::try_from(tls).expect("test QUIC server config"),
        ))
    }
}

fn issue_leaf(
    issuer: &CertifiedIssuer<'_, KeyPair>,
    dns_name: &str,
    expired: bool,
) -> (CertificateDer<'static>, Vec<u8>) {
    let mut params = CertificateParams::new(vec![dns_name.to_owned()]).expect("valid test DNS SAN");
    if expired {
        params.not_before = date_time_ymd(2020, 1, 1);
        params.not_after = date_time_ymd(2020, 1, 2);
    }
    params.extended_key_usages = vec![
        ExtendedKeyUsagePurpose::ClientAuth,
        ExtendedKeyUsagePurpose::ServerAuth,
    ];
    params.key_usages = vec![KeyUsagePurpose::DigitalSignature];
    let key = KeyPair::generate().expect("generate test leaf key");
    let cert = params
        .signed_by(&key, issuer)
        .expect("issue test leaf certificate");
    (cert.der().clone(), key.serialize_der())
}

fn roots(ca: CertificateDer<'static>) -> RootCertStore {
    let mut roots = RootCertStore::empty();
    roots.add(ca).expect("add test CA");
    roots
}

fn material(
    ca: CertificateDer<'static>,
    cert: CertificateDer<'static>,
    key: Vec<u8>,
) -> nbsr_transport::TlsMaterial {
    nbsr_transport::TlsMaterial::new(
        vec![cert],
        PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(key)),
        roots(ca),
    )
    .expect("valid test TLS material")
}
