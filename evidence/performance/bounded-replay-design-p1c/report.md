# NBSR Performance Task P1C — Security-Preserving Bounded Replay-State Design Investigation

## Executive decision

**C — Current semantics require full historical replay state.** The frozen Core v0.2 rule is that one `quic_stream_id` is opened at most once per Transport Session. Neither the protocol nor the implementation requires `quic_stream_id` to increase with `ControlEnvelope.monotonic_sequence`, and no finite reordering/gap bound exists. Therefore strict high-water and every finite fail-closed sliding window reject a fresh lower identifier that the current oracle accepts. Allowing identifiers below the window instead would accept an indistinguishable old duplicate. No bounded candidate is behaviorally equivalent.

The required decision taxonomy is: A = strict monotonic representation proven equivalent; B = bounded sliding replay window proven equivalent; C = current semantics require full historical replay state; D = protocol semantics are insufficiently frozen to choose safely. This report selects exactly **C**. Candidate representations below are named rather than lettered to avoid confusing them with this decision taxonomy.

This is an investigation and design proof. Production replay code and protocol behavior are unchanged.

## Git boundaries

- Branch: `codex/nbsr-perf-p1c-bounded-replay-design`
- Required and actual base: `23f3b4457e33061c96511e4f29121ef78c0d7bb9`
- Final task SHA: reported in the final handoff because a commit cannot contain its own SHA
- Required remote `main`: `1938154d498b32d81a3564319969430644e8a688`
- Required remote accepted product branch `codex/nbsr-v3-wp0-wp1`: `4e25ee026618a502327331f352d90e26d29284e3`
- No push, merge, rebase, or pull was performed.
- The original checkout and accepted branch histories were not modified.

## Exact replay semantics and semantic trace

### Identifier creation and validation

1. The public control API does not allocate the body ID. The caller supplies `STREAM_OPEN.body.quic_stream_id`; the benchmark source predicts it as `4 + 4 * stream_ordinal`.
2. The body decoder yields a Rust `u64`. `StreamGate` accepts only `4..=2^62-1`, divisible by four: source-initiated bidirectional QUIC IDs with stream 0 reserved for control.
3. Quinn allocates the actual stream when `connection.open_bi()` runs. `open_session_stream` rejects and resets it unless the actual Quinn ID equals the previously authorized permit ID. At destination, `accept_bi()` obtains the actual ID and `authorize_application_stream` requires the same authorized ID before exposing the stream.
4. Numeric gaps are permitted. The frozen document lists `4, 8, 12, and so on` but imposes no contiguity requirement, and the implementation checks range/parity/binding rather than adjacency.
5. QUIC transport retransmission does not duplicate `STREAM_OPEN` at this layer: control messages are ordered bytes on reliable stream 0. An application/adversary can nevertheless send a second control envelope, which is independently replay-checked.

### Admission and commit

1. `ControlSession.authorize_stream_open` first requires an active session, exact established `session_id`, a fresh session-scoped `request_id`, and a strictly increasing source-direction `monotonic_sequence`.
2. It resolves the independently bound active Service Channel, then `ChannelStreams.prepare_open` rejects any ID already in `used_stream_ids`, enforces 64 live streams per channel, and validates channel/route/grant/transport/port/ID binding through `StreamGate`.
3. Audit capacity is reserved before mutation. Only after all validation and audit succeed does `commit_open` insert the ID into the session-owned `used_stream_ids`, create live stream state, and commit request/sequence replay state.
4. Malformed, binding-rejected, capacity-rejected, or audit-rejected attempts do not consume the stream ID, request ID, or monotonic sequence. A corrected attempt may reuse that uncommitted numeric stream ID.
5. Once committed, release, reset/cancel, channel revoke, channel close, and channel reopen remove live stream/channel state but do not erase `used_stream_ids`. Reuse in any channel of that Transport Session remains rejected.
6. `ChannelStreams` is owned by one `ControlSession`; dropping the session drops replay history. A new Transport Session has a new replay scope, so the same numeric QUIC ID is legal there.

### Scope and identifier relationships

| Value | Type | Scope/role | Relationship to replay owner |
|---|---|---|---|
| `stream_id` / `quic_stream_id` | `u64`, valid 4 through `2^62-1`, multiple of 4 | Actual source-initiated bidirectional QUIC stream within one QUIC connection/Transport Session | They are the same value. `used_stream_ids` is keyed only by this value and is global across all Service Channels in the owning session. |
| QUIC stream ordinal | conceptual `(stream_id - 4) / 4` | Allocation order namespace for source-bidirectional application streams after control stream 0 | Used only by the model to remove fixed low bits; not a wire field. |
| `request_id` | 16 bytes, nonzero | Unique control request within the Transport Session | Separate session-wide `request_ids` set; a fresh request ID cannot make a committed stream ID reusable. |
| `session_id` | 16 bytes, nonzero | Established authenticated Transport Session | Selects the replay lifetime. Cross-session identical numeric stream IDs are legal. |
| `monotonic_sequence` | `u64`, positive/increasing per control direction | Orders accepted control envelopes | Independent of the numeric QUIC stream ID. A higher sequence may legally carry a lower fresh stream ID. |
| `channel_id` | 16 bytes | Independently authorized Service Channel | Not part of the replay key; same numeric stream ID across sibling channels in one session is rejected. |

### Ordering, concurrency, reset, and lifecycle

- Stream-0 control frames arrive in byte order. The receiver therefore observes `STREAM_OPEN` controls in send order, despite packet retransmission/reordering below QUIC.
- Concurrent application intent can choose/allocate multiple QUIC IDs, but the frozen rule does not require their `STREAM_OPEN` controls to follow numeric order. Current code accepts fresh valid `12` followed by fresh valid `4` when request IDs and control sequences advance.
- A QUIC reset/cancel after committed admission does not undo replay history; any separate live-stream cleanup likewise cannot make the ID reusable. A rejected pre-commit attempt does not create history.
- Service Channel close/reopen stays inside the same `ControlSession`, so replay state persists. It is intentionally not channel-scoped.
- Implemented same-edge resumption creates fresh-session authorization and has separate single-use resume-admission replay controls. It does not transplant the old `ChannelStreams` or resurrect old stream authority. Numeric QUIC IDs restart in the new Transport Session; old authorizations do not.
- No cross-edge migration implementation changes this replay scope. QUIC path migration, if performed by the existing QUIC connection, keeps the same Transport Session and replay owner.

## Attacker and replay matrix

| Case | Frozen outcome | Reason |
|---|---|---|
| Immediate duplicate committed `STREAM_OPEN` | REJECT | Duplicate request ID and/or used stream ID; both fail closed. |
| Very old duplicate in the same session | REJECT | Full committed history survives live-stream and channel cleanup. |
| Fresh lower ID after a higher ID | ACCEPT | Validity is range/parity/freshness; no numeric ordering invariant exists. Control sequence must still increase. |
| Duplicate after many newer IDs | REJECT | Age and numeric distance do not expire session replay history. |
| Concurrent valid distinct streams | ACCEPT | Subject to independent binding and 64 live streams per channel; control commits serialize. |
| Reset/cancel then replay committed ID | REJECT | Reset releases transport/live state, not committed replay history. |
| Rejected-before-commit ID retried with valid authorization | ACCEPT | Failed admission is mutation-free. |
| Service Channel close/reopen, same numeric ID | REJECT | Replay key is Transport Session-wide and retained across channel removal. |
| New Transport Session, same numeric ID | ACCEPT | QUIC stream namespace and `ChannelStreams` owner are connection/session-local. Fresh authorization is mandatory. |
| Same-edge resume attempt replay | REJECT | Separate resume record/admission replay state is single-use. |
| Resumed fresh session, numeric ID reused with fresh authority | ACCEPT | Old stream authorization is not resurrected; new session admits independently. |
| Same numeric ID on sibling channel in one session | REJECT | `used_stream_ids` is deliberately cross-channel. |
| Same numeric ID in a different session | ACCEPT | Replay history is not global across authenticated Transport Sessions. |
| Capacity-exhausted attempt | REJECT, state unchanged | Over-capacity fails before commit; later corrected/capacity-available attempt may retry. |
| Stale request ID or non-increasing control sequence | REJECT | Independent session replay checks run before stream commit. |

## Candidate equivalence

| Candidate | False accepts | False rejects | State | Decision |
|---|---:|---:|---|---|
| Full-history `HashSet` oracle | 0 | 0 | O(total committed stream IDs/session) | Current frozen behavior. |
| Strict high-water | 0 in tested fail-closed form | Nonzero: 592,066 in generated suite; 2 in literal `[12,4,8]` | One high-water ordinal | Unsafe: rejects fresh lower IDs. |
| High-water + finite bitmap semantics | 0 in tested fail-closed form | Nonzero for every tested width; 591,427 to 592,066 in generated suite | One high-water value plus exactly W bitmap bits | Unsafe: any finite W has fresh sequence `[0, W+1, 1]` outside the window. |

The window widths 1, 4, 16, 64, and 1,024 are diagnostic samples, not proposed constants. The proof is parameterized: for every finite W, ordinal sequence `[0, W+1, 1]` contains three distinct, in-range source-bidirectional IDs and the current oracle accepts all three, while a fail-closed W-window rejects ordinal 1. If a window instead accepts below-window identifiers, replaying ordinal 0 at the same point is indistinguishable without historical state and becomes a false accept. Therefore there is no minimum finite safe window under current semantics.

Strict high-water would become equivalent only after a future protocol change requiring each committed `quic_stream_id` to be numerically greater than every previously committed ID in that Transport Session. A sliding window would require a normative finite maximum distance between the highest committed ordinal and every still-legitimate unseen lower ordinal. Neither invariant is currently frozen, and adopting either would change current legal outcomes.

## Model/property methodology and results

The test-only Python model uses a set as the exact committed-ID oracle. It compares candidate decisions event-by-event and counts an oracle REJECT/candidate ACCEPT as a false accept and an oracle ACCEPT/candidate REJECT as a false reject.

Coverage includes:

- literal sequential, gap, reordered, immediate/old duplicate, maximum/near-maximum, and new-session sequences;
- explicit legal-domain checks for every candidate at the maximum ordinal `((2^62-1)-4)/4`, duplicate-at-maximum, negative, and maximum-plus-one inputs; invalid inputs fail without state mutation and boundary arithmetic does not wrap;
- exhaustive 720 permutations of six distinct ordinals (4,320 events), where strict high-water produced 2,556 false rejects and zero false accepts;
- 10,000 deterministic seeded sequences (`0x503143`), each with 64 distinct in-range ordinals and 16 duplicate events, shuffled into concurrent-style permutations: 800,000 events total;
- parameterized finite-window counterexamples for every sampled W;
- fresh model instances for close/session boundaries; production lifecycle tests cover release, revoke, close, drain, resumption, and fail-closed mutation ordering.

Generated-suite exact results:

| Candidate | False accepts | False rejects | Maximum populated markers | Fixed bitmap payload |
|---|---:|---:|---:|---:|
| Full history | 0 | 0 | 64 | not applicable |
| Strict high-water | 0 | 592,066 | 1 | not applicable |
| Window 1 | 0 | 592,066 | 1 | 1 bit + 8-byte high-water = 9 bytes rounded payload |
| Window 4 | 0 | 592,064 | 2 | 4 bits + 8-byte high-water = 9 bytes rounded payload |
| Window 16 | 0 | 592,055 | 2 | 16 bits + 8-byte high-water = 10 bytes payload |
| Window 64 | 0 | 592,026 | 2 | 64 bits + 8-byte high-water = 16 bytes payload |
| Window 1,024 | 0 | 591,427 | 4 | 1,024 bits + 8-byte high-water = 136 bytes payload |

The semantic model uses a set for readable membership decisions rather than implementing packed bit operations. “Maximum populated markers” reflects sparse randomized ordinals and is not storage size. The fixed bitmap columns and JSON fields report the candidate representation's actual theoretical W-bit payload plus an 8-byte high-water value, excluding object/alignment overhead. These are not recommendations because the candidates are unsafe. The exact machine-readable result is `model-results.json`.

## Memory and scaling model

### Measurements reused from P1B

- 75% runs: 1,215,000 replay insertions and high-water entries; `HashSet` capacity 1,835,008; entries and capacity returned to zero at `ControlSession` drop.
- Capacity/entry ratio at that point: 1.510295.
- Across the three 75% runs, peak-to-post-drain process deltas imply approximately 44.98–45.78 bytes/logical entry for private bytes and 52.64–53.19 bytes/logical entry for working set. This is a process-level retained-memory proxy, not exact `HashSet` allocation accounting.

### Estimates for continuously committed streams

The table uses the measured 1.510295 slots/entry ratio. “Raw slot payload” is capacity × 8 bytes for `u64` values only and excludes hash controls, allocator metadata, and base process memory. “Observed process proxy” applies the broader measured 44.98–53.19 bytes/entry range. All values are MiB and are extrapolations, not laptop-validated production claims.

| Rate | Duration | Historical entries | Estimated capacity | Raw slot payload MiB | Observed process proxy MiB |
|---:|---:|---:|---:|---:|---:|
| 1k/s | 1 min | 60,000 | 90,618 | 0.69 | 2.57–3.04 |
| 1k/s | 10 min | 600,000 | 906,177 | 6.91 | 25.74–30.44 |
| 1k/s | 1 hour | 3,600,000 | 5,437,062 | 41.48 | 154.43–182.61 |
| 10k/s | 1 min | 600,000 | 906,177 | 6.91 | 25.74–30.44 |
| 10k/s | 10 min | 6,000,000 | 9,061,770 | 69.14 | 257.38–304.36 |
| 10k/s | 1 hour | 36,000,000 | 54,370,620 | 414.81 | 1,544.27–1,826.13 |
| 100k/s | 1 min | 6,000,000 | 9,061,770 | 69.14 | 257.38–304.36 |
| 100k/s | 10 min | 60,000,000 | 90,617,700 | 691.36 | 2,573.78–3,043.56 |
| 100k/s | 1 hour | 360,000,000 | 543,706,200 | 4,148.15 | 15,442.66–18,261.34 |

`used_stream_ids` is one set per Transport Session, not one set per Service Channel. Multiple channels share the same historical set, so adding channels does not multiply a fixed per-channel replay structure; their aggregate committed stream rate drives the session total. Live-stream maps and quotas remain per channel and independently bounded. Because no safe bounded replacement exists, there is no security-equivalent bounded bytes/channel or bytes/session figure to claim.

For comparison only, the unsafe strict candidate stores one high-water integer, and an unsafe W-bitmap can use approximately `8 + ceil(W/8)` payload bytes/session plus container overhead, independent of total history. Those attractive bounds are not eligible because they change frozen behavior.

## Security invariants

The investigation preserves and tests/reviews the existing fail-closed chain: duplicate and old replay rejection; non-consumption on rejected admission; independent Service Channel authorization; source/destination and exact authenticated-connection admission; channel/route/grant binding; actual QUIC stream binding; stream authorization before application bytes; Core version/downgrade rejection; channel close/revoke/drain non-resurrection; same-edge resume single-use/fresh-authorization semantics; and audit/live-stream/buffer capacity exhaustion before mutation. No probabilistic acceptance/rejection, replay expiry, new authority, or production replacement was introduced.

## Files changed

- `scripts/performance/bounded_replay_model.py`: deterministic test-only oracle/candidate model and result generator.
- `tests/performance/test_bounded_replay_model.py`: literal, exhaustive, boundary, and seeded property tests.
- `evidence/performance/bounded-replay-design-p1c/model-results.json`: generated exact model counts.
- `evidence/performance/bounded-replay-design-p1c/report.md`: this investigation report.
- `evidence/performance/bounded-replay-design-p1c/checksums.json`: generated evidence integrity record.
- `docs/superpowers/plans/2026-08-10-p1c-bounded-replay-design.md`: scoped execution plan.

No file under `crates/nbsr-transport/src/` was changed.

## Verification

Fresh final results, all using `CARGO_TARGET_DIR=C:\codex-target\nbsr-p1c` for Rust:

- `python -m pytest tests/performance/test_bounded_replay_model.py -q`: 7 passed, 0 failed in 4.09 seconds after the final boundary/domain correction.
- `cargo test --manifest-path crates/nbsr-transport/Cargo.toml channel_streams::tests -- --nocapture`: 6 passed, 0 failed (24 library tests and unrelated integration targets filtered).
- Focused serial integration tests: `multi_stream` 3/3, `application_stream` 4/4, `multi_channel` 4/4, `channel_lifecycle` 3/3, `drain` 12/12, and `resumption` 17/17; aggregate 43 passed, 0 failed.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check`: exit 0.
- `cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings`: exit 0.
- One broader `cargo test --manifest-path crates/nbsr-transport/Cargo.toml -- --test-threads=1`: 142 passed, 0 failed (30 library unit, 96 integration, 16 doc tests).

The initial root-level Cargo command found no `Cargo.toml`; it executed no Rust test. It was corrected to the sole manifest under `crates/nbsr-transport` and is not counted as a test failure. No known Windows baseline failure appeared in the relevant broader Rust suite. No frozen vector or manifest was modified.

## Recommended next task

Investigate a security-preserving **Transport Session lifetime/rotation policy with seamless fresh authorization and explicit capacity admission**, quantifying the maximum full-history state per session while proving that rotation cannot resurrect channels, streams, RouteGrants, request IDs, or resume authority.

Do not start that task as part of P1C.
