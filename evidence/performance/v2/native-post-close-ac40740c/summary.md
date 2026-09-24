# Native finite post-close evidence

MEASURED: exact source ac40740c73c70c3661140ed613f61b693abbf1a9,
release binaries, Docker/WSL internal bridge, both peers on guest CPU 0,
16 KiB, eight streams, depth one, 3 s warmup and 20 s measurement.
Five counterbalanced repeats per path; all ten finite pairs pass payload,
owned exit, role/SHA/workload integrity and independent collection validation.
Each of the ten NBSR role reports passes the existing eleven-zero-counter
contract, bound to its actual owned PID. All twenty owned PIDs independently
absent before container stop under the peer UID; no forced local relay exit.
Direct has process cleanup evidence only; no NBSR counters are imputed to it.

DIAGNOSTIC: Direct median 2.395090 Gbit/s (CV 16.12%), NBSR 2.496439
Gbit/s (CV 12.17%). Median-cell p50/p95/p99: Direct 0.780553 / 1.238889 /
2.161256 ms, NBSR 0.735152 / 1.344196 / 2.124653 ms. These are neither
pooled quantiles nor a strict-stable ceiling. Observer overhead and host
allocation remain unqualified. No before/after speedup, physical-core ceiling,
server/WAN performance, long-run retention or soak claim follows.

Implementation is benchmark-only. Existing production reports and validator
semantics are reused; no Rust/Go production, protocol, security or ACK change.
Focused tests: 75 PASS, preceding literal RED retained, focused review and
follow-up mode-mismatch regression retained. Analysis revalidates raw peer
packages, report binding, requested mode, endpoint indexes and exact-PID checks.

Reproduce validation from repository root:
`python evidence/performance/v2/native-post-close-ac40740c/analyze.py`.
Raw roots and index hashes are in raw-evidence.json. The paired observer
qualification is a separate cohort; native paced B5 orchestration remains open.
