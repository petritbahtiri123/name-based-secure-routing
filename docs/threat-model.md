# NBSR threat model

Current architecture direction comes from
[NBSR Protocol Vision V3.6](architecture/NBSR_Protocol_Vision_V3.6.md).
This threat model describes the hardened prototype boundary; it does not claim
that the planned Name Node, OriginSet publication, QUIC Transport Session,
Service Channels, mobility profile, or federation exists.

## Scope

Assets in scope are registered-name integrity, origin concealment from clients,
route authorization, workload identity, signing/TLS keys, protected
application payloads, policy decisions, synthetic adapter state, and deployment
isolation. The current adversaries are a malicious client, compromised relay or
workload, network attacker, DNS rebinding source, forged service, and
misconfigured deployment.

The gateway/operator is trusted to route and enforce policy. It necessarily sees
requested names and resolved destinations. Node, Docker host, cluster
administrator, signing-key holder, and certificate-authority compromise are
outside the prototype's containment boundary.

## Threats and controls

| Threat | Concrete path | Enforcement boundary | Implemented control | Remaining limitation |
|---|---|---|---|---|
| Unauthorized public proxy | Caller asks for arbitrary public hostname/IP on 80/443 | Name control and relay registry | Only canonical enabled registry entries are admitted; public global-unicast is not authorization | Registry administration and signed ownership are local/manual |
| Private SSRF and metadata | Registered or rebound name resolves to special-use address | Name control issuance and relay connect-time check | Exact endpoint constraints plus special-use IPv4/IPv6 rejection | A deliberately registered private demo origin is trusted by policy |
| DNS rebinding/TOCTOU | Resolution changes after capability issuance | Relay immediately before socket open | Fresh resolution must exactly match signed set and current local policy | Conventional DNS still resolves the configured demo origin |
| Capability replay across routes | Ticket for route A used for route B/port | Relay capability and proof verifier | Name, route ID, gateway, port, policy fingerprint, endpoint set, session, audience, issuer, expiry bound together | Replay state is process-local |
| ISP admission replay | Captured route plus nonce reused | Bounded relay replay cache | Ephemeral Ed25519 proof and one-time nonce consumption | No regional durable replay coordination |
| Enterprise ticket replay | Valid bearer ticket reused before expiry | Envoy/verifier | Short lifetime and request scope | Not prevented; channel binding or one-time distributed replay state required |
| Header/method spoofing | Client forges service or authorization metadata | Envoy ext_authz and verifier | Gateway overwrites fixed service context; verifier checks actual method/path and rejects missing/duplicate metadata | Compromised Envoy remains authoritative |
| Backend bypass from relay | Compromised ISP relay connects to payments | Compose network and Calico policy | Separate ISP origin network; no enterprise protected interface; default-deny policy | Host/root or cluster-admin compromise bypasses this isolation |
| Unrelated Kubernetes pod lateral movement | Arbitrary pod reaches verifier/payments | Calico NetworkPolicy | Named source labels/ports only; live Service IP and Pod IP denial probes | Label/admission governance is not production-hardened |
| Broad DNS egress | Workload uses arbitrary kube-system pod as egress | DNS NetworkPolicy | Namespace plus `k8s-app: kube-dns` selector, TCP/UDP 53 only | DNS content/authenticity remains cluster-DNS dependent |
| Plaintext interception | Credentials or payload cross network in clear | TLS/mTLS service boundaries | Verified client-facing TLS and internal TLS 1.3 mTLS; no downgrade | Local bootstrap CA is not managed production PKI |
| Wrong-service certificate | Valid cert for one service used for another | TLS hostname/SAN/EKU validation | Service-specific certificates and expected server names | Rotation and revocation automation absent |
| Missing client identity | Peer reaches internal authorization/backend TLS endpoint | OPA, verifier, payments mTLS servers | Client certificate required before an HTTP response is served | Certificate identity maps to trust, not fine-grained service authorization |
| Origin enumeration | Client learns durable origin IP or reaches host port | API response, adapter state, deployment topology | Synthetic address only; no backend/origin host port; relay-only origin ingress | Operator, host admin, and cluster admin see internal addressing |
| Origin impersonation | Relay redirects HTTPS to wrong service | Application TLS | Client preserves registered SNI/Host and validates origin certificate | Compatibility HTTP has no end-to-end origin authentication |
| State exhaustion | Attacker fills replay, allocator, or admission structures | In-process capacity guards | Hard limits, expiry cleanup, and fail-closed admission | No distributed quota or DDoS service |
| Key leakage in source/archive | Generated keys enter build or release | Ignore/build/package boundaries | Atomic protected files, ignore rules, prohibited-path and content scans | Developer host compromise remains out of scope |
| Downgrade | TLS or native requirement replaced by plaintext/weaker path | Client TLS context and service config | TLS-required URLs, minimum/maximum TLS 1.3 internally, no plaintext retry | A normative native transport negotiation protocol is not implemented |
| Unicode/name alias confusion | Mixed case, trailing dot, or IDNA ambiguity bypasses policy | Request model and registry canonicalizer | Exact canonical ASCII registered name required | Internationalized native NBSR naming is not specified |
| Policy rollback/staleness | Old capability survives registry change | Relay local registry | Version and deterministic fingerprint mismatch fails closed | No distributed policy rollout consistency protocol |

## V3.6 architecture threats and required future controls

The following rows are forward-looking requirements. `Planned control` does
not claim implementation.

| Threat | Concrete path | Required future control | Failure rule / remaining gate |
|---|---|---|---|
| Malicious or compromised legacy DNS | Adapter returns attacker-selected or rapidly changing origins | Treat DNS as constrained reachability only; bind results to accepted Service Identity/policy; bound and validate temporary OriginSet | Never authorize from DNS and never return an origin fallback |
| Stale origin update | Old but validly signed update arrives after a newer set | Durable accepted generation/sequence/digest and validity checks | Reject stale update; preserve newer accepted state |
| Rollback or resurrection of an old OriginSet | Publisher replays a prior generation after expiry, revocation, or failover | Tombstone/highest-generation retention plus rollback binding | Fail closed; exact native mechanism is a human gate |
| Same-sequence different-content equivocation | Two updates use the same issuer/generation/sequence with different endpoints | Compare deterministic content digest and retain conflict evidence | Reject both conflicting candidates or follow an approved transparency policy |
| Compromised Destination Edge | Edge redirects channels to an unauthorized endpoint or widens service access | Independent owner/issuer authority, bounded OriginSet selection, per-service admission, revocation, and audit | Edge compromise cannot mint owner identity or authorize another service |
| Cross-service authorization confusion | Grant or admission for service A opens service B on a shared session | Independently authorize and name/service-bind every Service Channel | Reject channel; do not reuse service authorization |
| Channel key/context confusion | Channel A's key or transcript is accepted for channel B | Independent cryptographic or transcript-bound context including service, route, channel, grant, edges, and policy | Fail affected channel; exact derivation is a human gate |
| Transport-session compromise blast radius | Shared edge transport secrets expose or manipulate multiple channels | Forward secrecy, key updates, independent channel context, per-channel authorization, bounded session scope, emergency revocation | Do not treat transport compromise as authority for new services |
| Malicious session migration | Attacker redirects a valid session or Route Context to another path/edge | Path validation and explicit same-edge/cross-edge policy with binding checks | No new authorization from path or source-IP change |
| Replayed resume proof | Captured proof restores expired or revoked state | One-time/replay-safe proof, durable replay state, expiry and revocation recheck | Reject replay without reviving state |
| Unauthorized gateway handover | Gateway transfers a grant or channel to an unapproved peer | Explicit handover authority, target binding, fresh proof, policy and revocation validation | No grant or Route Context transfers blindly |
| Origin leak through logs, errors, telemetry, or fallback | Internal endpoint appears in a client error, route dump, metric label, log, or downgrade | Origin-free public schemas, redaction, opaque IDs, field allowlists, no direct fallback | Stable non-sensitive error; leak test required |
| Origin churn denial of service | Attacker forces repeated OriginSet changes, checks, reconnects, or drains | Generation/sequence rules, bounded update/check budgets, debounce/rate limits, last-known-good policy | Fail closed without global disruption or unbounded work |
| Poisoned health checks | Malicious endpoint or checker marks unauthorized target healthy | Check only authorized exact candidates, bind result to set digest, bound redirect/response/retry behavior | Health never creates identity or authority; trust model is a gate |
| Service-channel starvation or noisy-neighbor behavior | One service exhausts streams, flow control, memory, or audit capacity on shared transport | Independent quotas, fair scheduling, bounded buffers, per-service attribution | Throttle/deny affected channel without implicit cross-service termination |
| Split-brain origin publication | Multiple authorized publishers issue incompatible current sets | Approved publisher precedence, transparency/checkpoints, equivocation evidence, bounded last-known-good behavior | Fail closed when no deterministic authorized winner exists |
| Route continuation after service revocation | Existing channel continues or revives through drain, migration, resumption, or replica failover | Per-service revocation checks at new stream, renewal, resume, migrate, handover, and origin update boundaries | Immediate revoke or approved bounded drain; never resurrect |

## V3.6 trust-boundary changes

- Legacy DNS, delegated reachability, and health checks are untrusted inputs,
  not identity authorities.
- A Transport Session authenticates edges but is not a universal VPN-like
  authorization context.
- A Destination Edge can affect final-segment reachability but cannot become a
  service owner merely because it can reach an origin.
- Replicas must share enough accepted generation, sequence, digest,
  revocation, replay, and tombstone state to prevent rollback or resurrection.
- Default telemetry must distinguish per-service channels while remaining
  unable to reconstruct a client-to-origin map.

## Residual risk by severity

### Critical

No confirmed Critical vulnerability remains within the bounded local prototype
scope. This is not a production assurance statement.

### High

- A compromised control-plane signing key can mint enterprise tickets, and a
  compromised name-binding key can mint ISP route capabilities. There is no
  HSM/KMS, rotation, or distributed revocation.
- Host/root or Kubernetes cluster-admin compromise bypasses container and
  NetworkPolicy boundaries.

### Medium

- Valid enterprise bearer tickets are replayable during their short lifetime.
- Replay, admission, route allocation, and policy state are process-local and
  are not HA-safe.
- Native signed name ownership, federation, and revocation distribution are
  absent, so the local registry is an operator trust anchor.
- Compatibility HTTP lacks end-to-end origin authentication even though the
  outer relay transport is authenticated and encrypted.
- The Windows adapter is a loopback prototype; no signed WFP driver or live
  full-device interception was validated.

### Low

- Gateway/operator metadata retention and privacy controls are not implemented.
- Health and operational telemetry are minimal.
- Local demo certificate expiry requires regeneration rather than automated
  rotation.

## Required production work

Before any production claim: independent protocol review, managed PKI/HSM,
rotation and revocation, signed name ownership/delegation, enterprise replay
control, multiple replicas with shared bounded state, hardened admission/label
governance, regional failure testing, privacy/audit policy, Windows OS
integration, supply-chain attestations, and at least two interoperable native
implementations are required.
