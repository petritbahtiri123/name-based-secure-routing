# External server worker-scale preparation

Status: benchmark interface implemented; 8/16/32-core performance NOT_RUN /
EXTERNAL_HARDWARE_REQUIRED. No scaling efficiency or server capacity claim.

The prior loopback matrix and benchmark runtime accepted only 1/2/4 workers,
although the approved external matrix lists 8/16/32 cores. Both Direct and NBSR
now accept 1/2/4/8/16/32 workers through the common benchmark-only parser/runtime.
The one-worker current-thread runtime and default 1/2/4 loopback matrix are
unchanged. This code is gated by `benchmark-harness`; no production protocol,
security checks, worker default, timeout, wire format or dependency changes.

The server example is `config/benchmarks/linux-server-loopback-finite.json`.
Use the native build/manifest procedure in `EXTERNAL_LINUX_SERVER_VALIDATION.md`
with the exact reviewed source SHA, then run from the clean repository:

```bash
python3 -B -m scripts.performance.linux_loopback \
  --matrix config/benchmarks/linux-server-loopback-finite.json \
  --binaries /absolute/immutable-linux-binaries \
  --build-manifest /absolute/build-manifest.json \
  --output /absolute/new-server-loopback-output
```

The complete example requires at least 32 allowed physical cores on one NUMA
node, one logical CPU per core. Selection never fills missing physical cores
with SMT siblings or crosses NUMA nodes silently. On a smaller host, retain an
external copy of the matrix containing only available core counts and record
excluded counts as NOT_RUN / EXTERNAL_HARDWARE_REQUIRED. Do not present an
oversubscribed runtime test as a physical-core benchmark. Both peers share the
selected pool; each has the stated worker count, so this is not disjoint peer
placement. Shared CPU and all thread affinities are recorded.

The runner's existing finite Direct/NBSR counterbalancing and repeat policy
remain in force. It does not establish a strict-stable ceiling, sustained soak,
multi-host path, physical NIC throughput or complete external matrix acceptance.
No 8/16/32-core hardware is available in the current WSL environment. The added
Rust test exercises runtime construction, worker count, task completion and drop;
the Python test verifies synthetic physical-core selection and symmetric command
arguments, and rejects insufficient physical cores. Neither is a scaling result.

Literal RED: Python rejected the server matrix, and the release Rust test returned
InvalidValue for eight workers before the implementation changed. Focused GREEN
then exercises 8/16/32 runtime construction and completion of 64 tasks per runtime,
while invalid counts remain rejected. See retained verification evidence for
exact commands and toolchains.
