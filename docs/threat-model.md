# Threat model

| Threat | Asset | Prototype mitigation | Remaining limitation | Production recommendation |
|---|---|---|---|---|
| Stolen identity token | Workload identity | Signature, audience, issuer, expiry | Usable until expiry | Hardware/workload-bound identity and revocation |
| Stolen/replayed ticket | Route grant | 60s TTL, scope, `jti` | No replay cache | One-time nonce/replay store or channel binding |
| Ticket tampering | Policy grant | Ed25519 verification | Endpoint compromise bypasses checks | HSM keys and attested enforcement |
| Malicious client | Backend/API | Default deny and network isolation | DoS remains possible | Rate limits and quotas |
| Compromised gateway | Route integrity | Gateway lacks signing key | Can bypass forwarding rules | Hardened runtime, attestation, mesh policy |
| Compromised control plane | Signing key | Isolated private key | Can mint tickets | HSM/KMS, rotation, HA, audit |
| Compromised OPA/policy error | Authorization | Explicit versioned default deny | Allowed decision can be forged | Signed policy bundles and review gates |
| Backend enumeration/bypass | Backend secrecy | No address in API; no host port | Same-network compromise | Strong NetworkPolicy/firewalls and mTLS |
| Confused deputy | Route scope | Bind subject/service/method/path/audience | Bearer forwarding risks remain | Delegation chains and channel binding |
| Service-name spoofing | Logical namespace | Pydantic syntax and policy allowlist | No ownership registry | Signed service registry |
| Key leakage | Identity/routes | Separate keys, ignored local files | Plain local files | HSM/KMS and automated rotation |
| Log leakage | Credentials | Stable errors; no deliberate token logs | Platform access logs need review | Central redaction controls |
| Denial of service | Availability | Timeouts and bounded input | No rate limiting/HA | Edge limits, autoscaling, circuit breakers |
| Policy misconfiguration | Authorization | OPA tests and default deny | Human review required | CI policy tests and approvals |
