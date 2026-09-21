# NBSR engineering checkpoint — September 21

**IN PROGRESS / MORE ENGINEERING REQUIRED.** This is a budgeted continuation,
not a final funding freeze or one exact-SHA capacity scoreboard. The earlier
[September 19 checkpoint](ENGINEERING_CHECKPOINT_2026-09-19_CREDIT_CAMPAIGN.md)
remains historical and unchanged.

## Repository and budget

Start: `30b5452e52d81c52ab13ed8d600b98854e75021f`, branch
`codex/nbsr-v3-wp0-wp1`. Main and origin/main remain
`1938154d498b32d81a3564319969430644e8a688`. No push, merge, reset, history rewrite,
authority overlay or production Rust/Go change. The three preexisting OneDrive
evidence variants remain untouched.

The user authorized at most twenty additional weekly percentage points. Baseline
was 7% used, so the absolute account ceiling is 27%. These account readings are
not exact per-task token attribution. The final checkpoint message records the
last observed reading; no promise to consume the full budget is implied.

## Closed engineering stages

| Stage | Evidence-backed result | Classification |
| --- | --- | --- |
| Prepared source before finite accepts | Three deliberate delayed-start pairs: legacy 15/16 FAIL in all three, prepared 16/16 PASS in all three, identical Rust binaries | MEASURED harness startup slot exhaustion |
| Native TLS fixture placement | Five counterbalanced 512-bundle pairs, both arms complete all clients; Linux-local TLS lowers diagnostic cold-handshake quantiles in every pair | MEASURED functional result; DIAGNOSTIC timing, not a universal failure cause |
| Per-host private control | Prepared/readiness/active/release/ACK/cooldown phases, exact marker sets, live socket bindings, owned-child cancellation | COMPLETE scoped implementation |
| Two-endpoint coordinator | Existing strict SSH authentication interface, bounded local relays and evidence transfer, safe extraction and independent gates | COMPLETE implementation; actual SSH remains NOT_EXECUTED |
| Live coordinator validation | Three 16-bundle and five 512-bundle pairs; six source/destination EOF cases; 2,608 positive completions and zero final ownership in every positive cell | MEASURED Docker/WSL functional evidence at 3dfd9f8a |
| Shutdown reliability | Retained first-run exit 134 after completion; replaced blocked buffered-stdin daemon read with stop-aware descriptor reads/join | MEASURED harness failure and verified correction |
| Collection privacy | No validated live phase means no collection of a possibly preexisting remote directory | RED/GREEN regression and focused independent review |
| Native 1024 cardinality | Five of five 512 and five of five 1024 cells complete at the separately declared 200/s schedule; 7,680 positive completions, exact hold/ACK and zero final ownership | MEASURED functional evidence at 3c3f784a; no keepalive or timeout change |
| Catchable endpoint signals | Three source and three destination SIGTERM controls reject partial results and reap owned work; no measurement process remains | MEASURED negative controls, distinct from graceful ownership cleanup |

The original Windows transport-handshake attribution remains
`PLATFORM_DIAGNOSTIC_LIMIT` under the rejected observer gates. This campaign
does not retroactively turn those traces into valid causal evidence. Earlier
reused-namespace 512 failures remain retained; new fresh-namespace successes
cannot erase them.

## What the results do and do not mean

No new forwarding speedup or sustained admissions/s claim is made here. Historical
Windows strict-stable four-core forwarding remains 2.306118 Gbit/s for its
53468db4 workload. The older 2.185 stable, 2.942 degraded and approximately 3.040
saturated-peak bands describe distinct shapes. Historical Windows one-core and
admission figures retain their original scope in the
[working brief](FUNDING_EVIDENCE_WORKING_BRIEF.md).

The brief also retains the historical 3.235685 Gbit/s Docker/WSL finite reference
and separate 2048-bundle keepalive-enabled experiments. Neither is replaced by
this no-keepalive native-address coordinator. Do not call 1024 the largest NBSR
scale ever observed, or compare these different fixtures as one capacity ladder.

At 3c3f784a the new finite cardinality study declares 200 offered/s for both 512
and 1024, two source shards, one materialized 1 KiB bundle per logical client,
native local filesystems and fresh namespaces. Both roles select guest CPU 0 on
the same WSL host. The workload uses shared test identities and one service;
logical client count is not a count of independent customers or tenants.

Its [dedicated package](../../evidence/performance/v2/native-lifecycle-1024-3c3f784a/summary.md)
contains every repeat, independent functional verification and sampled process
resources. Aggregate RSS slope is at most a compound bundle estimate including
TLS/QUIC/harness/allocator effects; it cannot identify separate bytes per
connection/session/channel/stream or a leak. Fresh processes do not prove
same-process repeated-cycle retention. Cold-handshake timing includes synchronous
TLS configuration and remains diagnostic.

## Security and reproducibility

The approved Client → ISP-A adapter → unchanged NBSR → ISP-B adapter → Origin
Connector → isolated private origin architecture is unchanged. Historical
thirteen-case fail-closed adversarial evidence and three genuinely isolated
Docker origin-routing lifecycles remain scoped to their recorded sources; see
the prior checkpoint for exact evidence links. No LEGACY_REFERENCE_ONLY evidence
supports a current claim. Federation admission preflight is distinct from live
runtime federation, which remains NOT_PROVEN / BLOCKED_ARCHITECTURAL.

The new code is benchmark-only Python/standard-library orchestration. Exact-SHA
release rebuilds retain identical Rust binary hashes; all source changes are
recorded in Git. The focused suite reaches 112 passing tests after the 1024
extension. Ruff/diff and package privacy/integrity gates are recorded with each
stage. There is no fresh exhaustive production security audit or full Rust/Go
recertification claim for these Python-only changes.

Runbooks:

- [Native private-stream coordinator](EXTERNAL_NATIVE_LIFECYCLE_COORDINATOR.md)
- [Per-host lifecycle and peer gate](EXTERNAL_NATIVE_LIFECYCLE_PEER.md)
- [External Linux/server definition and remaining port gaps](EXTERNAL_LINUX_SERVER_VALIDATION.md)
- [One deferred administrator command](ADMIN_REQUIRED_FINAL_VALIDATION.md)

## Cleanup

After canonical retention and integrity checks, 28 stopped campaign-owned
3dfd9f8a fixture containers were removed by verified container ID. Their total
writable-layer size was 1,028,792,320 bytes. This freed Docker allocation, not
measured host SSD capacity: observed host free space changed by −315,392 bytes.
The canonical evidence, images, source/Git and host-generated fixtures were not
removed. Verified duplicate transfer archives are removed only after extraction
passes a complete checksum inventory; their hashes/sizes remain in transfer
records. Unfavorable valid evidence is retained.

Two empty internal bridge networks from those completed runs were also removed
by verified ID after Docker reported exhausted default address pools. Their
ownership, emptiness and retained before-state were checked first. The signal
probe's initial helper-name and same-UID permission setup failures are retained;
no host policy/capability was changed. The successful probe runs under UID 65532
and uses an identity-checked pidfd. See the
[six signal controls](../../evidence/performance/v2/native-control-signals-3c3f784a/summary.md).

## Remaining dispositions

| Disposition | Exact remaining scope |
| --- | --- |
| COMPLETE | Prepared-source attribution/fix; local TLS comparison; bounded lifecycle controllers/coordinator; functional namespace/EOF gates; 1024 wrapper support; scoped evidence and runbooks |
| ADMIN_REQUIRED | Existing matched Windows Direct paced-CPU WPR capture only; no repeated Task 4l ETW request |
| EXTERNAL_HARDWARE_REQUIRED | Actual independent-host SSH execution, physical-core/NIC/thermal qualification, server scale and WAN validation |
| BLOCKED_ARCHITECTURAL | Accepted live-federation manifest/trust-anchor/version incompatibility; no authority/security change made |
| BLOCKED_DESTRUCTIVE | None required |
| OPTIONAL_LOW_VALUE | Further invasive unqualified WSL instrumentation or repeated trials without a new measured question |
| OPEN SAFE ENGINEERING | Native remote paced B5/reference orchestration and full external matrix gates; remaining same-process memory observer qualification |
| OPEN VALIDATION | Explained residual/platform handshake limits; current-source qualified physical-core forwarding/admission references; genuine 60/120-minute near-ceiling soak; final whole-package/security acceptance |

Safe engineering remains. Do not describe this checkpoint as full completion,
quote another unsupported percentage of work remaining, freeze a funding package,
or say only external/admin work is left. The next implementation priority is the
native remote paced/reference ownership path; use existing B5 guards rather than
inventing weaker drift/cleanup acceptance. Any later soak must follow a valid
same-source/shape/host reference and retain every failed preflight.


## Final guest CPU placement checkpoint (2da82de2)

The smallest harness-only CPU-pool selector is verified by 124 focused tests
(10 literal RED failures before implementation), Ruff and focused diff review.
Production Rust binaries remain byte-identical. The exact-source 1024-bundle,
200 offered/s, two-shard diagnostic uses five counterbalanced shared/split pairs,
unchanged controller placement, native TLS/control files and identical private
fixture bytes within each pair. Shared Rust-child CPUs [0]/[0]: 2/5 complete
functional passes, three retained failures. Split [0]/[1]: 5/5 complete passes.
Do not discard the shared failures or call split completion sustainable capacity.
Split allocates an additional guest CPU; verified host physical scaling and a
production cause are not established. Shared failures include idle-timeout close
errors and destination cardinality failure; further stage/timer attribution is
required before another optimization. Independent process scans show no owned
Rust peer left before each fixture stop; failure cleanup is not graceful-counter
proof. See `evidence/performance/v2/native-lifecycle-placement-2da82de2`.

The cohort paused between complete pairs 1 and 2 on its predeclared disk reserve.
Both first-pair results were retained unchanged. After containment, Git tracking,
Cargo marker and active-process checks, `cargo clean --locked` removed only the
rebuildable `crates/nbsr-transport/target` (12,268 files). Measured host free-space
recovery: 5,572,845,568 bytes. Source, Git, authoritative raw evidence and private
fixtures were preserved. Separately, 32 stopped verified campaign containers
(1,446,105,088 logical writable bytes) and two empty owned networks were removed;
that Docker cleanup did not demonstrate host SSD recovery. Raw inventories,
commands and results are indexed with the placement package.

This is a budget checkpoint, not final funding closure. The absolute usage cap
for this turn is 27% (7% baseline plus 20 authorized percentage points). No new
long campaign is started near that cap. Native paced/reference orchestration,
qualified soak and the other remaining dispositions above remain open.
