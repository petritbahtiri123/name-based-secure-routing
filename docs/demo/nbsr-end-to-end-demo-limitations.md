# NBSR end-to-end demo limitations

The completion claim is limited to an evidence-backed local Windows explicit-proxy demonstration. It is not a claim that NBSR is production-complete or that every protocol capability has a production deployment.

## Demonstrated scope limitations

- Local/loopback only; no WAN or multi-region evidence.
- Explicit local HTTP CONNECT proxy adapter, driven by bounded .NET `TcpClient` code.
- No transparent DNS interception, TUN, WFP, kernel routing, OS-wide interception, or zero-configuration routing.
- TCP application profile only; no UDP or CONNECT-UDP in this demo.
- One live service fixture and one fixed backend/authority binding.
- `SERVICE_B_LIVE_DEMO = NO — POST-DEMO`.
- Shared-IP/same-port two-service isolation is regression evidence for `payments.example` and `storage.example`, not a live Service A/Service B run.
- The live `127.0.0.2:8080` configuration proves use of the shared-IP model for one service; it does not prove live two-service isolation.
- No production resolver/control-plane distribution.
- No production enrollment/storage deployment.
- No production federation/operator trust-distribution deployment.
- No installer, Windows service, daemon packaging, or automatic recovery service.
- No Kubernetes requirement or Kubernetes deployment evidence.
- No performance, capacity, availability, scalability, 100k RPS, or 1M RPS claim.
- Earlier benchmark campaigns remain separate from this correctness/security demonstration.

## Fixture boundary

The deterministic catalog/resolution input, Source Operator ACP signer/policy, enrolled-client bootstrap, destination trust/admission configuration, fixed destination-private backend binding, and short-lived local trust material are **DEMO FIXTURE** providers.

They replace the source of future production information/trust material. They do not skip the demonstrated canonicalization, Mapping/FlowContext, authority verification, TS/SC, Stream Credit, Application Stream, or destination-admission boundaries.

Production resolver/control-plane, enrollment/storage, Source Operator ACP, and federation/trust-distribution implementations are future provider work. The reviewed architecture permits provider replacement without rewriting the demonstrated secure-route core, but this demo does not implement or deploy those production systems.

## Service B

The protocol model is not limited to one service. The present live fixture is. Adding a live second service would expand the already-closed fixture/backend-routing and authority setup; that work is POST-DEMO. No Task 7 evidence relabels the Tranche 6 regression as a live `service-a/service-b` request.

## Backend and privacy boundary

The backend is unreachable directly because it has no network listener and is created only inside the destination after admission. This conclusion does not depend on keeping a filesystem path secret.

Task 5 `state.json` is **PRIVATE / OPERATOR-OWNED ORCHESTRATION METADATA**. Executable/build/process/readiness paths and hashes may exist there for ownership, provenance, PID-reuse protection, rollback, and safe stop. They are not public evidence, application state, normal metrics, or an Origin Endpoint. Operators must not publish that file as Task 7 evidence.

## Build reproducibility boundary

Fresh local Rust builds using Rust/Cargo 1.97.1 and the checked-in lockfile succeeded for the demo and for a separate locked release/full-test target. This demonstrates fresh local build reproducibility for this checkout and toolchain.

It is not bit-for-bit reproducibility across machines, independent supply-chain attestation, hermetic build proof, or formal toolchain provenance certification. Go and Rust dependencies remain those already locked by the repository; Task 7 adds none.

## Evidence boundaries

- LIVE DEMO evidence covers the single positive request and shutdown.
- INTEGRATION TEST evidence covers the complete secure-route component chain and boundary failures.
- REGRESSION TEST evidence covers the negative matrix and two-service same-IP/same-port isolation.
- Fixed public response text is allowlisted; arbitrary application payload is not evidence.
- Internal MappingID, LocalFlowID, channel identifiers, private proof material, credentials, and raw grants are intentionally absent.

## P1 cross-gateway telemetry inspection (2026-11-28)

This subsection retains the initial inspection before implementation. The later
authorized [live Python relay composition](p1-cross-gateway-telemetry.md) now
demonstrates the three cases at its separate fixture scope; it does not relabel
or change the historical Go/Rust demo evidence below.

Inspected source: `840fef10d601f28336afde92f730b539eaf9154f`, isolated branch
`codex/p1-cross-gateway-telemetry`. **P1 is not demonstrated.** No two-gateway
trial was run and no measured cross-gateway request trace is available.
The V3.6 roadmap contains the origin-safe telemetry acceptance requirement,
but this inspection did not locate a separately named "P1 cross-gateway
telemetry" entry in that roadmap. P1 here names the requested task, not a
newly completed roadmap milestone.

### Existing components and exact reuse boundary

| Component | Existing evidence or behavior | Missing for the requested composition |
| --- | --- | --- |
| Go explicit-proxy demo | `demo/internal/client/runtime.go` accepts a real TCP CONNECT flow; `assembly.go` creates a client-owned session targeting `destination.edge` | This is the existing client adapter, not an independently composed gateway A. Treating it as the source gateway is an explicit topology choice, not evidence of another implemented gateway hop. |
| Rust destination | `crates/nbsr-transport/src/bin/wp8_interop_server.rs` supports admission and the destination-private backend; the Go `full_e2e_test.go` composes that path | The existing one-destination demo does not supply the requested three-case, two-gateway receipt and trace join. |
| WP7 two-operator lab | `nbsr/two_operator_lab.py` checks separate operator contexts; `DestinationConnector.connect` returns a capability-bound receipt | It performs no service network delivery. Its connector receipt cannot establish a service observation. |
| WP8 interoperability | Existing source/destination route and stream interoperability is retained | Peer interoperability alone is not a client-to-two-gateways-to-service application trace. |
| Python name relay / enterprise Envoy | `nbsr/name_relay.py` dials the admitted origin directly; `gateway/envoy.yaml` routes to a fixed payments upstream | These are separate paths. The relay does not initiate another relay's authenticated admission handshake. Their composition must not bypass policy or expose the private destination. |
| Existing evidence verifier | `scripts/demo/verify-nbsr-demo.py` checks a closed set of stages, negative results and forbidden fields | Its public stage records contain `stage`, `status`, `scope`; they are not correlated per-request events emitted by two gateways. Do not extend historical evidence to claim P1. |

The nearest existing live topology is application -> Go client proxy -> Rust
destination -> private backend. It is a useful reuse candidate, but this
inspection does not rename the client proxy as an independently established
gateway A. No new protocol fields, trust rules or fallback routes were added.

### Remaining acceptance work

First establish the source-gateway boundary and its client identity/admission
contract, then compose it with the existing destination admission and backend.
Use a bounded diagnostic correlation identifier whose propagation and ownership
are explicit; do not publish internal MappingID, LocalFlowID, credentials,
grants, proofs, raw exceptions, payloads or endpoint-derived identifiers.
Instrument actual decisions and completion, rather than synthesizing stages
from a scenario name. Keep the historical evidence schema unchanged.

| Requested case | Required service observation | Required trace distinction | This inspection |
| --- | --- | --- | --- |
| Allowed | Exactly one request and its expected response | A forwarding, B admission, service completion under the same request identifier | Not run |
| Policy denied at B | Zero requests, after a confirmed B policy decision | B policy denial; no service-completion event | Not run |
| B unavailable | Zero requests with bounded failure and confirmed cleanup | A-to-B connection failure/timeout; no invented B policy event | Not run |

These are acceptance requirements, not sample results. A refusal at the source
authority is not a B policy denial. A transport mock or cancellation test is
not a stopped/unreachable B. Zero requests requires service-side accounting,
not just a client error. There is deliberately no fabricated trace example.

### Reproduce the checks performed

From this isolated checkout in PowerShell:

```powershell
Set-Location C:\Users\bajra\.codex\worktrees\p1-cross-gateway\NBSR
python -m pytest -q -p no:cacheprovider tests/demo/test_nbsr_end_to_end.py tests/demo/test_nbsr_final_evidence.py
git diff --check
```

Observed: **60 passed**, Python 3.14 / pytest 8.4.2. These existing tests use
constructed evidence fixtures. They verify evidence validation, forbidden-field
rejection and rejection of falsely labelled live results; they do not launch
Go/Rust or prove live service delivery or runtime log privacy. No duplicate
tests, dependencies, builds, sockets, VM operations or benchmark runs were added.
There is no verified P1 reproduction command until the composition above exists.

### Repository recovery retained separately

The blocking Codex checkpoint reference contained 41 NUL bytes and had no
reflog. Its original bytes and relative path were retained under the original
repository's `.git/codex-ref-repair-20261128/`, outside `refs`. Backup SHA-256:
`9e1736c43d19118e6ce4302118af337109491ecc52757dfb949bad6a7940b0c2`.
Fetching the requested branch then passed with per-command automatic maintenance
disabled. No original branch, index or working files were reset or cleaned.
This repairs the observed invalid reference; it is not a full repository
integrity certification or recovery of the lost checkpoint SHA.

Managed worktree creation subsequently failed on an unavailable partial-clone
object. A separate branch was created with `git worktree add --no-checkout`,
then a focused sparse checkout was populated and attached to the chat. The
original dirty checkout and unrelated worktrees were left in place. No commit
or push was made. The earlier automatic-maintenance worktree permission failure
was not repaired; no worktree pruning or global Git setting change was attempted.
