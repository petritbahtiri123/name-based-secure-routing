# B3 shared marker monitor — 2026-09-14

Status: benchmark-only implementation verified; matched 2048-bundle rerun remains FAIL.
Base: `0288122db02dce0931326dea3e993fdf78c3d189`. No production transport,
protocol, authority, security or timeout setting changed.

## Measured problem and change

The earlier 2048-waiter diagnostic measured substantial CPU in per-client
10 ms filesystem polling. A new counterbalanced offline comparison evaluates
the actual implementation against the retained original waiter, on one selected
Linux guest CPU. Each cell has five repeats, 2048 absent-marker waiters and a
two-second measurement after a 30 ms registration settling period.

| Unrelated directory files | Original median CPU | Shared monitor median CPU |
|---|---:|---:|
| 0 | 33.970% | 17.984% |
| 8192 | 34.984% | 17.487% |

These are DIAGNOSTIC CPU measurements, not admissions or throughput. Cell CV is
9.6–18.6%; all five repeats are retained. `/proc/self/stat` resolution is 10 ms.
Pending-task controls are at or below one CPU tick. No QUIC traffic was present;
the experiment does not attribute all handshake failures to marker polling.

The selected implementation shares one 10 ms polling timer per lifecycle shard,
checks the same individual file paths, and wakes only completed waiters. It is
enabled only for the benchmark's hold-for-release lifecycle mode. Each wait
retains its own original timeout; a file takes precedence over a timeout as
before. A directory cannot satisfy a file marker. There is no global cache.
Cancelled registrations are removed at the next scan. Normal shutdown aborts
and joins the scanner; owner drop also aborts it. A stopped scanner fails closed.

The preliminary directory-scan prototype was not adopted: its cost depended
strongly on unrelated directory entries. Its initial teardown-order failure is
retained as INVALID, not included in either comparison. No prototype code enters
the production library or the retained monitor.

## Verification and next gate

- Literal RED: matching-marker regression failed against the unimplemented API.
- GREEN: nine focused release Rust tests, including cancellation, shutdown,
  marker identity, directory rejection and active-before-release ordering.
- 68 related Python tests pass; one existing skip.
- Release benchmark-feature clippy with `-D warnings`, default source-bin check,
  fmt and diff checks pass. Default-bin check retains existing unrelated warnings.
- One focused parent review: no protocol/security authority paths changed;
  monitor lifetime belongs to the runtime owner, not cloned wait handles.

Canonical evidence: `evidence/performance/v2/b3-marker-monitor-0288122d`.
Raw source archives plus exact overlay files bind the pre-commit CPU/test builds.
Exact-commit builds and five counterbalanced pairs are now retained under
`evidence/performance/v2/b3-marker-monitor-pairs-d76cc302`. Both variants fail
all five full 2048-bundle attempts on one guest CPU. Median source/destination
active-marker count rises from1470 to1774; source handshake timeouts fall from578
to273. Median pre-start source CPU falls from0.549498 to0.359704 effective cores.
These are improvements inside failed workloads, not sustainable admissions/s or
a new stable scale. Retained destination UDP drops remain; closed sockets and
precise drop timing are unobserved. No hardware ceiling is established.

Next attribution question: B3's deliberately serialized acceptance arms one
handshake at a time to avoid premature accept deadlines. Determine whether
head-of-line handshake waiting contributes to the remaining failure, while
preserving the original paced arrival schedule and timeout values. Do not simply
re-arm all accepts at startup or reopen the previous deadline defect.
