# NBSR end-to-end demo

## Purpose

This is a local Windows correctness and security demonstration of the NBSR explicit-proxy route. It is not a production deployment, performance benchmark, transparent network interceptor, or production control plane.

## What this demo demonstrates

**DEMONSTRATED:** a bounded .NET `TcpClient` HTTP CONNECT request for `service-a.nbsr.test:8080` enters a loopback explicit proxy and completes the current secure-route path:

application driver → canonicalization and ServiceDigest → deterministic ResolutionResult → shared Synthetic IP → immutable Mapping → single-use FlowContext → opaque MappedRoute → actual TS proof and RoutePlan → AuthorityKey → TLS 1.3/HTTP2 Source Operator ACP → independent Manager/Verifier RouteGrant validation → QUIC v1 Transport Session → independently authorized Service Channel → Stream Credit → actual StreamID → same-stream ACCEPT → final authority barrier → Application Stream → Rust/Quinn destination → destination-only admitted backend → same-stream response.

The exact response is `hello from service-a through NBSR`. The configured live Synthetic IP is `127.0.0.2`. The backend has no network listener and is started by the destination only after admission.

## Architecture and topology

All network endpoints are ephemeral loopback listeners. The application knows only the explicit proxy and requested service name. The client has no Origin Endpoint or direct backend dialer. The Rust destination accepts the NBSR QUIC/TLS connection, performs destination admission, and then starts one fixed private backend child for the admitted service.

`DIRECT_BACKEND_PATH = UNAVAILABLE BY TOPOLOGY`. This is structural network unreachability, not secrecy of a filesystem path.

## Trust boundaries

The Source Operator ACP uses TLS 1.3 and HTTP/2. Its signed result is independently checked by the client Manager/Verifier. Transport Session, Service Channel, Stream Credit, Application Stream, and destination admission remain separate checks. No application payload is delivered before same-stream ACCEPT and the final authority barrier.

The local fixtures replace sources of information and trust material; they do not bypass canonicalization, Mapping lifecycle, RouteGrant verification, TS proof continuity, SC authorization, Stream Credit, Application Stream admission, or destination admission.

## Windows prerequisites

- Windows with PowerShell 7 or newer.
- Git, Go, Cargo, and Rust available on `PATH`.
- Repository branch `codex/nbsr-v3-wp0-wp1`.
- External build storage under `C:\NBSR-build`.
- No active Task 5 demo run.

## Start

From the repository root, choose a new bounded run ID:

```powershell
$runId = 'demo-review-001'
pwsh -NoProfile -File scripts/demo/start-nbsr-demo.ps1 -RunId $runId
$state = Join-Path (Resolve-Path client/nbsr-go-client/demo/test-results/nbsr-demo/runtime) "$runId/state.json"
```

Startup builds the three Go executables and the Rust destination from the current checkout, creates short-lived per-run trust material, starts authority → destination → client, validates readiness, and prints the exact state path. Never select a state by recency.

## Run

```powershell
pwsh -NoProfile -File scripts/demo/run-nbsr-demo.ps1 -StatePath $state
```

The one-shot driver permits one application request per active lifecycle.

## Stop

```powershell
pwsh -NoProfile -File scripts/demo/stop-nbsr-demo.ps1 -StatePath $state
```

Stop verifies process identity, terminates only owned processes, records `STOPPED`, and removes the active lock. Repeated stop is idempotent.

## Expected output

```text
NBSR demo: PASS
Service: service-a.nbsr.test
Path: NBSR secure route
Response: hello from service-a through NBSR
```

## Verify Task 6 and Task 7 evidence

Task 6 validates the negative matrix against one explicit Task 6 STOPPED state:

```powershell
python scripts/demo/verify-nbsr-demo.py --state C:\absolute\task6-run\state.json --output C:\absolute\task6-run\task6-result.json
```

Task 7 emits the separate closed final schema against one explicit Task 7 STOPPED state:

```powershell
python scripts/demo/verify-nbsr-demo.py --final --state $state --output (Join-Path (Split-Path $state) 'nbsr-end-to-end-demo-evidence-v1.json')
python -m pytest tests/demo -q
```

The generated JSON remains in ignored runtime storage. It contains allowlisted hashes, identity, stages, results, and zero/idle counters—not executable paths, private material, raw grants/proofs, or internal correlation IDs.

## Cleanup behavior

Final evidence requires `STOPPED`, no owned process or active lock, and zero FlowStore entries, Mapping references, proxy connections, sessions, channels, streams, pending admissions, and backend children. A RUNNING state cannot produce final clean evidence.

## Demo fixtures

**DEMO FIXTURE:** deterministic resolution/catalog input; local Source Operator ACP signer and policy; enrolled-client bootstrap state; local destination trust/admission configuration; one fixed destination-private backend binding; and short-lived locally generated certificates/trust material.

Future production resolver/control-plane, enrollment/storage, Source Operator ACP, and federation/operator trust-distribution providers may replace these fixture providers within the reviewed architecture boundary without rewriting the demonstrated Mapping/FlowContext core, MappedRoute, RoutePlan, AuthorityKey, HTTPProvider, Manager/Verifier, TS, SC, Stream Credit, Application Stream, or destination-admission semantics. Those production provider systems are not implemented by this demo.

## Scope boundary

The live demo has one service fixture. `SERVICE_B_LIVE_DEMO = NO — POST-DEMO`. Same-IP/same-port multi-service isolation is demonstrated by an existing regression, not by a live Service A/Service B run. See [evidence](nbsr-end-to-end-demo-evidence.md) and [limitations](nbsr-end-to-end-demo-limitations.md).
