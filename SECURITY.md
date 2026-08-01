# Security Policy

NBSR is an experimental protocol and reference implementation. It is not production-ready and must not be presented as providing production security guarantees.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting feature for this repository when available. Otherwise, contact the repository owner privately through their GitHub profile and provide only enough initial information to establish a secure reporting channel.

A useful report includes:

- affected commit, branch, component, and configuration;
- impact and affected trust boundary;
- exact reproduction steps or a minimal proof of concept;
- required privileges, identity, and network position;
- whether secrets, personal data, or third-party systems were involved;
- suggested mitigation, when known.

Do not include real credentials, private keys, tokens, production data, or confidential logs. Redact sensitive material before sharing it.

## Authorized testing only

Security testing must be limited to systems and accounts you own or have explicit authorization to test. Do not scan, exploit, disrupt, or attempt to access third-party systems in the name of NBSR research.

The project does not authorize:

- testing against public services without permission;
- denial-of-service or resource-exhaustion testing against shared infrastructure;
- credential theft, persistence, lateral movement, or destructive actions;
- publication of an uncoordinated exploit affecting users or operators.

## Supported security scope

Reports are especially relevant when they affect:

- deterministic CBOR or schema validation;
- COSE Sign1 or Ed25519 verification;
- route, session, stream, identity, name, port, transport, nonce, expiry, or sequence binding;
- downgrade, replay, rollback, equivocation, or revocation behavior;
- synthetic-address ownership and resolution state;
- destination and OriginSet policy enforcement;
- TLS, mTLS, QUIC, ALPN, or peer-identity validation;
- secret handling, release packaging, container isolation, or default-deny policy;
- inconsistencies between normative documentation, vectors, and implementations.

## Current non-claims

The repository does not claim production readiness, global federation, distributed replay or revocation guarantees, DDoS elimination, anonymity, complete origin concealment, or independent runtime interoperability. See `docs/protocol/status.md`, `docs/security-model.md`, and `docs/threat-model.md`.

## Disclosure process

The maintainers will attempt to acknowledge a credible report, reproduce it, assess affected versions and boundaries, prepare a fix and regression test, and coordinate disclosure. Response times are best-effort while the project remains independently maintained.
