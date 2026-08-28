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
