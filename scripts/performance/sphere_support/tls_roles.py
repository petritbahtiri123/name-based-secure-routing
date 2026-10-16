"""Create private role key only on its node. Public CSR/certificate exchange only."""
import json, os, pathlib, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from plan import UNIT,ROOT,CONTROL

def reaper_gate(role):
    from tls_lifetime import gate
    return gate(role,270)

def csr(role):
    if role not in UNIT:raise ValueError('role')
    reaper_gate(role)
    from tls_lifetime import authority
    os.umask(0o077);p=authority(role)
    if list(p.iterdir()):raise ValueError('TLS directory not empty')
    key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,role+'.edge')])
    req=x509.CertificateSigningRequestBuilder().subject_name(name).add_extension(x509.SubjectAlternativeName([x509.DNSName(role+'.edge')]),False).sign(key,hashes.SHA256())
    reaper_gate(role)
    (p/(role+'-key.der')).write_bytes(key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    public=req.public_bytes(serialization.Encoding.DER);(p/(role+'.csr')).write_bytes(public)
    return public

def sign_public(requests):
    if set(requests)!=set(UNIT):raise ValueError('roles')
    now=datetime.now(timezone.utc);key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'NBSR ephemeral 20261016-01')])
    ca=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(minutes=10)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).sign(key,hashes.SHA256())
    result={'ca.der':ca.public_bytes(serialization.Encoding.DER)}
    for role,raw in requests.items():
        req=x509.load_der_x509_csr(raw)
        if not req.is_signature_valid or req.subject!=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,role+'.edge')]):raise ValueError('CSR identity/signature')
        if req.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)!=[role+'.edge']:raise ValueError('CSR SAN')
        pub=req.public_key()
        if not isinstance(pub,ec.EllipticCurvePublicKey) or not isinstance(pub.curve,ec.SECP256R1):raise ValueError('CSR algorithm')
        cert=x509.CertificateBuilder().subject_name(req.subject).issuer_name(ca.subject).public_key(pub).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(minutes=10)).add_extension(x509.SubjectAlternativeName([x509.DNSName(role+'.edge')]),False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH,ExtendedKeyUsageOID.SERVER_AUTH]),False).sign(key,hashes.SHA256())
        result[role+'.der']=cert.public_bytes(serialization.Encoding.DER)
    # CA private key is never serialized; only these public bytes escape the function.
    return result

if __name__=='__main__':sys.stdout.buffer.write(csr(sys.argv[1]))
