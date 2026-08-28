# NBSR end-to-end demo evidence

This record is a reviewed summary of the ignored machine bundle `nbsr-end-to-end-demo-evidence-v1`. Categories are deliberately separate: **LIVE DEMO**, **INTEGRATION TEST**, and **REGRESSION TEST**.

## Provenance

- Baseline/source commit: `19f6468f77175adcb7ad410c2016aa889b964dc0`
- Branch: `codex/nbsr-v3-wp0-wp1`
- Final run: `task7-final-20260828-a`
- Platform: Windows loopback
- Production executable source dirty: no; Task 7 worktree changes are verifier, tests, and documentation only.
- Go: `go1.26.5 windows/amd64`
- Rust: `rustc 1.97.1 (8bab26f4f 2026-07-14)`
- Cargo: `cargo 1.97.1 (c980f4866 2026-06-30)`
- PowerShell: `7.6.4`
- Python: `3.14.6`

## Exact launched binary identity — LIVE DEMO

Only SHA-256 identities are public evidence; operator-owned filesystem paths are excluded.

| Component | SHA-256 |
|---|---|
| Demo authority | `344e9bb9652e5619cf652ccde40deb6ae7fc7df3df9e64b73a9d61c6506e2a2f` |
| Demo client | `d035de1d10ce46e8912b511395d61dbbb334f48578c1f9039549bc2df8db64b1` |
| Deterministic backend | `460b8affa2ed4f0accbb4db742de0d03b0c0280b67f5e4493c97651811f6992b` |
| Rust destination | `10f114ebbe47560f16992d69a5df30969ce5d44ad1f17807b41c97db64bdf122` |

## Positive route — LIVE DEMO

- Requested and canonical name: `service-a.nbsr.test`
- Port: `8080`
- ServiceDigest: `07ed4ff0a2365cc91649cf8a9405d2f1cd1261fcb201a922acdbf4f4bcf213b5`
- Synthetic IP: `127.0.0.2`
- Response: `hello from service-a through NBSR`
- Response SHA-256: `118f23b81f99bf29783c86760ac0e63feb23063d894997582633151c2419f217`
- Backend invocations: `1`
- Result: `PASS`

The final evidence records PASS for every required live stage: resolution/canonicalization, Mapping acquisition, FlowContext correlation, authority verification, active TS, independently authorized SC, Stream Credit admission, Application Stream admission, and backend response return. The Task 4 real-route integration gate independently covers actual TS proof/RoutePlan, AuthorityKey, TLS 1.3/HTTP2 ACP, Manager/Verifier RouteGrant validation, QUIC v1, actual StreamID, same-stream ACCEPT/final authority barrier, and Go/quic-go → Rust/Quinn delivery.

## Negative matrix — REGRESSION TEST

| Scenario | Result | Backend | Fallback | Replay | Cleanup |
|---|---:|---:|---:|---:|---:|
| Unknown service denied | PASS | 0 | 0 | 0 | CLEAN |
| Authority denied | PASS | 0 | 0 | 0 | CLEAN |
| ServiceDigest mismatch | PASS | 0 | 0 | 0 | CLEAN |
| Expired Mapping | PASS | 0 | 0 | 0 | CLEAN |
| Direct backend unavailable | PASS | 0 | 0 | 0 | CLEAN |

Unknown service opens no route. Authority denial exercises stale-generation denial. Digest mismatch exercises signed service-binding rejection. Mapping expiry uses the deterministic exact-expiry lifecycle. No case retries or transitions to a direct route.

`DIRECT_BACKEND_PATH = UNAVAILABLE BY TOPOLOGY`: the backend has no network listener, is destination-spawned only after admission, and is not represented by an application/client Origin Endpoint.

## Shared-IP isolation — REGRESSION TEST

`TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd` passed with:

- `payments.example` and `storage.example`
- shared Synthetic IP `127.80.0.1`
- same port `443`
- distinct ServiceDigest and Mapping provenance
- cross-correlation `0`

This proves existing shared-Synthetic-IP/same-port correlation semantics. It is not a live Service A/Service B demonstration. `SERVICE_B_LIVE_DEMO = NO — POST-DEMO`.

## Cleanup — LIVE DEMO and INTEGRATION TEST

Lifecycle is `STOPPED`; cleanup is `CLEAN`. FlowStore entries, Mapping references, proxy active connections, sessions, channels, streams, pending admissions, backend children, owned processes, and active locks are all `0`.

## Privacy

The final JSON validator uses exact allowlisted structures and rejects forbidden fields, paths, private material, raw RouteGrant/proof data, credentials/tokens, and raw MappingID/LocalFlowID values. The focused scan covered the final JSON, application output, normal logs, safe readiness files, and this public evidence record: `12` files, `0` forbidden matches.

Task 5 `state.json` is **PRIVATE / OPERATOR-OWNED ORCHESTRATION METADATA**. It may retain process/executable/build/readiness paths, hashes, and PID identity for provenance, rollback, PID-reuse safety, and safe stop. Those values are not application-visible and were not copied here. A filesystem executable path is not an Origin Endpoint.

## Verification matrix

- `python -m pytest tests/demo -q` — 60 passed.
- Task 4 focused real-route/cancellation/rejection/no-fallback matrix — PASS.
- Task 5 PowerShell focused tests and fresh start/run/stop — PASS.
- Task 6 pytest, Go Task 6, exact Mapping expiry, shared-IP isolation, and explicit verifier — PASS.
- Production/demo/wirepeer full Go tests, targeted race, vet, and tidy diff — PASS.
- Rust locked release build, fmt, all-target check, clippy with warnings denied, and all-target tests — PASS.
- Live P1F/P2D Go↔Rust verifier — 7 cases PASS with the required
  `benchmark-harness` build. The recorded Task 7 interop run used Rust SHA-256
  `9310823f9db1daa0442d9900fab7c8f239aac38e75d86cd4732ebb2bd87f57c2`
  and Go SHA-256
  `31fd4c7407a3c4efefc8056b5881c7dd07d6041864c330b59dd3bb8e2531a945`.
  The fresh publication-gate rebuild also passed 7/7 with the same Go binary
  and Rust SHA-256
  `bf6307585d39561a4af0329b52dea422596c64d9b41d00bd4ffae585b2a2adb6`;
  the different Rust hash is consistent with the explicit non-bit-identical
  build limitation. These are interop binaries, not the live demo binaries.
- Frozen protocol/schema/vector/registry and dependency paths — unchanged.

## Claim taxonomy

**DEMONSTRATED:** the local explicit-proxy live path, one admitted backend response, topology-enforced lack of direct backend route, cleanup, evidence privacy, and fresh local build/test reproducibility on this checkout/toolchain.

**IMPLEMENTED BUT NOT DEMONSTRATED HERE:** same-IP/same-port two-service correlation and mandatory negative behavior are integration/regression evidence, not additional live Task 7 requests. Other repository protocol capabilities are outside this evidence record.

**DEMO FIXTURE:** local deterministic providers and trust material listed in the operator document.

**NOT IMPLEMENTED / FUTURE:** production provider deployments and the live second-service fixture described in the limitations document.
