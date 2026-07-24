# NBSR security hardening report

## Scope and evidence status

This report covers the July 2026 hardening of the Build Week enterprise
authorization prototype, ISP name-routing vertical slice, Windows prototype
adapter, Docker Compose deployment, and Kubernetes/Kind reference deployment.
It does not claim production readiness or full NBSR Protocol Vision v2
conformance.

Codex Security scan
`31dd72ff-236a-4f72-ba35-44d89f481e79` completed its analysis and produced 15
closure records, 11 validated findings, coverage data, and a hardening
portfolio. The scanner's terminal orchestration failed while sealing the run,
so the UI did not record a final sealed state. The saved canonical artifacts
were schema-validated in dry-run mode and were used as the remediation input;
the seal failure is an evidence-handling limitation, not a claim that the scan
completed normally.

## Finding dispositions

| ID | Severity | Boundary | Disposition | Verification |
|---|---|---|---|---|
| SEC-002 | High | Relay SSRF and DNS rebinding | Fixed. Every resolved literal is rechecked immediately before connect; non-global destinations require an exact trusted-origin hostname/network rule. | Destination-policy unit tests and relay rebinding regression |
| SEC-003 | Low | Optional relay TLS | Fixed. The Windows relay client always creates a verifying TLS context, requires a CA or system trust, checks the hostname, and requires TLS 1.3. | Windows-agent TLS and untrusted-certificate tests |
| SEC-004 | Medium | Plain enterprise control API | Fixed. Control-plane credentials and route grants use server-authenticated TLS. | HTTPS client tests, Compose config, and live plaintext rejection |
| SEC-005 | Low | Plain enterprise gateway | Fixed. Envoy serves the client-facing gateway with TLS and dedicated key material. | Envoy config, client tests, and live plaintext rejection |
| SEC-006 | Low | Exposed Envoy administration | Fixed. The admin listener binds only to container loopback and is not published. | Envoy config review and network reachability check |
| SEC-007 | Low | Broad Kubernetes network policy | Fixed. Namespace-wide arbitrary egress was replaced by workload-specific peer and port policies. | Manifest regression tests and live allowed/denied Kind probes |
| SEC-009 | Medium | Local credential permissions | Fixed for the prototype. Private keys, tokens, and the Windows journal use atomic protected writes and restricted permissions/DACLs. | Cross-platform secure-file tests |
| SEC-010 | Medium | Docker build-context leakage | Fixed. `.dockerignore` excludes Git data, credentials, caches, logs, archives, and generated artifacts. | Scratch build-context archive audit |
| SEC-011 | Medium | Synthetic allocator exhaustion | Fixed for one process. Allocation uses bounded indexed state and expiry heaps instead of repeated network scans. | Capacity, expiry, and no-linear-scan tests |
| SEC-012 | Medium | Unbounded relay replay cache | Fixed for one process. Replay state has capacity and expiry bounds and fails closed when full. | Replay capacity and expiry tests |
| SEC-014 | Medium | Client-controlled verifier metadata | Fixed. The verifier uses the actual method/path of Envoy's ext-authz request; Envoy overrides a fixed service header inside that request. | Spoof, duplicate, missing-header, and scope tests |
| SEC-008 | Deferred during scan | Kind CNI enforcement uncertainty | Closed by implementation validation. Kind 0.24+ provides network-policy support; the workflow pins a v1.35.0 node image by digest and tests both permit and deny paths live. | `scripts/verify-kind-security.*` on Kind 0.32.0 |

SEC-001, SEC-013, and SEC-015 were rejected or ignored during validation and
were not carried into the remediation finding set. This report does not
reclassify them as vulnerabilities.

## Structural controls added

- Dedicated enterprise and ISP TLS trust domains and server keys.
- Strict request-context boundary between Envoy and the ticket verifier.
- Global-unicast relay policy with explicit, exact private-origin exceptions.
- Capability-to-port binding for HTTP/80 and HTTPS/443.
- Bounded admission, replay, and synthetic-address state.
- Atomic owner-restricted writes for local private material and journals.
- Minimal Docker build context.
- Default-deny Kubernetes isolation with explicit workload flows.
- Digest-pinned Kind node image and executable enforcement probes.

## Validation results

The hardened branch produced the following observed results on 2026-07-25:

- `python -m pytest -q`: 180 passed, 1 skipped, with 12 upstream
  FastAPI/Uvicorn deprecation warnings under Python 3.14.
- `python -m ruff check .`: all checks passed.
- `opa test /policy -v`: 5 of 5 policy tests passed.
- `docker compose config --quiet`, a fresh `docker compose build`, and Envoy
  `--mode validate`: passed.
- Enterprise live demo: all eight allow/deny scenarios passed, including
  tampering, expiry, scope escalation, and direct-backend denial.
- ISP live demo: relayed HTTP/80 and HTTPS/443 both passed; the client-visible
  state omitted the origin address and the origin observed the relay peer.
- Additional live negative checks: plaintext on the two TLS ports was rejected,
  spoofed route-context headers could not authorize a different method/path,
  and Envoy's port 9901 was unreachable from the client network.
- Kind 0.32.0 with the digest-pinned Kubernetes v1.35.0 node image: all eight
  pods became ready with zero restarts, 13 NetworkPolicies were present,
  required paths passed, and both tested forbidden paths were denied.

The distributable archive is rechecked after extraction because its SHA-256
depends on the final commit. Its exact path and digest belong in the branch
handoff rather than this source-controlled report.

## Residual risk

The prototype still lacks distributed replay/revocation state, HA, production
PKI and rotation, HSM/KMS protection, enterprise ticket channel binding,
signed name ownership, federation, QUIC/HTTP3, arbitrary UDP, raw IP tunnels,
and a signed Windows Filtering Platform adapter. The ISP operator necessarily
observes requested names and resolved destinations. These are explicit scope
limits, not implicitly completed features.
