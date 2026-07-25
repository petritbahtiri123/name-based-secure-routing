import argparse
import sys
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from nbsr.secure_files import ensure_private_directory, secure_write_private, secure_write_text  # noqa: E402


def private_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def public_pem(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


parser = argparse.ArgumentParser(description="Generate local NBSR demo trust material.")
parser.add_argument(
    "--output-root",
    type=Path,
    default=repo_root,
    help="Root under which secrets/ and tokens/ are generated (defaults to the repository root).",
)
output_root = parser.parse_args().output_root.resolve()
secrets = output_root / "secrets"
tokens = output_root / "tokens"
ensure_private_directory(secrets)
ensure_private_directory(tokens)
identity = Ed25519PrivateKey.generate()
ticket = Ed25519PrivateKey.generate()
name_binding = Ed25519PrivateKey.generate()
secure_write_private(secrets / "identity-private.pem", private_pem(identity))
(secrets / "identity-public.pem").write_bytes(public_pem(identity))
secure_write_private(secrets / "ticket-private.pem", private_pem(ticket))
(secrets / "ticket-public.pem").write_bytes(public_pem(ticket))
secure_write_private(secrets / "name-binding-private.pem", private_pem(name_binding))
(secrets / "name-binding-public.pem").write_bytes(public_pem(name_binding))
now = datetime.now(UTC)
for short in ("allowed", "denied"):
    claims = {
        "iss": "https://identity.nbsr.local",
        "sub": f"spiffe://nbsr.local/workload/client-{short}",
        "aud": "nbsr-control-plane",
        "iat": now,
        "exp": now + timedelta(hours=8),
        "jti": f"demo-{short}-{int(now.timestamp())}",
    }
    secure_write_text(tokens / f"client-{short}.jwt", jwt.encode(claims, identity, algorithm="EdDSA"))

# Local enterprise TLS material protects every cross-container enterprise hop.
ca_key = Ed25519PrivateKey.generate()
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NBSR local demo CA")])
ca = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=1))
    .not_valid_after(now + timedelta(days=7))
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=None,
            decipher_only=None,
        ),
        critical=True,
    )
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
    .sign(ca_key, algorithm=None)
)
(secrets / "demo-ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
secure_write_private(secrets / "demo-ca-private.pem", private_pem(ca_key))


def issue_certificate(
    certificate_authority_key,
    certificate_authority,
    common_name: str,
    extended_key_usage,
    *,
    include_localhost: bool = False,
):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    names = [x509.DNSName(common_name)]
    if include_localhost:
        names.extend((x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1"))))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(certificate_authority.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.ExtendedKeyUsage([extended_key_usage]), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(certificate_authority_key.public_key()),
            critical=False,
        )
        .sign(certificate_authority_key, algorithm=None)
    )
    return key, cert


for service_name, file_prefix, include_localhost in (
    ("control-plane", "control-plane", True),
    ("gateway", "gateway", True),
    ("opa", "opa", False),
    ("ticket-verifier", "ticket-verifier", False),
    ("payments-service", "payments-service", False),
):
    server_key, server_cert = issue_certificate(
        ca_key,
        ca,
        service_name,
        ExtendedKeyUsageOID.SERVER_AUTH,
        include_localhost=include_localhost,
    )
    secure_write_private(secrets / f"enterprise-{file_prefix}-key.pem", private_pem(server_key))
    (secrets / f"enterprise-{file_prefix}-cert.pem").write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

for client_name, file_prefix in (
    ("control-plane-client", "control-plane-client"),
    ("gateway-client", "gateway-client"),
):
    client_key, client_cert = issue_certificate(
        ca_key,
        ca,
        client_name,
        ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    secure_write_private(secrets / f"enterprise-{file_prefix}-key.pem", private_pem(client_key))
    (secrets / f"enterprise-{file_prefix}-cert.pem").write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))

# The ISP name-control and relay share a demo-only CA that is separate from the
# enterprise service CA and from every JWT/signing trust domain.
isp_ca_key = Ed25519PrivateKey.generate()
isp_ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NBSR ISP demo CA")])
isp_ca = (
    x509.CertificateBuilder()
    .subject_name(isp_ca_name)
    .issuer_name(isp_ca_name)
    .public_key(isp_ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=1))
    .not_valid_after(now + timedelta(days=7))
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=None,
            decipher_only=None,
        ),
        critical=True,
    )
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(isp_ca_key.public_key()), critical=False)
    .sign(isp_ca_key, algorithm=None)
)


(secrets / "isp-ca.pem").write_bytes(isp_ca.public_bytes(serialization.Encoding.PEM))
secure_write_private(secrets / "isp-ca-private.pem", private_pem(isp_ca_key))
for service_name, file_prefix in (("name-control", "control"), ("name-relay", "relay"), ("facebook.test", "origin")):
    server_key, server_cert = issue_certificate(
        isp_ca_key,
        isp_ca,
        service_name,
        ExtendedKeyUsageOID.SERVER_AUTH,
        include_localhost=True,
    )
    secure_write_private(secrets / f"isp-{file_prefix}-key.pem", private_pem(server_key))
    (secrets / f"isp-{file_prefix}-cert.pem").write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

print("Generated ignored enterprise and ISP demo trust material.")
