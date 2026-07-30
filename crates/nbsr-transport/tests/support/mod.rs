#![allow(dead_code)]

use rcgen::{
    BasicConstraints, CertificateParams, CertifiedIssuer, ExtendedKeyUsagePurpose, IsCa, KeyPair,
    KeyUsagePurpose,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};

pub struct TestPki {
    ca: CertificateDer<'static>,
    source_cert: CertificateDer<'static>,
    source_key: Vec<u8>,
    destination_cert: CertificateDer<'static>,
    destination_key: Vec<u8>,
}

impl TestPki {
    pub fn generate() -> Self {
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

        let (source_cert, source_key) = issue_leaf(&ca, "source-edge.test");
        let (destination_cert, destination_key) = issue_leaf(&ca, "destination-edge.test");

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

    pub fn roots(&self) -> RootCertStore {
        roots(self.ca.clone())
    }
}

fn issue_leaf(
    issuer: &CertifiedIssuer<'_, KeyPair>,
    dns_name: &str,
) -> (CertificateDer<'static>, Vec<u8>) {
    let mut params = CertificateParams::new(vec![dns_name.to_owned()]).expect("valid test DNS SAN");
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
