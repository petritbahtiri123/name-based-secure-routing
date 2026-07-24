# NBSR Protocol Vision v2 conformance matrix

## Status

This matrix compares the hardened prototype with **NBSR Protocol Vision v2**,
prepared 2026-07-23. It is an implementation-status record, not a native NBSR
conformance certificate. Vision v2 explicitly says that name routing alone is
insufficient without the complete mandatory secure-tunnel properties; this
repository therefore does not claim full conformance.

Status meanings:

- **Implemented**: exercised behavior exists in this prototype at its stated
  scale.
- **Partial**: a vertical slice or one required property exists, but the Vision
  v2 requirement is broader.
- **Not implemented**: no credible implementation is present.

## Core protocol and architecture

| Vision v2 requirement | Status | Repository evidence and gap |
|---|---|---|
| Application requests a name, not a destination IP | Implemented | The name-route API accepts a hostname and returns only synthetic compatibility addresses plus a signed route binding. |
| Native naming without conventional DNS in the critical path | Partial | The client-side contract is name-first, but the relay currently uses operating-system resolution for the approved origin. Native ownership, delegation, and registry semantics are not implemented. |
| NBSR client discovery and secure peer establishment | Partial | Configured gateway endpoints use verified TLS; regional discovery, signed discovery, and federation are absent. |
| Mandatory authenticated, encrypted, integrity-protected route transport | Partial | All client-facing control, gateway, and relay paths require server-authenticated TLS, the relay client requires TLS 1.3, and ISP admission uses Ed25519 proof-of-possession. There is no certified native tunnel profile, full mutual peer identity, or conformance state machine. |
| Name-bound route or tunnel creation | Implemented | EdDSA bindings cover hostname, synthetic addresses, gateway, capability-derived ports, expiry, route ID, and the client-session key thumbprint. |
| Gateway and regional selection | Partial | The Windows prototype can try ordered authenticated relay endpoints; dynamic regional selection and multi-region routing are absent. |
| Source and destination enforcement hooks | Partial | Per-client/global admission, relay destination policy, ticket enforcement, and Kubernetes peer policy exist. ISP-to-ISP source and destination enforcement does not. |
| DNS coexistence during migration | Implemented | The Windows loopback DNS adapter and gateway-side resolver demonstrate coexistence while keeping resolved origin addresses out of client-visible route state. |
| Platform-neutral protocol | Partial | Shared Python services run in Compose and Kubernetes, but the only client adapter is a Windows-first loopback prototype and there are no independent implementations. |
| Kubernetes is a reference deployment, not a dependency | Implemented | The same protocol core runs through Docker Compose; Kubernetes manifests do not define the wire format. |

## Tunnel security profile

| Mandatory property | Status | Repository evidence and gap |
|---|---|---|
| Peer authentication | Partial | Server certificates authenticate control and relay endpoints; Ed25519 proves possession of the client session key. Production identity, trust distribution, and mutual infrastructure authentication are absent. |
| Confidentiality and integrity | Partial | Outer TLS protects NBSR client-facing transport and HTTPS remains end-to-end through an opaque relay. Internal demo service hops are isolated but not all mutually encrypted. |
| Forward secrecy | Partial | TLS 1.3 is required, but no NBSR transport-profile certification or key-rotation state machine exists. |
| Anti-replay | Partial | Relay nonce replay is rejected within a bounded process-local cache. Durable regional replay state and enterprise-ticket replay prevention are absent. |
| Downgrade resistance | Partial | The relay client disables TLS versions below 1.3. The HTTP control/gateway profile and protocol-version downgrade signaling are not yet defined as a native conformance contract. |
| Key rotation without stream interruption | Not implemented | Bootstrap regenerates demo credentials; active tunnel key rotation is absent. |
| Cryptographic name binding | Implemented | The signed route binding and proof context cover the requested name, route ID, gateway, session key, and allowed ports. |

## Lifecycle, mobility, and streams

| Vision v2 requirement | Status | Repository evidence and gap |
|---|---|---|
| Distinct lease and active-stream semantics | Partial | Bindings expire and new admissions require a fresh binding; an admitted byte relay may finish after lease expiry. There is no general stream/tunnel model. |
| Renewal during active transfer | Not implemented | No lease-renewal protocol or revalidation state machine exists. |
| Idle timeout and maximum tunnel lifetime | Partial | Admission and handshake deadlines exist; complete tunnel lifecycle timers do not. |
| Multiplexed streams | Not implemented | Each prototype relay connection carries one TCP flow. |
| Migration, failover, and resumption | Partial | Ordered gateway retry exists before admission. Live path migration and resumable encrypted sessions do not. |
| Mobile wake-up integration | Not implemented | APNs, FCM, and OS runtime integration are outside this prototype. |

## ISP, enterprise, Kubernetes, and federation

| Vision v2 requirement | Status | Repository evidence and gap |
|---|---|---|
| ISP-capable core without enterprise IAM | Partial | The public ISP profile requires no enterprise JWT, billing, or content inspection. It is a local single-operator vertical slice, not an ISP lab. |
| Source-side and destination-side DDoS enforcement | Partial | Admission limits and destination policy exist; federated edge identification, independent destination admission, and distributed abuse controls do not. |
| Backend concealment | Implemented | Name-route responses and Windows mapping state omit origin addresses; protected services have no host port and accept only named deployment paths. The gateway operator still observes names and destinations. |
| Enterprise identity and fine-grained authorization as extensions | Implemented | Separate Ed25519 identities, OPA policy, and method/path/service tickets remain an optional enterprise profile rather than a prerequisite for ISP name routing. |
| Regional Kubernetes HA, autoscaling, observability, and failure handling | Partial | A least-privilege, live-tested Kind reference deployment exists. It uses single replicas and does not implement zone-aware HA, autoscaling, GitOps, observability, or chaos SLO tests. |
| Signed name ownership and delegation | Not implemented | No authoritative NBSR registry or ownership protocol exists. |
| Multi-operator federation and revocation distribution | Not implemented | No cross-domain trust, route federation, or revocation distribution exists. |
| Privacy-minimized routing metadata | Partial | Payload inspection is absent and origin addresses stay client-hidden, but the gateway sees requested names and resolved destinations; retention controls are not implemented. |

## Roadmap position

The hardened code is best described as:

- a strong **Phase 1 vertical slice** for name-first routing and hidden origin
  addressing;
- a partial **Phase 4/6 experiment** for rate limits and enterprise policy; and
- an early **Phase 3 reference deployment** without HA.

It has not met the exit criteria for Vision v2 Phase 2 lifecycle, Phase 3
regional resilience, Phase 4 ISP isolation, Phase 5 federation, or Phase 7
standardization. The next protocol work should define the native discovery and
state machine, a reviewed tunnel profile, renewal/revocation/migration
semantics, and conformance tests before expanding platform integrations.
