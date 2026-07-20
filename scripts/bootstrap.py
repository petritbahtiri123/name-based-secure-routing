from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID


def private_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def public_pem(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


root = Path(__file__).resolve().parents[1]
secrets = root / "secrets"
tokens = root / "tokens"
secrets.mkdir(exist_ok=True)
tokens.mkdir(exist_ok=True)
identity = Ed25519PrivateKey.generate()
ticket = Ed25519PrivateKey.generate()
name_binding = Ed25519PrivateKey.generate()
(secrets / "identity-private.pem").write_bytes(private_pem(identity))
(secrets / "identity-public.pem").write_bytes(public_pem(identity))
(secrets / "ticket-private.pem").write_bytes(private_pem(ticket))
(secrets / "ticket-public.pem").write_bytes(public_pem(ticket))
(secrets / "name-binding-private.pem").write_bytes(private_pem(name_binding))
(secrets / "name-binding-public.pem").write_bytes(public_pem(name_binding))
now = datetime.now(UTC)
for short in ("allowed", "denied"):
    claims = {"iss": "https://identity.nbsr.local", "sub": f"spiffe://nbsr.local/workload/client-{short}", "aud": "nbsr-control-plane", "iat": now, "exp": now + timedelta(hours=8), "jti": f"demo-{short}-{int(now.timestamp())}"}
    (tokens / f"client-{short}.jwt").write_text(jwt.encode(claims, identity, algorithm="EdDSA"), encoding="utf-8")

# Optional local mTLS material. It is not used by the reliable JWT path.
ca_key = Ed25519PrivateKey.generate()
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NBSR local demo CA")])
ca = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + timedelta(days=7)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(ca_key, algorithm=None)
(secrets / "demo-ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
(secrets / "demo-ca-private.pem").write_bytes(private_pem(ca_key))
print("Generated ignored local demo keys, tokens, and optional mTLS CA material.")
