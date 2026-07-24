# Threat model

| Threat | Asset | Prototype mitigation | Remaining limitation | Production recommendation |
|---|---|---|---|---|
| Stolen identity token | Workload identity | Signature, audience, issuer, expiry | Usable until expiry | Hardware/workload-bound identity and revocation |
| Stolen/replayed enterprise ticket | Route grant | 60s TTL, method/path/service scope, `jti` | Enterprise ticket remains bearer material | One-time nonce/replay store or channel binding |
| Replayed ISP admission | Name route | Session-key proof, fresh nonce, bounded replay cache | Cache is process-local | Durable regional replay state or sticky routing |
| Ticket tampering | Policy grant | Ed25519 verification | Endpoint compromise bypasses checks | HSM keys and attested enforcement |
| Plaintext credential interception | Identity and route grants | Server-authenticated TLS on all client-facing control, gateway, and relay endpoints | Demo CA and server authentication only | Managed PKI; enterprise mTLS where policy requires it |
| Client header spoofing | Enterprise authorization | Verifier uses ext-authz request method/path; Envoy overrides the fixed service header inside the auth request | Envoy compromise remains authoritative | Signed inter-service context or mutually authenticated mesh |
| Malicious client | Backend/API | Default deny, scoped tickets, name-route rate limits, bounded state | Enterprise admission and limits are not distributed | Edge limits, tenant quotas, and abuse service |
| Compromised gateway | Route integrity | Gateway lacks signing key | Can bypass forwarding rules | Hardened runtime, attestation, mesh policy |
| Compromised control plane | Signing key | Isolated private key | Can mint tickets | HSM/KMS, rotation, HA, audit |
| Compromised OPA/policy error | Authorization | Explicit versioned default deny | Allowed decision can be forged | Signed policy bundles and review gates |
| Backend enumeration/bypass | Backend secrecy | No address in API or host port; default-deny and per-workload NetworkPolicy | Node or cluster administrator can bypass pod policy | Separate trust zones, firewalls, and service authentication |
| Confused deputy | Route scope | Bind subject/service/method/path/audience | Bearer forwarding risks remain | Delegation chains and channel binding |
| Service-name spoofing | Logical namespace | Pydantic syntax and policy allowlist | No ownership registry | Signed service registry |
| DNS rebinding or SSRF | Relay destination | Revalidate every resolved literal at connect time; global-unicast default; exact trusted-origin exceptions | Operator-approved private origins remain trusted | Signed registry and independently managed egress policy |
| Capability escalation | Relay scope | `http` authorizes only TCP/80 and `https` only TCP/443 | No richer protocol negotiation | Versioned capability registry and conformance tests |
| Key leakage | Identity/routes | Separate keys; ignored, atomic, owner-restricted local files | File-based demo keys remain on the host | HSM/KMS and automated rotation |
| Log leakage | Credentials | Stable errors; no deliberate token logs | Platform access logs need review | Central redaction controls |
| Denial of service | Availability | Timeouts, bounded input/state, global and per-client name-route limits | Single-process counters; no HA coordination | Regional limits, autoscaling, circuit breakers |
| Kubernetes lateral movement | Workload isolation | Default deny plus named peer/port policies; live positive/negative Kind probe | Kind is a reference lab, not a production cluster | Enforced production CNI, admission policy, and continuous probes |
| Policy misconfiguration | Authorization | OPA tests and default deny | Human review required | CI policy tests and approvals |
