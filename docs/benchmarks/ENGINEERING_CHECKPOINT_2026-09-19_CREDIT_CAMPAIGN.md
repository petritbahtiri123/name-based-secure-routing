# NBSR maximum-quality / funding-grade engineering checkpoint

**MORE ENGINEERING REQUIRED. This is a budgeted checkpoint, not a final funding
freeze or a declaration that all safe engineering work is exhausted.**

The campaign authorized up to 1,000 credits. It began at
`52824743e074528852105bc3e0be4ed8d9c83c8a` on `codex/nbsr-v3-wp0-wp1`.
Implementation and evidence through `50925e10` are indexed below; the commit
adding this checkpoint follows that sequence. Main and origin/main remain
`1938154d498b32d81a3564319969430644e8a688`. No push, merge or history rewrite.

## What changed and what it establishes

| Stage | Retained result | Classification |
| --- | --- | --- |
| Native packet phases, 6b1095c5 | Twenty matched Direct/NBSR cells; eighty independent TShark phase-window checks; forty live socket joins; 160 incorrect joins rejected | MEASURED packet accounting; timing DIAGNOSTIC |
| Source allocator observation, 2c35c773 | Five observer-off/on pairs, 100 same-process cycles, zero final ownership, 55 XML snapshots | Observer qualification REJECTED; allocator cause INCONCLUSIVE |
| Explicit lifecycle source bind, b6cf5e56 | Twelve default/alias cycles complete; actual sockets and final ownership verified; malformed bind rejected | MEASURED benchmark capability; no production change |
| Native held bundles with Windows control storage | Five repeats each at 16/32/64/128 pass; 1,200 completed connections; subsequent 256 attempt fails | MEASURED functional scale, not admission capacity |
| Native per-host runner, a401567d | Three 16-bundle cells pass with separate role control roots; first missing-destination-release attempt retained | MEASURED corrected coordinator mechanics |
| Control-storage comparison, a401567d | Five Linux-local 256-bundle cells pass; all five matched v9fs cells fail | MEASURED functional sensitivity; no qualified causal timing claim |
| Native 512 progression, a401567d | Three complete 512/512; two fail with one/four observed handshake failures | PARTIAL; not repeat-qualified acceptance |
| Native runner cancellation | Three source and three destination SIGTERM controls reject partial output and reap owned children | MEASURED harness reliability |
| Independent pair gate, e74e53b1 | Eleven complete pairs accept; eleven failed/cancelled pairs reject without reruns | MEASURED evidence validation |

Production performance optimizations in this campaign: **none**. Changes are
benchmark-only Rust binary support, Python orchestration, observation and
analysis. No library protocol, wire, authentication, authorization, trust,
cryptographic, replay, fail-closed or send-completion rule changed. No mandatory
security check was skipped. The three Linux release binary hashes at a401567d
match b6cf5e56; Python-only follow-ups did not change them.

The concrete harness corrections are bounded packet-phase control, lifecycle
use of the existing explicit benchmark connector, propagation of release markers
to both separate control roots, and use of native Linux control storage for the
next functional scale fixture. The pair validator replaces reliance on summary
flags with independent checks of raw outcomes, identities and provenance.

## Scoreboard and boundaries

These rows are deliberately source-scoped. They are not one final-SHA capacity
scoreboard, and a functional lifecycle pass is not a latency-stable admission cell.

| Metric | Value | Evidence scope |
| --- | --- | --- |
| Single-core forwarding | 0.865859 Gbit/s, 52,847.849 ops/s, 1 KiB/64 streams/depth 1 | HISTORICAL Windows physical-core allocation, cbdca987 |
| Single-core forwarding | 1.052536 Gbit/s, 4,015.106 ops/s, 16 KiB/eight streams/depth 1 | HISTORICAL Windows physical-core allocation, cbdca987 |
| CPU cost for those shapes | 18,601.695 / 242,551.717 CPU ns/op | DERIVED from sampled combined peer CPU, not instruction cost |
| Four-core strict-stable forwarding | 2.306118 Gbit/s, four groups/16 KiB/one stream | HISTORICAL five-repeat stage, 53468db4 |
| Earlier forwarding bands | 2.185 strict-stable / 2.942 repeatable degraded / approximately 3.040 saturated peak Gbit/s | HISTORICAL distinct workloads; peak is not stable capacity |
| Finite admission | 125 offered/s → 119.920 actual/s stable; 150 degraded; 200 saturated | HISTORICAL Windows 512-client batches, 1917b195; not sustained admissions/core |
| Later Linux finite admission | 512/512 in all five; 104.756154 actual/s at 125 offered/s, 83.805% | 9745cecb: SATURATED by achieved/offered; not reproduced stable capacity |
| Latest native repeat-qualified held scale | 256/256 in five Linux-local control cells | MEASURED shared-WSL namespace fixture at a401567d; no latency qualification |
| Largest observed complete native held cell here | 512/512 in three of five attempts | MEASURED individual successes; overall PARTIAL, two failures preserved |
| Earlier resource scale | 2,048 materialized streams on 32 channels; separate historical bundle tests also exist | HISTORICAL source/fixture scope; not superseded or recertified by this campaign |
| Sustained near-ceiling soak | No qualified 60/120-minute result | NOT_PROVEN; short runs cannot be added together |
| Current hardware or global production ceiling | None established | NOT_PROVEN |

Historical single-/multi-core, admission and memory sources are linked in the
[working brief](FUNDING_EVIDENCE_WORKING_BRIEF.md). Later dispersed Linux finite
references remain visible in the [preceding checkpoint](ENGINEERING_CHECKPOINT_2026-09-19.md).
No new forwarding, burst-resilience or sustainable admissions/s claim is made
from the held-bundle fixtures in this campaign.

At 256 Linux-local bundles, sampled median peak RSS is 111,935,488 bytes
(106.75 MiB) for the source and 85,852,160 bytes (81.875 MiB) for the destination.
Peak observed FDs are 267/8; threads 4/2. Both children have guest affinity [0];
the separate control watcher is outside child affinity. These are complete
process peaks with coupled connections/sessions/channels/streams, not independent
bytes per object, dedicated physical-core utilization, allocations/op or retained
allocator cost. The allocator experiment's unchanged 5% observer gate rejects
handshake p99 (13.8703% shift) and source CPU (5.1282% shift), among other metrics.
Immediate post-close XML does not establish a cooldown plateau or a leak.

## Where the native handshake investigation reached

The original 256 continuation reaches 146 active bundles and 110 source
HandshakeTimeout outcomes. A separately retained failure-only probe reaches
138 active and 118 timeouts. Its snapshot observes 256 live source UDP sockets
and one destination listener with zero cumulative drops at that instant.
Closed sockets and exact drop timing are not observed.

The first attempt's one-second application CPU windows have a conservative
maximum upper bound of 0.43 combined cores during the first ten seconds. This
does not measure IRQ work, host/VM contention or subsecond spikes and does not
prove a hardware ceiling. Prior Linux receive-buffer experiments already failed;
no repeated speculative buffer change was made.

The new counterbalanced control-storage study uses the same a401567d release
binaries and finite workload. Linux-local overlayfs passes 5/5 at 256 while
Windows v9fs fails 5/5. This establishes functional control-path sensitivity in
that instrumented fixture, not an isolated filesystem-latency or production
transport cause. Existing selective-marker fallback, watcher interference and
VM scheduling are not individually isolated. Failure cancellation prefixes must
not be compared with the older complete 120-second timeout totals as throughput.

At 512 on Linux-local storage, failures concern logical client 511 in one cell
and 508–511 in another. They remain UNRESOLVED. Three successes do not waive the
two failures. No 1024 test is attempted at the unchanged 100/s schedule: its
launch span plus two-second hold exceeds the existing ten-second idle lifetime.
That is a limitation of this held fixture, not a production connection ceiling.
Read-only previous-cohort hashing overlapped the 512 diagnostics; no controlled
idle-host timing comparison is asserted.

## Direct versus NBSR packet accounting

The twenty phase-aware cells contain five counterbalanced pairs for each of
1 KiB/64 streams and 16 KiB/eight streams, depth one, 1000 operations per stream,
zero warmup. Captures pass zero-loss, MTU, exact-tuple, complete-inventory and
readiness/terminal coverage checks. Four packet-order windows independently
match TShark IP-byte sums and packet counts.

| Shape | Median incremental setup IP bytes | Median established-with-postflight IP-byte delta | Delta / useful request-response bytes |
| --- | ---: | ---: | ---: |
| 1 KiB / 64 streams | +38,590 | −21,451 | −0.0163658% |
| 16 KiB / eight streams | +15,596 | −23,519 | −0.00897179% |

These are **MEASURED captured IP accounting**, with DERIVED paired deltas, on
controlled virtual interfaces. The established window includes mandatory untimed
payload validation and the existing 100 ms ACK drain. Signed packetization
differences are not compression, a constant NBSR tax, generic QUIC framing cost,
physical Ethernet overhead or pure timed-operation accounting. Capture timing
is unqualified. Every pair, including unfavorable ones, remains in
[the phase evidence](../../evidence/performance/v2/native-phases-6b1095c5/summary.md).

## Architecture and security

The approved path remains Client → ISP-A non-frozen adapter → unchanged NBSR
secure path → ISP-B non-frozen adapter → Origin Connector → isolated private
origin. Existing approved design/plans and frozen authority are preserved.
No LEGACY_REFERENCE_ONLY evidence is used to support the following claims.

| Boundary | Accepted evidence | Limitation |
| --- | --- | --- |
| Replay, tampering, service/name/port/transport/PoP binding; expiry, revocation, generation and downgrade; unauthorized/forged identity; malformed input; failure/recovery | Thirteen accepted fail-closed cases at bf53b8d4 | HISTORICAL source-scoped matrix, not whole-current-source recertification |
| Direct-origin reachability | Three Docker network lifecycles deny client/ISP-A direct DNS/IP probes and return the exact body through the authorized route | MEASURED local topology at f831c9bb; shared bootstrap fixtures; no hostile host/root resistance claim |
| Federation admission preflight | Retained separately from route/network isolation | Does not establish live runtime federation |
| Independent live federation | Existing package manifest/trust-anchor/version incompatibility remains fail-closed | BLOCKED_ARCHITECTURAL; live runtime federation NOT_PROVEN |
| New lifecycle addressing | Existing TLS/ALPN/name/channel-binding tests and actual bind controls pass | Benchmark-only address selection; no authority relaxation |
| New runner cancellation | Six live catchable-signal cases reap owned children and reject partial results | Not graceful runtime cleanup; SIGKILL/host failure outside handler scope |

See [adversarial evidence](../../evidence/security/adversarial-refresh-bf53b8d4/summary.md)
and [private-origin isolation](../../evidence/security/isp-isolation-f831c9bb/REPORT.md).
No production security regression was identified by the relevant focused checks;
no exhaustive fresh security audit is claimed for this benchmark-only campaign.

## Reproducibility, validation and repository discipline

Checkpoint host inventory: Intel Core i5-10210U, four physical cores/eight
logical processors, 16,942,501,888 visible memory bytes, Windows with Docker
Desktop/WSL. This inventory is not allocated-capacity, thermal or power telemetry.
The native cells use internal virtual networks and guest-visible affinity; they
are not independent servers or physical-NIC measurements. Full per-cell Linux
topology, kernel, toolchain, image/build and process metadata remain in raw roots.
Checkpoint free space is approximately 6.8 GiB; the five-GiB run reserve was not
lowered. Further large captures/builds must recheck space before starting.

Executable native per-host lifecycle commands and the independent transferred
pair gate are in [the runbook](EXTERNAL_NATIVE_LIFECYCLE_PEER.md). The latter
checks exact source/build/binary/public fixture, argv/environment, readiness,
PID epoch, affinity, resource counter progression, terminal exit and raw
payload/cardinality/eleven-counter ownership. Simultaneous all-active holds and
actual socket bindings still require the separate coordinator evidence. Indexes
detect corruption, not malicious forgery or remote attestation.

Fresh final Python scope: **176 tests PASS** across the changed and adjacent
phase/capture/pair/cohort/lifecycle/allocator modules. Scoped Ruff, `pip check`,
Rust `cargo fmt --check`, and campaign `git diff --check` pass. Earlier meaningful
Rust stages retain literal RED, focused Linux release tests, TLS/argument tests,
and feature-enabled release clippy `-D warnings`. The non-feature check had
existing warnings and is not described as lint-clean. Go code and dependency
lockfiles did not change; no new Go full-suite/vet or dependency-version upgrade
is asserted. One focused parent correctness/security review covers each change;
no recursive or unrelated repository audit was substituted.

The ten stage evidence packages pass complete canonical/raw checksum checks and
canonical credential-marker checks: 102 canonical indexed entries, 112 canonical
files inspected for privacy, and 31,688 raw index-entry verifications. Raw roots
shared by references may be counted more than once. These are not 31,688 distinct
files. The checkpoint package below records exact commands, logs and index hashes.

Six stopped campaign fixture containers were removed after retained-evidence
verification, freeing 2,693,197,824 disposable writable-layer bytes inside Docker.
No matching host SSD recovery is claimed. An earlier mistaken incomplete source
staging tar of 4,397,726,208 bytes was removed before any test ran and regenerated
from tracked files only. Source, accepted evidence, images, volumes, keys and
unrelated personal data were not deleted. Three pre-existing untracked OneDrive
evidence variants remain untouched. No benchmark is left intentionally running.

## Remaining work and dispositions

| Disposition | Work |
| --- | --- |
| COMPLETE | Scoped packet phases; optional allocator observer plus honest rejection; native lifecycle bind/runner; controlled storage sensitivity; retained 512 failures; cancellation; independent pair gate; stage evidence/checkpoints |
| ADMIN_REQUIRED | The one existing matched Windows Direct paced-CPU capture in [the deferred ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md); no repeated handshake ETW request |
| EXTERNAL_HARDWARE_REQUIRED | Dedicated physical-core/server/NIC/thermal validation, independent hosts, actual larger core counts and a qualified source-bound reference/soak |
| BLOCKED_ARCHITECTURAL | Federation manifest/trust-anchor/version incompatibility; no frozen authority or security guarantee changed |
| BLOCKED_DESTRUCTIVE | None required; no history rewrite, force-push, broad cleanup or security-policy change |
| OPTIONAL_LOW_VALUE | More invasive unqualified WSL profiling, repeated buffer/location trials without a new question, or reruns seeking favorable outcomes |
| OPEN SAFE IMPLEMENTATION | Automated two-host lifecycle/admission barrier and cancellation orchestration; remote paced B5/reference orchestration and full external matrix gates |
| OPEN VALIDATION | Explained 512/native and historical handshake limits; independently qualified retained-memory observation; current-source physical single-/multi-core capacity; 60/120-minute soak; final whole-package/security gates |

The safe implementation rows are genuine remaining engineering, not disguised
hardware blockers. Their existence means this checkpoint must not be described
as completion of the original mission. Continue from these concrete gaps rather
than reopening accepted tests or estimating another unsupported completion
percentage. External preparation is described in
[the Linux/server definition](EXTERNAL_LINUX_SERVER_VALIDATION.md); it remains
explicitly partial until the missing orchestration is implemented and verified.

## Funding-safe wording

NBSR has demonstrated authenticated secure routing to an isolated private origin
in a containerized laboratory. Historical Windows loopback tests measured
2.306118 Gbit/s strict-stable in a specified four-core workload. This campaign
adds independently checked Direct/NBSR packet-phase accounting and five complete
256-bundle native Linux namespace fixtures with zero final ownership. It also
preserves higher-scale failures and rejected observers instead of presenting
them as stable capacity. Independent server-class and sustained near-ceiling
validation remain work for the next engineering/partner-hardware phase.

Do **not** claim current production/ISP/WAN capacity, a proven hardware ceiling,
repeatable 512-native acceptance, a production speedup from these changes, exact
live-object memory cost, leak-free arbitrary lifetime, a qualified 60/120-minute
soak, measured physical Ethernet overhead, or independent live federation.
The 2.942/3.040 Gbit/s historical degraded/peak values must not replace stable
capacity. Recommendation for the full mission: **MORE ENGINEERING REQUIRED**.
Technical outreach can use the scoped evidence to seek validation partners,
without marketing unproven pilot readiness or production guarantees.

[Evidence/checksum index](../../evidence/performance/v2/credit-campaign-checkpoint-20260919/evidence-index.json)
and [atomic commit sequence](../../evidence/performance/v2/credit-campaign-checkpoint-20260919/commit-sequence.txt).
