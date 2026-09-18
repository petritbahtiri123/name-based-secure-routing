# NBSR engineering checkpoint, September 18

**MORE ENGINEERING REQUIRED — not a final funding freeze.** The available
Windows/WSL campaign has made concrete progress without a production protocol or
security change. This checkpoint preserves unsuccessful observations as well as
successful ones. It does not recertify every historical workload at one final SHA.

Start: `840c326d25c82a8d01d1a52bed6034aa517b5dcf`.
Latest technical/evidence commit: `dfbea41fda27c0c66d5bd28592e8d90927b44d4a`.
The documentation/checkpoint commit follows it. Branch remains
`codex/nbsr-v3-wp0-wp1`; main and origin/main remain
`1938154d498b32d81a3564319969430644e8a688`. Nothing was pushed or merged.

## Engineering and measured outcomes

1. **B5 placement diagnostic COMPLETE; sustained acceptance FAIL.** Five matched
   300-second pairs explicitly place both peers on one guest CPU or one distinct
   guest CPU each. Split placement reduces median steady-window p99 by 30.2041%
   (1.552181 to 1.083359 ms), while summed CPU rises 17.0712%. Median goodput rises
   3.7470%, with one unfavorable paired change retained. This allocates two CPUs;
   it is not a same-resource optimization. All ten runs complete with zero
   errors/timeouts and eleven final ownership counters zero on both peers, but
   neither arm has any run passing every drift gate. Shared p99 dispersion remains
   above 5%. No qualified soak, leak conclusion or capacity increase is claimed.
   [Details](B5_PLACEMENT_DIAGNOSTIC.md).
2. **Portable B5 paired driver COMPLETE.** Exact-source/build checks,
   counterbalancing, three-to-five-repeat policy, continuous placement identity,
   failure retention and recursive evidence sealing work on the retained Docker
   mechanics smoke. That smoke is not performance evidence. Native execution is
   still required. [Procedure](B5_NATIVE_PLACEMENT_VALIDATION.md).
3. **Server worker preparation COMPLETE; scaling NOT_RUN.** The benchmark-only
   runtime and Linux finite matrix accept 8/16/32 workers in addition to 1/2/4.
   Focused release tests build those runtimes, complete tasks and drop them;
   topology tests reject insufficient physical cores and SMT substitution. No
   8/16/32-core performance result exists. [Procedure](EXTERNAL_SERVER_WORKER_SCALES.md).
4. **Linux B1 packet accounting COMPLETE for the declared loopback subset.**
   Client PID/start-time/socket-inode ownership, exact initial/terminal capture
   markers and zero-drop/full-inventory gates are implemented. A missing-tail
   fixture and an 845-drop formal capture were rejected and preserved. Increasing
   only the capture kernel buffer from the documented 2 MiB default to 64 MiB
   gives 20/20 subsequent valid captures with unchanged binary hashes, workload
   and timeouts. Five pairs per shape complete with zero workload errors/timeouts.
   [Evidence](../../evidence/performance/v2/b1-linux-packets-6b3d37e8/summary.md).

| New packet observation | 1 KiB / 64 streams | 16 KiB / 8 streams |
| --- | ---: | ---: |
| Useful operations per run | 64000 | 8000 |
| Useful request+response bytes | 131072000 | 262144000 |
| Median paired whole-capture IP delta, NBSR minus Direct | +1192910 bytes | -117313 bytes |
| Delta / useful application bytes | +0.910118% | -0.044751% |
| Paired IP delta range | +836011 to +1519934 | -280129 to -28622 |
| Separate relay setup UDP payload delta, median | +30949 bytes | +12793 bytes |
| Separate established relay delta range | +179151 to +496496 | -89265 to +34379 |

MEASURED IP/UDP byte totals cover setup, useful operations, untimed validation
and teardown. The relay's established phase is a separate scope. Neither these
figures nor synthetic loopback Ethernet lengths are physical-wire measurements.
No constant NBSR framing tax, throughput improvement or observer-qualified
performance claim follows. Capture ran as root inside a disposable Docker
container with default capabilities, without Windows elevation or security-policy
changes. All permissions warnings are retained with actual zero-loss evidence.

No production NBSR implementation optimization was made in this continuation.
The only Rust change extends the feature-gated benchmark worker selector;
production defaults, wire/security/authority and all acceptance gates are intact.
No timeout was increased and no workload reduced to obtain a pass.

## Historical performance remains source-scoped

The [working brief](FUNDING_EVIDENCE_WORKING_BRIEF.md) retains detailed sources.
Windows four-physical-core strict-stable forwarding remains 2.306118 Gbit/s in
its accepted stage. The Linux Docker/WSL 16 KiB/eight-stream finite reference at
40b277fb is STABLE at 3.235685 Gbit/s, while its separate paced preflight fails.
These are different environments and workloads, not competing final-SHA ceilings.

The Linux finite admission ladder at 2a30272e remains 125 offered/s ->
119.313320 actual/s STABLE, 150 -> 142.418287 DEGRADED, 200 -> 111.350407 SATURATED.
It shares one selected guest CPU with established traffic; it is not sustained
admissions/s/core or a global NBSR limit. The selective B3 marker monitor is enabled
by `--hold-for-release`, which the B4 admission command does not use. The new B1
adapters also do not alter that runner, so valid admission work was not repeated
solely because documentation/capture source SHAs changed.

The prior f8925b25 B3 matched comparison completes 2048 bundles in all five
before and five after runs, reducing source pre-start CPU 56.109%. Baseline also
passes 5/5; this does not prove removal of the historical intermittent handshake
failure. Larger 4096 scale is not accepted. No new hardware ceiling is established.

## Consolidated remaining state

| Classification | State / next evidence |
| --- | --- |
| COMPLETE | Matched placement intervention and honest failure analysis; portable placement mechanics; server worker interface/tests; Linux loopback packet cohort; retained failures, focused verification and cleanup |
| ADMIN_REQUIRED | One existing Windows matched Direct CPU capture command in [the ordered ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md). No repeated handshake ETW capture or new elevated command requested. |
| EXTERNAL_HARDWARE_REQUIRED | Native Linux/server and physical NIC/two-host execution, real 8/16/32-core scaling, qualified profiler/thermal evidence. [External definition](EXTERNAL_LINUX_SERVER_VALIDATION.md) identifies executable subsets and remaining remote orchestration gaps; it is not a claim that the full remote matrix is implemented or run. |
| BLOCKED_ARCHITECTURAL | Existing federation package manifest/trust-anchor/version mismatch. It remains fail-closed. Resolving immutable package compatibility/authority requires a protected decision; no pin or assertion was silently changed. [Blocker](FEDERATION_PACKAGE_AUTHORITY_BLOCK.md). |
| BLOCKED_DESTRUCTIVE | None introduced; no destructive repository/system action is needed for this checkpoint. |
| OPTIONAL_LOW_VALUE | Further invasive WSL probes or repetitions seeking a favorable drift result without a newly qualified observer. Prior distortion/failure evidence remains authoritative. |

Residual handshake and B5 residency/latency cause remain PLATFORM_DIAGNOSTIC_LIMIT,
not proven production bottlenecks or hardware ceilings. No guessed production
optimization is justified. The next useful causal evidence is a qualified
observer or native host, followed by any justified fix and capacity reruns.
Near-ceiling 60/120-minute soak and final whole-campaign acceptance remain open.
Separate short runs must not be added together and called a continuous soak.

Private-origin Docker isolation and the prior adversarial matrix retain their
recorded scope; no production security code changed here. Federation admission
preflight remains separate from live runtime federation, which is NOT_PROVEN.
Do not claim that every current conformance test is green given the known package
trust-anchor failure. The final funding freeze waits for these explicit closures.

## Verification, budget and cleanup

Placement validation: 187 focused Python tests, Ruff and exact release builds
passed at that stage. Portable driver: focused RED/GREEN and live mechanics
collection passed. Worker extension: focused release Rust tests, all-target
release Clippy `-D warnings`, fmt, Python topology tests and Ruff passed.
Linux B1 final scope: 51 Python tests, Ruff, 20 zero-loss captures, canonical
privacy, 32 canonical index entries and 423 raw index entries passed. Exact
commands/logs and source-bound before/after evidence are retained; these counts
are stage scopes, not a sum of distinct full-suite tests.

Safe cleanup removed only owned disposable container build/checkouts and completed
campaign containers, after raw evidence verification. Source, images required for
reproduction, release binaries, authoritative pcaps/traces, unfavorable runs and
Git data remain. The checkpoint evidence includes all four cleanup inventories
and approximate writable-layer bytes; Docker VHD space is not claimed as recovered
host SSD space. Final process/disk status is recorded separately.

Weekly usage was 52% at the start of the authorized 20-point continuation and
65% at the latest pre-checkpoint observation (approximately 13 points used;
usage reporting is coarse). The allowance is a cap, not a target. Further tokens
do not substitute for unavailable native/elevated evidence or authorize a frozen
authority change. No routine approval is needed for subsequent safe work.

Campaign recommendation remains **MORE ENGINEERING REQUIRED**. Conservative
technical outreach can use the measured, source-scoped claims above, with the
soak, native/server, authority and live-federation limitations disclosed.
