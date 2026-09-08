# NBSR campaign continuation checkpoint

## Resumed campaign, 2026-09-08

User authorized work up to 30% total weekly usage, stopping earlier if complete.
Starting usage 2%, starting HEAD `09a669a343330b381c67605114338cdc87d420e4`.
The older 43% budget below belonged to the previous usage window.

Current-source release build: `C:/NBSR-build/linux-current-09a669a3`;
binary hashes match the prior befccf5f build. Six fixed-historical-rate Linux
B5 diagnostics compare warmup 3 versus 60 seconds, three attempts each, under
`C:/NBSR-build/linux-b5-preparation-09a669a3`. All six abort on destination
private growth; no limit, assertion, timeout or workload measurement interval
was changed. Longer unpaced preparation did not close the paced-memory issue.
This is a diagnostic comparison, not accepted near-ceiling calibration.

A fresh paired current-host finite reference completed under
`C:/NBSR-build/linux-b5-reference-09a669a3`: 30 valid records, all six cells
SATURATED, CV 11.73-30.78%. No new strict-stable calibration was established;
no qualified soak should consume the historical reference on this host state.
Short host power/load snapshots are diagnostic, not causal or ceiling proof.
The separately named B3 live-bundles workload at 40b277fb passed five repeats
each at 512/1024, private-resident CV below 1%, zero final ownership. Five
100-cycle same-process repetitions completed 500 clean cycles; FD/thread deltas
zero, retained-memory cause and a general plateau still INCONCLUSIVE.
Canonical package: evidence/performance/v2/b3-live-bundles-40b277fb.
ec836e81 permits 2048/4096 for only the explicit live workload, after literal
RED and 53 Python tests, release clippy/default check. Larger runs remain next.
See B3_LIVE_BUNDLES.md. No production optimization was made.

The 40b277fb requalification completed: all three materialized idle controls
failed with 2,221 matched source idle-expiry diagnostics. Linux 16 KiB/eight
streams has a short finite NBSR STABLE cell at 3.235685 Gbit/s; 1 KiB/64 has
no strict-stable cell. Scope remains one selected guest CPU, observer not
separately qualified, not server or sustained capacity. Its 70% paced preflight
failed p99 drift at 150 seconds; no longer soak followed.

At07096c08, Windows 16 KiB/eight streams reproduced 1.050835 Gbit/s finite
STABLE, 1.155600 DEGRADED and 1.108855 SATURATED. The 70% short paced preflight
failed repeat two at 94.828% achieved/offered. Canonical packages:
evidence/performance/v2/windows-requalification-07096c08 and
linux-requalification-40b277fb. These preserve failures, not a funding freeze.

The initial 2048 active-bundle attempt failed with601 handshake timeouts;
no OOM/memory-pressure evidence and no4096 attempt. The B4 Linux ladder then
exposed a verified PF_EXITING FD-permission race at100/s.2a30272e adds a B4-only
exit transition with owned completion required;69 tests and500 real Linux
child lifecycles pass (four actual exiting observations). No production change.

The2a30272e ladder completed:23 valid records,0 invalid,125/s ->119.313320
STABLE;150/s ->142.418287 DEGRADED;200/s ->111.350407 SATURATED. The actual
PF_EXITING transition at200/s repeat4 was followed by owned exit0.
Canonical:evidence/performance/v2/linux-followup-2a30272e.

At0124f8ad,2048 live/materialized bundles pass five repeats each with two and
four allocated guest CPUs, all cleanup validation passes. Largest accepted
active scale is now2048 in this VM workload. Four-CPU4096 fails its first attempt
with891 handshake timeouts and one ControlStreamFailed task panic; retain it.
All six one-CPU buffer sensitivity attempts fail; requesting1MiB was clamped to
425984bytes from212992 and did not establish a reliable improvement. Do not
promote the diagnostic setting to a production default. Failure-only snapshots
localize destination UDP receive drops but do not prove the sole timeout cause.
Canonical:evidence/performance/v2/linux-resource-scale-0124f8ad.
All containers from these series have exited and all raw roots are sealed.
No qualified60/120-minute soak; full closure gates remain pending. No Linux
production optimization or hardware ceiling was established. A possible B3
per-client lifecycle-marker polling cost is only an unprofiled lead, not a cause.

External documentation now identifies executable Linux B3/B4/B5 loopback CLIs;
remote/server execution remains unavailable. Usage last read 25% of the 30% cap.

58650e15 repairs stale B5 fixture provenance and excludes the ISP PoC adapter
from production-client inventory; 834 performance tests pass, three existing
skips. Full logs and scoped integrity/privacy/dependency checks are preserved.
fa0e60a8 preserves offline polling and three matched filesystem-location pairs.
All six real attempts fail; no placement optimization was adopted. Temporary
Rust diagnostic patches are retained only in raw evidence, not merged source.
Two owned stopped containers were removed only after copied guest evidence was
verified. Cleanup log: C:/NBSR-build/marker-container-cleanup-0124f8ad.json.
Earlier pure Cargo-cache cleanup recovered about 1.01GB; its paths and exact
before/after values are in closure-checks-40d109a8.

ACTIVE: nbsr-b5-16k8-preparation-0124f8ad, output
C:/NBSR-build/linux-b5-16k8-preparation-0124f8ad. Three counterbalanced warmup
3/60-second pairs at fixed historical rate64804600000000/7500349701, requested
300-second measurement, existing live guards. Source/binaries0124f8ad in a
private checkout. No concurrent build, benchmark or large integrity scan.
This separately tests the16KiB/eight-stream p99-drift question; earlier1KiB/32
warmup diagnostics failed on memory. Do not relabel either as qualified soak.


## Five-point continuation checkpoint

User budget baseline 38%, maximum 43%; last check during closure 40%.
Start `0e4b5cf6`; diagnostic extension `f732ac94`; buffered diagnostic repair
`befccf5f`; subsequent evidence commit binds the final results. See
B3_IDLE_ATTRIBUTION.md and evidence/performance/v2/b3-idle-attribution-befccf5f.

Final source befccf5f: 512 bundles PASS 3/3 with zero final ownership and
private-resident CV below 5%. Three independent unchanged 1024 attempts fail:
731 failed clients, all with complete diagnostics; 713 verified idle expiry,
18 other-closed remain unattributed. Pinned Quinn source/archive verification
proves TimedOut is idle timer expiry. This closes the dominant cause diagnosis,
not the failed 1024 workload. Do not increase timeout or silently change workload
to pass it. No production optimization, hardware ceiling or new speed claim.

Initial f732 diagnostics were malformed/interleaved and control 512 failed;
all attempts preserved, not observer-qualified. Final buffered output passes
the exact failure-ID completeness verifier for all three attempts. All runs
are complete; no benchmark is intended to continue in the background.
Next useful work remains B5 memory/soak, separately specified larger-scale
active-liveness testing if needed, and deferred admin/external validation.
This checkpoint supersedes the earlier generic 1024 ACK-progress uncertainty
for the new measured idle-expiry cases, not every historical failure.

## Extra two-point diagnostic

At `bc9e0437`, user authorized the remaining 38–40% budget. See
B3_1024_RETAINED_FAILURE.md: 233 failed early client IDs, 791 successful
application rows; idle-expiry hypothesis is supported but not proven. ACK-file
timeout is downstream of application failures, not wire ACK attribution.
Retained-input analysis only; no new benchmark or production modification.

## Additional budget review, 2026-09-07

User authorized three additional weekly percentage points from 37% (limit 40%).
The focused retained-evidence review reached 38% at its last usage check.
See VERIFIED_IMPROVEMENTS_2026-09-07.md for actual benefits and remaining gaps.
Three completed 50-cycle endpoint-footprint CVs are below 5%, but destination
growth varies materially; no bounded-memory or long-soak closure is established.
The 1024 failure also contains application-accept failures; ACK timeout alone
is not causal attribution. No additional benchmark or production change was
made in this review. Campaign remains PARTIAL. The earlier budget stop below
is historical; do not mistake this review for completion of remaining engineering.

## Budget stop, 2026-09-07

STOPPED at weekly37% used, baseline21%: approximately16 percentage points.
User target was +15, absolute maximum +17 (38% total). Do not automatically
restart this budget or continue engineering without a new user instruction.
Campaign PARTIAL, not a funding freeze. No push or main modification.

Latest engineering commit:d0792699 (B3 expected-source join). Additional evidence
commits follow. This continuation started atba8c93472969d8ecf13dac2b3322694e209d1d2d.
Use git log from that SHA for the complete atomic sequence.

Completed: finite Linux failure-context/source binding; identity-checked finite
exit-transition handling with500 actual child lifecycles;22-row Linux finite
reference at8779e69c (NBSR1.822417GbpsSTABLE/2.165110DEGRADED/2.432145SATURATED;
Direct baseline dispersed). These are VM-loopback results, not server capacity.

At857b4080, bounded latency storage is prepared before timing (51Linux/50Windows
B5 tests, one existing ignored each). Fixed-load rerun failed destination-private
growth at100seconds. Mapping/allocator traces are DIAGNOSTIC, not observer-qualified;
no production optimization followed. See B5_SAMPLE_PREPARATION.md and
B5_LINUX_MAPPING_DIAGNOSTICS.md. Long near-ceiling soak remains NOT_PROVEN.

Windows started-descendant cancellation coverage:1c16b03d, five repeated pairs,
scoped release clippy PASS. The separate100ms timeout cannot establish descendant
startup on this host; no timeout was extended. See BACKEND_DESCENDANT_CANCELLATION.md.

B3 source preflight6660a04d rejects tracked/untracked dirty source. B3 source join
d0792699 moves the existing30second join before explicit Linux bundle cooldown;
ordinary live sampling/report gates remain strict.117 focused tests pass, one
existing skip; Ruff passes.

Linux B3 retained evidence: evidence/performance/v2/linux-b3-continuation-d0792699.
At1c16b03d:35 valid materialized stream cells through2048,23 valid bundle cells,
five3-cycle smokes;256-bundle repeat4 failed /proc FD access during source exit.
Atd0792699:five256-bundle and five512-bundle repeats pass;1024 fails post-release
connection ACK timeout, not a proven hardware/production ceiling. Three complete
50-cycle same-process runs provide150 cycles with final zero ownership. Repeat4
was interrupted with SIGINT solely for the usage budget; repeat5 was not run.
All partial/failing artifacts are preserved. Assess three-repeat dispersion
before deciding whether further cycle repeats are necessary; do not replace or
hide the interrupted attempt.

Raw roots:C:/NBSR-build/linux-b3-current-1c16b03d,
linux-b3-joined-d0792699,linux-current-1c16b03d,linux-current-d0792699,
b3-final-join-6660a04d. Canonical package binds their full indexes and analyses.
All benchmark containers finished/stopped; no background continuation intended.
About8GB disk remained; no cleanup was required. Never delete authoritative roots.

Remaining:1024-bundle close/ACK progress attribution; qualified B5 memory/observer
and long soak; current evidence/claims reconciliation and external portable matrix.
One deferred Windows Direct CPU Administrator command remains in
ADMIN_REQUIRED_FINAL_VALIDATION.md. External/server hardware is unavailable.
Accepted ISP isolation/preflight evidence remains scoped; live federation is not
implemented. Keep existing valid work; do not rerun indiscriminately.

The older checkpoint below is historical context and is superseded where noted.

Campaign PARTIAL, not final closure. Latest engineering SHA edc0f96d0be2ae089e559092cab8fce2de50aac8; this checkpoint is added by a subsequent evidence-only commit. Branch codex/nbsr-v3-wp0-wp1. main/origin-main remain1938154d498b32d81a3564319969430644e8a688. No push, reset, merge or history rewrite. User authorizes continued safe work and deferred admin validation; do not ask routine approval.

## Next measured problem

Current-source Linux finite reference: C:/NBSR-build/linux-current-edc0f96d/reference-1k32-with-fixtures. Five valid rows, then third NBSR attempt fails PermissionError /proc/230/fd. All six final ownership reports are eleven-counter zero, including the invalid attempt. Preserve the failure; do not count it as valid or replace it. No accepted reference exists. Investigate failure-only proc state/identity and nonreaping waitid correlation around the FD denial before changing sampling behavior. Earlier Linux B4 had an FD-denial nonreproduction diagnostic; this is fresh current-source evidence. Do not silently retry, suppress telemetry failure, or classify it as production NBSR capacity.

Raw root C:/NBSR-build/linux-current-edc0f96d contains native binaries, build manifests, full Git bundle, exact crates/vectors archives, all setup failures and raw cohorts.365 indexed files; raw index SHA-256679ce31f6d1e0b25b99401daed3c3dd69bcb5c5af4d6198b9cb4787f86d217da. Canonical summary: evidence/performance/v2/linux-current-edc0f96d. Native benchmark binaries load reference vectors through compile-time CARGO_MANIFEST_DIR=/work/crates/nbsr-transport; runtime must retain the matching read-only /work source/vector tree. The corrected external reference-with-fixtures.py and captured commands show the tested setup. Initial Direct-only CLI compatibility failed p99 drift; it was not a qualified near-ceiling workload.

The owned build container nbsr-linux-build-edc0f96d is exited0 and retains generated Cargo cache. Runtime containers used --rm and none remain active. Raw binaries and source archives are retained independently. Disk was about12.57GB free; no broad cleanup performed. Do not delete authoritative raw roots. A future source change requires fresh source/build binding; do not relabel old manifests with a new SHA.

## Implemented in this continuation

- f5bc22cb: B5 evidence at2d7525f3;470 raw hashes verified.32stream1KiB finite NBSR0.812138 STABLE at that exact stage; depth2/4 saturated. Separate64stream baseline saturated and preserved. Ownership observer three pairs passed5% gate. Direct600seconds0.114662Gbps/20.17%achieved fails; separate NBSR600seconds0.555331/97.68% passes one repeat with11zero cleanup, then repeat2 source-private-growth abort. No qualified long soak.
- 85e706fc: closed server workload definition, explicitly PARTIAL_REQUIRED_PORTING; two RED/GREEN contract tests.
- 648c8acd: nonreaping Linux child observation and shared consume injection;54 focused tests, three actual Linux exit-status cases.
- 580291f0: explicit terminal-role Linux sampling;84 focused tests and real Linux two-role fixture.
- 228d0800: explicit Linux clock/private-resident guard metrics;60 focused tests; unchanged growth/drift thresholds.
- c6bb0e9f: one deferred Administrator CPU-capture command for Windows Direct pacing. WPR failed0xc5585011 here. Script parser and non-admin refusal pass; elevated run NOT_RUN.
- 7f84a3a5: Linux lifecycle adapter connected to shared B5 run_one;55 focused tests and actual Python-child Linux lifecycle fixture.
- edc0f96d: Linux B5 CLI with strict build/reference binding,3-to5 counterbalanced repeats, p99/goodput dispersion and failed-prefix preservation;59 focused tests. Actual Rust execution now attempted but no qualified reference/soak.

## Remaining campaign

Attribute Linux FD failure and Windows NBSR private-memory growth; Windows Direct CPU attribution is deferred in ADMIN_REQUIRED_FINAL_VALIDATION.md, do not request it yet. At2d NBSR memory abort, steady source private memory increased108KiB in three36KiB steps over30seconds while all11 owned-resource gauges stayed constant; allocator cause is unproven. Re-establish exact-current qualified references/observer comparisons before 10/30/60/120-minute soak progression. No timeout increases, workload hiding, rejected-result replacement or security weakening.

Finish portable Linux sustained validation and full wire/multihost matrix; current CLI and matrix are PARTIAL, not validated server results. Existing Windows B3/B1/ISP/security evidence remains accepted in its recorded scope; do not rerun solely because this checkpoint exists. Final whole-feature quality/security/privacy/dependency/evidence freeze and funding package are still pending. No live runtime federation is implemented; preflight and private-origin isolation remain separately scoped. No hardware production ceiling is proven. See MAXIMUM_QUALITY_CAMPAIGN_STATUS.md for other accepted stage references and limitations.

No active benchmark or background runtime is left at this checkpoint. Preserve the user's full mission; quota exhaustion is not technical completion.
