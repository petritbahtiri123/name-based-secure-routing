# Native same-process cycle evidence

Implementation 4375d7ac9af300e2eb0d407d808e794c408d033f. MEASURED functional
Docker/WSL namespace evidence; no physical-server or qualified memory-cost claim.

Three repetitions of four cycles and three repetitions of sixteen cycles PASS:
60/60 sequential connection/session/channel/materialized-stream lifecycles.
One source and one destination PID/start-time epoch persisted per trial. Every
cycle used the existing authenticated 1024-byte round trip, both endpoint active
barriers, two-second hold and cooldown. Twelve positive-trial owned PIDs were
absent before containers stopped. All eleven final ownership counters were zero
for both roles. Source per-cycle closed observations were also zero throughout;
destination per-cycle closed ownership was not measured separately.

Six catchable control-EOF trials PASS: three per role, after the first cycle
completed and both endpoints were active in the second. Twelve owned PIDs were
absent, no local relay forced. These controls do not prove graceful ownership-zero
on cancellation, SIGKILL recovery or network-partition behavior.

Retained per-cycle RSS/FD/thread samples appear in analysis.json. The source RSS
increase during early cycles was retained and investigated with the longer
sixteen-cycle workload. These are diagnostic RSS observations, not allocator
attribution, bytes per resource or a general leak-free claim. No timing-neutral
observer, sustainable admission or physical-core claim follows. No production
Rust/Go, frozen security, wire or trust changes; release binary hashes are unchanged.

Literal RED/GREEN and review: prerequisite 114 affected tests; integration 133
affected tests; Ruff and focused independent review/re-review PASS. Review found
and fixed premature completion markers arriving between polls (two literal RED
regressions). Both fresh release cohorts and failures/cleanup are retained.

Cleanup: six stopped, proven disposable positive fixtures removed after canonical
raw inventory verification (192761856 logical writable bytes; no immediate host
SSD recovery). Two inactive Cargo caches recovered 372752384 measured host bytes.
Candidates with unknown top-level tmp content were skipped. Source, private
fixtures, Git and authoritative evidence were not deleted.

Reproduction: docs/benchmarks/NATIVE_SAME_PROCESS_CYCLES.md; raw run.py/setup.py,
configuration, release build manifest and commands. Read-only analysis:
python -B evidence/performance/v2/native-cycles-4375d7ac/analyze.py C:/NBSR-build/native-cycles16-4375d7ac

Open: per-axis native channel/stream scaling, qualified memory observer/retention
attribution, actual independent SSH/server validation and full matrix completion.
The cycle mechanism is complete within this bounded scope, not final B3 closure.
