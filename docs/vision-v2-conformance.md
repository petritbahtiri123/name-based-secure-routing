# NBSR Protocol Vision v2 alignment

## Authority and status

This matrix records the historical Vision V2 baseline and is not V3
implementation evidence. Current direction is
[NBSR Protocol Vision V3](architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md).

The retained
[NBSR Protocol Vision v2](architecture/NBSR_Protocol_Vision_v2.pdf) repository
copy is byte-identical to the supplied source and has SHA-256
`746cbe07012dd646de71537470ed9ef55a85222509f065d5dda4668557e56806`.
At the time of this matrix, the earlier 19-page feasibility-study source binary
had not been supplied to the checkout and was not reconstructed. It is now
preserved separately under `docs/research/`.

This matrix is an implementation-status record, not a conformance certificate.
The current repository does not claim native NBSR conformance because it does
not implement the complete mandatory secure tunnel and lifecycle profile.

## Non-negotiable invariants

| Vision v2 invariant | Status | Evidence | Gap |
|---|---|---|---|
| Name-first | Confirmed functional | The ISP API admits only a canonical registered name; client-visible state contains a synthetic address and bounded route capability, not the origin IP. | Native global ownership/delegation is absent. |
| Mandatory authenticated, encrypted, integrity-protected transport | Partially functional | Client-facing service TLS and internal enterprise TLS 1.3 mTLS are live-tested; ISP admission adds an Ed25519 session proof. | No reviewed native multiplexed tunnel profile or independent conformance implementation. |
| No optional secure mode | Partially functional | Configured routes have no verification-disable or plaintext-retry path. | Compatibility HTTP exists inside outer TLS and must not be called native end-to-end authenticated NBSR. |
| Transport agility with fixed security properties | Design/documentation only | TLS 1.3 is the current experiment. | No normative profile negotiation or certified QUIC/Noise/HBONE profiles. |
| Application simplicity | Partially functional | The Windows prototype presents local name/synthetic-address behavior and hides route cryptography from the test application. | Not integrated with production operating-system APIs. |
| Native naming | Partially functional | An operator registry, stable route IDs, and default-deny name semantics are implemented. | Gateway-side conventional DNS still resolves the configured origin; signed ownership and delegation are absent. |
| DNS as migration/bootstrap, not permanent native dependency | Partially functional | The client does not receive a DNS origin answer; DNS is behind the registry/relay boundary. | Current demo still depends on cluster/host DNS for the configured origin. |
| ISP-capable | Partially functional | Local ISP profile works without enterprise IAM or inspection; source relay and destination origin boundaries are separate. | No actual ISP lab, source/destination operator enforcement, subscriber controls, or federated DDoS path. |
| Enterprise IAM optional to core | Confirmed functional | ISP name routing runs without workload JWT/OPA; enterprise identity/policy is a separate flow. | No normative extension negotiation. |
| Platform-neutral; Kubernetes not a dependency | Partially functional | Shared Python services run in Compose and Kind; Kubernetes does not define the route format. | Only one Windows-first client prototype and no independent non-Python implementation. |
| Backend concealment where required | Confirmed functional | No origin/backend host ports; client-visible route state omits durable origin addresses; live origin observes relay peer. | Gateway/operator and privileged infrastructure administrators see routing metadata. |

## Mandatory tunnel properties

| Property | Status | Evidence | Gap |
|---|---|---|---|
| Peer authentication | Partially functional | Server certificates validate client-facing peers; internal enterprise peers use mTLS; ISP client proves an ephemeral session key. | Full mutual native peer identity and trust distribution are absent. |
| Confidentiality | Partially functional | TLS protects NBSR transport and mTLS protects enterprise internal payloads. HTTPS remains end-to-end through the relay. | No native multiplexed tunnel. |
| Integrity | Partially functional | TLS plus Ed25519-signed capabilities/tickets detect modification. | No normative transcript binding across all future states. |
| Forward secrecy | Partially functional | TLS 1.3 cipher negotiation provides transport-level forward secrecy. | No NBSR profile certification or long-lived tunnel key schedule. |
| Anti-replay | Partially functional | ISP nonce replay is rejected in bounded state. | Enterprise bearer ticket replay and distributed regional replay are not prevented. |
| Downgrade resistance | Partially functional | Internal service TLS is fixed to TLS 1.3 and failures do not retry plaintext. | No native version/profile negotiation state machine. |
| Key rotation without stream interruption | Not implemented | Bootstrap can regenerate stopped-demo credentials. | No active tunnel key rotation. |
| Cryptographic name binding | Partially functional | ISP capability binds registered name, route ID, gateway, port, endpoint set, policy fingerprint, client session, and expiry. | The transport session itself is not a complete native tunnel bound to a standardized name transcript. |

## Lifecycle and mobility

| Requirement | Status | Evidence | Gap |
|---|---|---|---|
| Distinct lease and stream semantics | Partially functional | Capabilities expire and one admitted TCP flow can complete independently. | No multiplexed stream/tunnel abstraction or completion-grace specification. |
| Renewal during active transfer | Not implemented | Fresh capability can be requested before a new admission. | No in-stream revalidation/renewal. |
| Idle timeout and maximum lifetime | Partially functional | Handshake/admission deadlines and route expiry exist. | General tunnel idle and maximum lifetime timers do not. |
| Multiplexed streams | Not implemented | One connection carries one TCP flow. | Multiplexing protocol absent. |
| Migration and resumption | Implemented but not live-verified | Ordered pre-admission relay failover is unit-tested. | Active path migration and resumable encrypted sessions absent. |
| Revocation distribution | Not implemented | Local policy version/fingerprint changes deny new admission. | No distributed revocation channel or bounded propagation objective. |
| Mobile wake-up integration | Not implemented | None. | APNs/FCM/OS integration remains future work. |

## Deployment and extension alignment

| Requirement | Status | Evidence | Gap |
|---|---|---|---|
| Enterprise identity and fine-grained policy as extension | Confirmed functional | Ed25519 workload identity, OPA default deny, scoped route tickets, Envoy ext_authz, and fixed backend route pass live Compose scenarios. | Production identity, replay prevention, audit, and HA absent. |
| Regional Kubernetes reference | Partially functional | Fresh Kind v1.35 deployment uses checksum-verified Calico; all pods ready, zero restarts, exhaustive allow/deny probes pass. | Single-node/single-replica; no zone-aware HA, autoscaling, observability, GitOps, or chaos SLO. |
| Signed name ownership/delegation | Not implemented | Local operator registry only. | No auditable ownership hierarchy. |
| Multi-operator federation | Not implemented | None. | Trust, routing, revocation, and policy exchange absent. |
| Privacy-minimized metadata | Partially functional | Payload inspection is absent and clients do not receive origin addresses. | Name/destination retention, minimization, and operator privacy controls absent. |
| Source and destination DDoS enforcement | Partially functional | Bounded local admission and destination default-deny exist. | No participating ISP deployment or distributed abuse/reputation service. |

## Vision v2 roadmap position

| Phase | Status | Exit criterion assessment |
|---|---|---|
| Phase 0 - Vision lock | Confirmed functional | Authoritative PDF, terminology, invariants, state-machine draft, and anti-drift status are in the repository. |
| Phase 1 - Core client/server | Partially functional | A client connects by registered name without receiving the durable backend IP, but native naming and tunnel conformance are incomplete. |
| Phase 2 - Lifecycle | Not implemented | Renewal, key rotation, migration, and resumption exit criterion is not met. |
| Phase 3 - Regional Kubernetes | Partially functional | Least-privilege reference deployment works locally; HA/zone failure exit criterion is not met. |
| Phase 4 - ISP lab | Partially functional | Local ISP-shaped route exists; no real ISP source/destination isolation experiment. |
| Phase 5 - Federation | Not implemented | No cross-domain route, trust, or revocation. |
| Phase 6 - Enterprise extensions | Partially functional | Strong authorization proof of concept; production identity/compliance requirements remain. |
| Phase 7 - Standardization | Not implemented | No normative draft, full conformance suite, or two independent implementations. |

## Anti-drift conclusions

- New requests must begin with a registered name, never an arbitrary
  destination.
- Native security properties cannot be disabled.
- Enterprise identity can add policy but cannot become a prerequisite for the
  core ISP-capable path.
- Kubernetes remains a deployment option.
- DNS may remain a controlled compatibility/bootstrap mechanism while native
  ownership/delegation is designed, but it is not the permanent North Star.
- No roadmap item is complete merely because a local TLS relay or policy demo
  exists.
