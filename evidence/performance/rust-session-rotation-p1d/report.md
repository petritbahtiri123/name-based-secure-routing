# NBSR Performance Task P1D — Bounded Transport-Session Rotation

## Executive summary

**Outcome C — DESIGN BLOCKED BY FROZEN PROTOCOL/OWNERSHIP SEMANTICS.** No production fix was implemented, kept, or reverted. The existing protocol securely supports an independently authenticated TS-B and independently authorized SC-B, and the adversarial model preserves replay and authority separation. It does not define the production owner that acquires fresh RouteGrants before cutover, atomically selects TS-B for new application flows, fans revocation across both generations, and drains TS-A invisibly. Gates 3 and 5 therefore fail.

Measured production effect: **not measured / not eligible**. The conditional implementation gate failed before production edits, so running smoke, five paired BEFORE/AFTER cells, or a long rotating-session campaign would have measured a nonexistent/speculative implementation.

## Git boundaries

- Branch: `codex/nbsr-perf-p1d-session-rotation`
- Base SHA: `a13ead66e65896260a44da19da0ae27b0c98cd96`
- P1C parent: `23f3b4457e33061c96511e4f29121ef78c0d7bb9`
- Underlying accepted product SHA: `4e25ee026618a502327331f352d90e26d29284e3`
- Final SHA: recorded in the final handoff because a commit cannot contain its own SHA
- Remote `main`, pre/post: `1938154d498b32d81a3564319969430644e8a688`
- Remote accepted branch `codex/nbsr-v3-wp0-wp1`, pre/post: `4e25ee026618a502327331f352d90e26d29284e3`
- Push/force-push/merge/rebase/pull: none
- Final status: required clean after the local outcome-C commit

## Root cause carried from P1B/P1C

The destination `ChannelStreams.used_stream_ids` inserts one ID for each successfully committed Application Stream and retains it until `ControlSession` drop. Frozen semantics allow a fresh lower stream ID after a higher ID, reject an arbitrarily old committed duplicate, preserve history across sibling Service Channels and channel release/reset/revoke/close, and permit retry only when the original attempt failed before commit. Thus a high-water mark falsely rejects valid traffic, while any finite window either falsely rejects a fresh below-window ID or accepts an indistinguishable old replay. Direct HashSet bounding is not safe.

## Rotation security proof

- **TS-A authority:** exact authenticated connection capability/exporter, session ID, nonces/session key, request/sequence history, SC-A channel/route/grant/nonce, stream permits, and full committed stream history remain TS-A-local until retirement.
- **TS-B authority:** a new TLS-authenticated connection, new connection capability, session ID, nonces, request/sequence state, RouteGrant identifiers/digest/nonce, channel ID, and live exporter binding are independently required.
- **Replay boundaries:** committed ID 4 rejects again on TS-A but may be admitted as numeric ID 4 on independently authorized TS-B. No TS-A replay state authorizes TS-B.
- **RouteGrant/channel:** matching numeric or copied TS-A channel/grant fields reject. Existing resumption consume requires different channel ID, route ID, grant digest, and grant nonce.
- **Request ID/sequence:** both are session-local. A consumed request rejects in its session; a non-increasing sequence rejects. Rotation does not turn either into cross-session authority.
- **Resume/migration:** resume records are single-use, preflight is bound to one manager/new session/new connection, and only normally closed old channels can issue. QUIC path migration retains the existing session and is not rotation.
- **Revocation:** model revocation rejects new streams. Production cross-generation revoke fan-out is not defined, contributing to the gate failure.
- **Races:** in-flight TS-A streams remain TS-A-bound; TS-B receives new streams only after admission in the model; failed admission leaves TS-A intact. The application-visible selector/retry synchronization point is absent in production, so ambiguous races fail closed rather than being implemented.

Full path-by-path evidence is in `security-analysis.md`; exact model outcomes are in `model-results.json`.

## Rotation policy

- Exact trigger/configured bound: **none installed**.
- Configured replay-memory budget: **none installed**.
- Reason: a count threshold without a defined transition owner does not produce deterministic safe production rotation.
- Sizing evidence only: P1B observed 52.64-53.19 working-set bytes per committed entry. A hypothetical 16 MiB local budget with 25% margin yields `floor(16 MiB * 0.75 / 53.19) = 236,565` entries. This is not selected, configured, or claimed as a protocol guarantee.

## Production implementation

No production file changed. The secure primitives already present are parallel authenticated connections, independently initialized `ControlSession`s, fresh RouteGrant admission, exporter-bound channels, drain, and strict single-use same-edge resume. Missing is a higher-layer service/session pool and fresh-authority provider. Adding those inside the transport state machine would invent ownership and application semantics, so the conditional gate prohibited it.

## TDD evidence

- RED 1: `python -m pytest tests/performance/test_session_rotation_model.py -q` failed collection with `ModuleNotFoundError` before the model existed.
- GREEN 1: the initial implementation exercised ten tests; one fixture reused both request ID and sequence, correctly reaching the earlier request-replay guard. The fixture was isolated with a fresh request ID.
- RED 2: adding canonical machine-result behavior failed import because `canonical_results` did not exist.
- GREEN 2/final: 11/11 focused model tests passed.

The tests cover old stream replay, fresh cross-session numeric reuse, stale channel/grant rejection, request and sequence replay, single-use resume, failed new admission, exact threshold selection, in-flight drain/release, revocation transition, and the absent production owners.

## Security regression results

Fresh validation used `CARGO_TARGET_DIR=C:\codex-target\nbsr-p1d`:

- Focused `channel_streams` unit tests: 6 passed, 0 failed.
- Focused integration suites: handshake 11, control 1, multi-stream 3, application-stream 4, multi-channel 4, channel-lifecycle 3, drain 12, resumption 17; aggregate 55 passed, 0 failed.
- Focused Rust total: 61 passed, 0 failed.
- P1C + P1D Python models: 18 passed, 0 failed in 4.08 seconds (P1D alone: 11 passed).
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets -- -D warnings`: exit 0.
- Broader serial Rust suite: 142 passed, 0 failed (30 library, 96 integration, 16 doc tests).
- Known Windows baseline failures: none appeared in the relevant suite.

## BEFORE vs AFTER

| Metric | BEFORE | AFTER |
|---|---:|---:|
| Replay entries/capacity | P1B: 1,215,000 / 1,835,008 at 75% run | Not measured; no implementation |
| WS/private bytes | P1B retained proxy: 52.64-53.19 / 44.98-45.78 bytes per entry | Not measured |
| Memory slope | History-linear replay owner | Not measured |
| Rotations | 0 | 0 |
| Throughput | Accepted P1B workload evidence retained | Not measured |
| p50/p95/p99 | Accepted P1B evidence retained | Not measured |
| Errors | Accepted P1B evidence retained | No new runtime cell |
| CPU | Accepted P1B evidence retained | Not measured |

No performance value is extrapolated into an AFTER claim.

## Long-session result

Not run because short-performance validation was ineligible. Current non-rotating replay state remains history-linear during a Transport Session and releases at `ControlSession` destruction. No bounded/sawtooth production claim is made.

## Acceptance gate

| KEEP condition | Result |
|---|---|
| Security tests pass | PASS for design/model and unchanged production |
| Replay equivalence across session boundaries | PASS in model with independent fresh authority |
| Zero new protocol errors | PASS; no production change |
| Old authority cannot resurrect | PASS in model/current resume tests |
| Replay-state growth becomes bounded | FAIL / not implemented |
| Throughput regression <= 5% | INCONCLUSIVE / not measured |
| p99 regression <= 5% | INCONCLUSIVE / not measured |
| No new resource leak | PASS only in the sense no production code changed |
| Complexity justified by benefit | FAIL / no eligible implementation |

Overall KEEP: **FAIL / not applicable**. This is outcome C, not an implementation that reached keep/revert evaluation.

## Evidence integrity

- New evidence: `evidence/performance/rust-session-rotation-p1d/`.
- P1A tree object unchanged: `74caa77ae79cbcb4e0b4a53d95352df3c198aaf1`.
- P1B tree object unchanged: `8b8893dd5347338c8e220b7ede278ba7b15abdbe`.
- P1C tree object unchanged: `5fad03f39f242ce70141f6e2b35e4e7a4795d21b`.
- Checksums cover every P1D evidence file except the checksum manifest itself.
- No new large raw evidence was produced; no P1D file requires Git LFS. Historical LFS evidence was not changed.

## Remaining risks

1. There is no frozen service/session-pool owner for make-before-break flow selection.
2. There is no frozen mechanism for acquiring fresh RouteGrants before active-channel cutover.
3. Revocation fan-out and retry behavior across concurrent session generations are undefined.
4. Memory/latency/throughput benefit remains unmeasured because implementing before resolving 1-3 would be speculative.

## Recommended next task

Define and freeze exactly one **application-facing active/standby Transport Session ownership and fresh-RouteGrant acquisition contract**, including atomic new-flow selection, cross-generation revocation, failure retry, and drain retirement semantics. Do not implement or benchmark it until that contract is approved.
