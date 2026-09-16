# B5 allocator sampler: diagnostic results, not qualified attribution

Ten 300-second runs completed at the unchanged fixed historical offered rate
`64804600000000 / 7500349701` ops/s. Exact release binaries: `f8925b25`.
Linux Docker/WSL loopback, one selected guest CPU, 16 KiB, eight streams, depth
one, three-second warmup, 30-second progress. Ownership sampling was enabled in
both arms. Five counterbalanced allocator-off/on pairs were retained; the first
three on-arm p99 medians had 6.83% CV, triggering the extension to five.

The diagnostic library reads glibc `mallinfo2` every ten seconds on its own
thread and writes a separate per-PID file. It selects only the two NBSR benchmark
executable names, requires an explicit output-directory environment variable,
does not interpose allocation calls, and joins its worker at process exit.
It changes no production source or binary. It is not a production component.

## Observer comparison

| Metric | Allocator off | Allocator on | Median delta |
|---|---:|---:|---:|
| Gbit/s | 2.239750 | 2.237813 | -0.0865% |
| Median window p99, ms | 1.258867 | 1.284597 | +2.0439% |
| Approximate summed peer guest cores | 0.745650 | 0.751178 | +0.7413% |
| Goodput CV | 0.6143% | 0.7572% | -- |
| Window-p99 CV | 1.1958% | 5.5178% | -- |

Paired p99 deltas were +2.530%, -0.690%, **+14.809%**, **+7.646%**, -1.384%.
The two differences above 5% and unresolved on-arm dispersion prevent a
negligible-observer-effect claim. Classification: **NOT_QUALIFIED_FOR_CAUSAL
PERFORMANCE_ATTRIBUTION**. This does not prove the library caused those changes.
Do not select only the passing or favorable pairs to qualify it.

Three off runs and four on runs passed the existing diagnostic gates. Off r1
failed source-private growth. Off r3 failed goodput drift, p99 drift and
destination-private growth. On r3 failed p99 drift. All ten completed traffic
with zero errors/timeouts, passed sampled-ownership growth checks, and finished
with all eleven ownership counters zero at both peers. Failed runs remain FAIL.
Independent five-minute runs are not a continuous 50-minute soak.

## Allocator observations

The analysis verifies PID identity, monotonic timestamps, initial/final records,
at least 29 in-phase samples per role, gaps below twelve seconds, and resource
alignment error below one second. The full analysis retains every sample.
The sampler adds a thread and file descriptor per peer; its allocations are
part of the observed process. No instrumented memory total is a baseline cost.

All ten instrumented role series had constant `hblkhd` of **3,018,752 bytes**
during steady samples. This is an aggregate allocator field, not address-level
proof that one particular allocation stayed alive. Source accounting
(`uordblks + hblkhd`) first-to-last changes ranged from -14,960 to +34,496 bytes;
destination changes ranged from -149,088 to +149,952 bytes. These fluctuate,
and allocator accounting is not exact application ownership.

Examples retained as DIAGNOSTIC leads:

- On r1 source private residency rose 73,728 bytes while accounting fell 14,960.
- On r3 destination residency rose 49,152 bytes while accounting fell 148,960;
  arena free bytes rose 259,552.
- On r5 destination residency rose 20,480 bytes while accounting fell 149,088.

The data therefore do not support equating residency growth with growth in
allocator-accounted memory. They do not establish allocator retention as the
cause of the uninstrumented failures, absence of a leak, a production defect,
or a hardware ceiling. Maximum observed in-phase `mallinfo2` duration was
16,300 ns; this excludes output and cannot qualify the entire observer.

## Verification and next step

Literal stub RED failed for missing trace; GREEN passed activation, parseable
initial/final output, bounded join and unchanged fixture output. Final tests
also passed executable filtering and absent opt-in. C used `-Wall -Wextra
-Werror`; focused Python checks: 26 PASS; test Ruff PASS. No production
optimization or gate change was made.

Canonical: `evidence/performance/v2/b5-allocator-sampler-7d131c71`.
Raw: `C:/NBSR-build/b5-allocator-sampler-7d131c71`; exact release-build index is
also bound by the package. Preserve the executed runner/library and failed runs.
Reproduction commands and source are retained; use a fresh output directory.

Memory attribution remains PARTIAL and p99 cause UNRESOLVED. Do not add more
intrusive allocator hooks to force a conclusion. The next lower-impact avenue
is externally observed scheduler/wait accounting, if this guest exposes it;
otherwise native-host profiling remains an explicit validation limitation.
