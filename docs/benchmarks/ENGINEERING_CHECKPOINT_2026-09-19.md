# NBSR engineering checkpoint, September 19

**MORE ENGINEERING REQUIRED. Final local classification: UNRESOLVED.**
This is a continuation checkpoint, not a funding freeze or a claim that all safe
engineering work is exhausted. Remaining implementation and validation are
listed separately from unavailable hardware and protected authority changes.

Continuation start: `c2806269f1078a8dcbb1cf63bcec2afb569c1f88`.
Latest implementation/evidence commit before this checkpoint: `59862280`.
Branch: `codex/nbsr-v3-wp0-wp1`. Main and origin/main are protected at
`1938154d498b32d81a3564319969430644e8a688`; no push, merge or history rewrite.

## Completed engineering in this continuation

- Native-address finite peers ran sixteen Direct/NBSR cells across two Docker
  namespaces. Source/role/build/authority/affinity and terminal process evidence
  are retained. Wrong-authority and changed-affinity controls reject. This is
  namespace mechanics, not two independent physical hosts or a production gain.
- Read-only peer-pair and complete-cohort gates verify transferred artifacts,
  exact expected source, complete checksum inventories, work equivalence,
  declared counterbalancing and three-to-five repeats. All sixteen retained
  cells revalidate without rerunning or rewriting raw evidence. A deliberately
  under-repeated analysis manifest is rejected; Direct 1 KiB CV remains 10.092%.
- Linux NIC inventory preserves partial/unavailable information. An observed
  ethtool permission error despite exit zero now remains explicitly incomplete.
  A veth-reported 10 Gbit/s is not physical link or hardware-ceiling evidence.
- Seven live SIGTERM reproductions proved orphaned benchmark/capture processes.
  Deferred cancellation now passes 24 live controls across eight Linux entry
  points: native peer, loopback, B1, B5 campaign, B5 placement, finite reference,
  B4 and B3. SIGTERM/SIGINT/SIGHUP reject partial attempts and reach owned-child
  cleanup. SIGKILL and host failure are outside catchable signal handling.
- B3 normal follow-up completes three ten-cycle repetitions, thirty same-process
  lifecycle cycles total, with cleanup PASS. This is a regression smoke, not a
  new fifty-cycle retention or maximum-cardinality acceptance.
- Linux packet-accounting rejection now also clears the observer's valid flag.
  The original two-drop log still fails; correcting its flag does not excuse loss.
- The external build recipe now binds its manifest to the pre-build SHA, rejects
  a changed/dirty checkout and refuses manifest overwrite. Three previously
  accepted invalid provenance cases now reject in executable recipe tests.
- The deferred Administrator capture has an independent clean source clone at
  4eb62c09. Pre-existing untracked OneDrive variants remain preserved, and the
  strict clean-source capture gate is unchanged. The ledger has one exact command.

All changes above are benchmark/reproducibility/maintenance work. No production
NBSR optimization, cryptographic shortcut, wire/authority change or longer timeout
was introduced. Fresh locked Linux release builds reproduce the same three Rust binary
hashes; the separately prepared Windows binaries have their own recorded hashes. Forced cancellation cleanup is distinct from graceful ownership cleanup.

## Current observations that limit claims

| Source and workload | Observed result | Classification / meaning |
| --- | --- | --- |
| 9745cecb B4, 512 clients, two source shards, 125 offered/s, one shared guest CPU | Five valid runs; every run 512/512, zero errors/timeouts, cleanup PASS; median 104.756154 admissions/s, 83.805% achieved/offered; established-goodput CV 26.397% | SATURATED for this cohort. Historical Linux 2a30272e stable 125/s is not reproduced. No causal hardware/production attribution. |
| 71c0a3eb finite reference, 16 KiB/eight streams/depth one, one shared guest CPU | Five pairs; Direct median 2.110116 Gbit/s, CV 23.760%; NBSR 2.079099 Gbit/s, CV 13.183%; all ten correctness/cleanup checks pass | Direct SATURATED, NBSR UNRESOLVED; neither is a strict-stable reference. |
| 6052fe9f B5 placement mechanics, 1000 offered ops/s, 15-second measurement | Five shared/split pairs; nine of ten fail drift gates; residual p99 CV 11.570%/12.178% | Functional mechanics verified; no qualified sustained result or capacity claim. |
| b560d0bd B1 revalidation | Twelve captures complete; thirteenth reports two pcap drops and is rejected. Complete five-pair 1 KiB subset has median whole-IP delta/useful bytes +1.005249%; 16 KiB incomplete | INVALID_PARTIAL full cohort; capture-loss cause UNRESOLVED_OBSERVER. Earlier complete 6b3d37e8 cohort remains historical, not current recertification. |

All unfavorable valid runs and rejected attempts remain retained. Separate short
tests are never added together and described as a continuous soak. Current guest
CPU observations, including B4's approximately 0.953 effective cores, do not prove
dedicated host physical-core saturation or a global NBSR ceiling.

Historical source-scoped results remain in the
[working brief](FUNDING_EVIDENCE_WORKING_BRIEF.md): Windows four-core 2.306118
Gbit/s strict-stable; calibrated single-core results; earlier stable/degraded/
saturated admission and forwarding cells; 2048-bundle/stream scaling; security
and isolated-origin evidence. They are not one latest-SHA scoreboard.

## Original V2 program state

| Task | Current disposition | Exact remaining closure |
| --- | --- | --- |
| 1: plateau attribution | PARTIAL / PLATFORM_DIAGNOSTIC_LIMIT | Qualified blocked-time/CPU attribution; prior intrusive observers failed distortion gates. |
| 2: measured optimization | Named harness repairs complete; production optimization not justified | A measured production hotspot before any production performance change. |
| 3: forwarding maximum | PARTIAL, historical finite boundaries | Reproducible current-host reference and attributed limiting resource; current finite rerun is not stable. |
| 4: admissions/multi-client | PARTIAL, historical finite ladder | Explain current dispersion/handshake waits and establish a reproducible sustainable boundary. |
| 5: memory/lifecycle | PARTIAL | Attribute retained private memory and bound the cooldown plateau; complete missing independent resource/Go/Linux coverage. Zero owned counters alone do not prove allocator closure. |
| 6: near-ceiling soak | NOT_PROVEN; preparation gates fail | Valid reference, one stable 120-minute workload and a 60-minute second workload under the accepted plan. |
| 7: packet overhead | PARTIAL loopback; latest full cohort invalid | Zero-loss current complete comparison and dedicated physical-interface accounting with offloads/uncertainty disclosed. |
| 8: external definition | PARTIAL_REQUIRED_PORTING; external NOT_RUN | Complete remote admission/lifecycle/soak/wire matrix commands and their acceptance; current finite per-host subset is executable. |

## Remaining work by disposition

- **COMPLETE:** the scoped implementations, focused regressions and retained
  positive/negative controls above. See the checkpoint checksum index for exact
  commit sequence, raw roots and verification results.
- **ADMIN_REQUIRED:** one existing matched Windows Direct paced-CPU capture in
  [the ordered ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md). No new handshake ETW
  request, repeated elevation prompt or security-policy change.
- **EXTERNAL_HARDWARE_REQUIRED:** native/server physical-core/NIC/thermal evidence,
  independent hosts, and actual 8/16/32-core scaling. Docker namespaces are not
  substitutes. External preparation still has implementable gaps listed in Task8.
- **BLOCKED_ARCHITECTURAL:** existing federation package manifest/trust-anchor/
  version incompatibility remains fail-closed. No immutable pin is changed.
  Admission preflight is separate from live runtime federation, still NOT_PROVEN.
- **BLOCKED_DESTRUCTIVE:** none required. A prior Git automatic-maintenance warning
  about stale worktree metadata was not addressed through unsafe deletion.
- **OPTIONAL_LOW_VALUE:** further invasive WSL profiling or repeated workloads
  seeking favorable results without a qualified observer or new causal question.

Private-origin isolation and thirteen accepted adversarial cases retain their
recorded scope. No full current-source security recertification is claimed,
especially given the existing fail-closed federation package test failure.

## Disk maintenance and verification scope

NTFS compression of eight retained ETLs reduces allocated storage by
10,030,006,272 bytes (9.34 GiB). Original paths, lengths and every SHA-256 remain
unchanged; nothing is deleted. This is storage maintenance, not a measured fix
for the later packet loss. Additional cleanup removes twelve explicitly owned,
stopped diagnostic/build containers after evidence verification: about 3.44 GiB
of Docker writable layers, not an equivalent measured host-SSD recovery. Required
images, raw evidence, binaries, source, Git history and unrelated user data stay.

Each implementation stage retains RED/GREEN results and source-bound live or
offline validation. B3 focused scope: 33 tests; B4: 42; finite-reference: 90;
native cohort/pair: 32. These overlap and are not a sum of distinct tests. Final
checkpoint verification passes 254 tests across sixteen affected test files,
scoped Ruff and twelve evidence packages; the Administrator preparation package
also passes its separate integrity/privacy checks.
Ruff passes changed implementations/tests except the Task4i inventory-only edit's
twenty demonstrably pre-existing style findings; no lint rule was disabled.
Rust/Go production and dependency files did not change in this continuation, so
historical broad suite results are not mislabeled as fresh current-source runs.

The known untracked OneDrive duplicate `checksums (1).sha256`, `commands (1).txt`
and `summary (1).md` files remain untouched. No completion percentage is asserted:
implementation progress and blocked experimental closure are different measures.

## Reproducible checkpoint index

[Canonical evidence and raw checksum references](../../evidence/performance/v2/engineering-checkpoint-20260919/evidence-index.json),
[verification commands/results](../../evidence/performance/v2/engineering-checkpoint-20260919/verification.json), and
[commit sequence](../../evidence/performance/v2/engineering-checkpoint-20260919/commit-sequence.txt).
The sequence ends before this documentation/evidence commit to avoid a self-referential hash.
Next safe engineering scope is the remaining external matrix porting and explicit
memory-retention coverage; no new performance fix is justified by the noisy cohorts.
