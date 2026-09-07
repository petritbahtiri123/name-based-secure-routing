# NBSR campaign continuation checkpoint

## Active continuation, 2026-09-07

User authorized an additional 15 percentage points of weekly account usage,
maximum 17. Baseline 21% used; target stop around36%, maximum38%, reserving room
for a clean checkpoint/report. Latest observation27%; this is account-wide,
not a per-task token count. Do not silently restart this budget after compaction.

New commits:4ceb32c4 retains finite failure traceback/notes;ad86ab24 binds the
formatter source;c6c7e925 preserves FD exit-transition diagnosis and updates the
working brief;8779e69c adds explicit finite-only exiting observations.121 tests,
Ruff and500 real Linux lifecycle checks pass. The500-child diagnosis showed290
FD denials with non-zombie rechecks; all had PF_EXITING. The original invalid
attempt lacks enough evidence for retrospective attribution. Ordinary live
permission failures still fail; no timeout or protocol change.

Current release build at8779e69c completed and all three Linux binary hashes
equal the prior edc0f96d binaries. New raw root:C:/NBSR-build/linux-current-8779e69c.
The reference-1k32 ladder completed22 valid rows, no telemetry failures. NBSR
depth1 isSTABLE1.822417Gbps/CV0.663%;depth2DEGRADED2.165110;depth4SATURATED2.432145.
Direct baseline remainsUNRESOLVED/CV6.98%.266 outer hashes are preserved in
linux-reference-8779e69c; no dedicated physical-server claim. Never replace old
failed cohorts.

The next B5 ownership comparison loaded that reference at70%, but its first
ownership-off control aborted on source-private growth at10seconds. See
b5-sample-residency-8779e69c:114688bytes of steady growth,10530bytes/s, while
12067 retained u64 latency samples account for96536bytes and9653bytes/s.
A three-pair optimized Rust mincore probe proved reserved sample pages become
resident during filling (1->24pages); pre-touch before filling stays48->48.
Next: RED residency test, prepare both existing sample buffers before measurement
without changing capacity/stride/guards, then actual rerun. Some residual growth
may remain; do not claim all growth attributed or a production leak fixed.
No active benchmark container remains at this checkpoint.

The earlier nonreproductions and transition probes are preserved in
linux-fd-transition-ad86ab24 (255 indexed files) and linux-fd-exiting-c6c7e925
(7 files). No production code changed. B5's general Linux resource sampler is
still strict; the finite opt-in does not automatically extend to its null-memory
guards. Source-private growth and qualified long soaks remain open. About12.6GB
free disk remained; no cleanup/deletion was needed. Docker build-cache image
nbsr-linux-build-cache:edc0f96d is generated campaign cache, not evidence.

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
