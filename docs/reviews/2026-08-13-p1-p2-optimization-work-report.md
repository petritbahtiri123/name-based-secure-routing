# NBSR P1–P2 Optimization Work Report

## Technical summary

The local P1A→P2D program produced a complete linear history on
`codex/nbsr-v3-wp0-wp1`. The work first isolated retained-memory ownership,
proved that a finite sliding replay window cannot preserve the frozen replay
semantics, added the accepted P1F hard cap, established/profiled the data plane,
rejected P2C because its tail-latency cost failed the fixed gate, and accepted
P2D stream credits after an exact-final-source campaign.

The strongest measured optimization result is P2D Attempt 8: median throughput
increased from 4,282.05 to 15,567.44 operations/second (+263.55%) while median
p99 fell from 18.6981 ms to 5.4623 ms (-70.79%). These are Windows loopback lab
measurements for the exact recorded source and are not cloud, WAN, production,
or general deployment claims.

## Work preserved in the consolidated branch

| Stage | Local tip | Result |
|---|---:|---|
| Pre-V3 hardening | `c0ade42` | Historical base retained |
| P1A source memory attribution | `275315e` | Diagnostic evidence retained; no leak claim |
| P1B destination memory attribution | `23f3b44` | Retained capacity attributed to `used_stream_ids` |
| P1C bounded replay design | `a13ead6` | No finite sliding/high-water model preserves frozen semantics |
| P1D session rotation | `611e828` | Design blocker; no speculative production implementation |
| P1E active/standby rotation | `aa41bd0` | Code-level protocol blocker recorded |
| P1F replay hard cap | `55a5de9` | Accepted exact fail-closed 10,000-entry cap |
| P2A established data-plane baseline | `a19b685` | Persistent Rust baseline established |
| P2B stream-establishment profile | `e82b7cf` | Lifecycle cost ownership measured |
| P2C pipelined STREAM_OPEN | `366bbfc` | Implemented experimentally, rejected, production change reverted |
| P2D stream-credit window | `e62af52` | Accepted optimization; Attempt 8 is sole authority |
| Reconciliation design and plan | `0f95884` | Current local consolidated tip before this report |

Every listed tip was freshly verified as an ancestor of the consolidated
branch before publication was attempted. The branches therefore do not require
separate merge commits: pushing the consolidated tip preserves their complete
ordered history.

## Memory and replay findings

The memory work did not justify calling the observed growth a Quinn leak. The
durable closure retained `INCONCLUSIVE` classifications where the frozen
boundedness or reproducible-growth gates were not met. P1B localized retained
capacity to the session-wide replay set, while P1C demonstrated why eviction,
sliding windows, or a high-water rule would change replay behavior.

P1F addressed resource exhaustion without deleting accepted replay history:
fresh valid stream IDs reject before commit or upstream effects when the exact
10,000-entry session budget is full. Duplicate precedence and previously
committed history remain intact. This is a bounded-session policy, not replay
expiry and not silent eviction.

## Optimization results

| Candidate | Throughput result | p99 result | Decision |
|---|---:|---:|---|
| P2C bounded admission pipeline, window 2 | +23.64% median | +41.68% median regression | **Rejected and reverted** |
| P2D V1 stream credits, concurrency 64 | +263.55% median | -70.79% median | **Accepted** |

P2C proved that overlapping ordered source admissions can increase aggregate
throughput, but queueing raised median p99 from 0.394 ms to 0.5582 ms. The fixed
limit allowed at most +5%; the observed +41.68% therefore failed by a wide
margin. No soak was run and the production candidate was reverted.

P2D removed repeated per-stream control admission from the critical path using
64 exact-once credits and bounded refill on the existing authenticated control
stream. Attempt 8 recorded five matched 60-second pairs, a 300.387-second soak,
16 continuity windows, correct 1 KiB echo payloads, and zero unexpected errors.
The measured soak rate was 16,085.92 operations/second. The replay limit was
exactly 10,000 at all 2,726 audited endpoints across 1,363 shards; any different
value was defined as FAIL.

## Security properties retained

- V1 negotiation cannot silently downgrade or enter legacy stream paths.
- Stream admission uses actual Quinn stream handles, never arithmetic ID prediction.
- Application payload remains quarantined until same-stream ACCEPT.
- Credits remain bound to session, channel, route, grant, generation, slot,
  stream ID, and revocation state.
- Revocation dominates unused credit; rejected capacity/audit operations do not
  consume credit or mutate replay state.
- Refill uses the sole ordered authenticated control stream and bounded epoch
  state; a third epoch and epoch wrap reject fail closed.
- P1F's exact replay hard cap remains mandatory in every authoritative P2D path.
- Rejected P2C production behavior remains absent from the final tree.

## Fresh repository-gate status

The optimization-specific Rust gate is green: a fresh all-target run with the
benchmark harness produced 180 passed, 0 failed, and 1 ignored evidence-only
soak. The current full Python repository gate is not green: 1,795 passed,
38 failed, and 1 skipped.

The Python failures cluster around Windows checkout byte conversion under
global `core.autocrlf=true`, historical Core/F75 authority locks that do not yet
cover later accepted P1/P2 source edits, generated-vector digest drift, and one
Windows Application Control block (`os error 4551`) in the cross-process Rust
build. These failures are being treated as real gates. No frozen authority will
be rewritten merely to obtain a passing count, and the live wire test will not
be skipped or mislabeled PASS.

## Scope and limitations

- Measurements are unoptimized/optimized Windows loopback lab evidence on one
  host, not same-region, cross-region, WAN, cloud, or production evidence.
- P2D figures apply only to the exact Attempt 8 source, configuration, payload,
  concurrency, and evidence package.
- Memory stability remains bounded by the recorded PASS/FAIL/INCONCLUSIVE
  methodology; ambiguous cells remain `INCONCLUSIVE`.
- The report does not claim that all repository tests currently pass.

## Next actions

1. Complete the remote backup of the consolidated working branch without
   modifying `main`.
2. Make byte-locked checkout behavior deterministic and rerun representative
   authority/vector tests from a fresh checkout.
3. Inventory the exact remaining P1/P2-vs-F75 authority delta and require
   explicit approval before activating any additive overlay.
4. Run the cross-process wire test from the allowed external Cargo target.
5. Run full Python, Rust, lint, vector, LFS, and protected-ref gates; publish the
   final repair commits only after exact verification.

## Evidence used

- `evidence/performance/pipelined-stream-open-p2c/final-report.md`
- `evidence/performance/stream-credit-window-p2d/final-report.md`
- `evidence/performance/stream-credit-window-p2d/security-matrix.md`
- `evidence/performance/bounded-replay-design-p1c/report.md`
- `evidence/performance/rust-session-rotation-p1d/report.md`
- `evidence/performance/loopback-completion-3188c7c/reports/latency-and-performance-validation.md`
- `evidence/performance/memory-closure-00ed052/reports/memory-completion.md`
