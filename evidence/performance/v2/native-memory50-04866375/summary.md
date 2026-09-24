# Native fifty-cycle private-memory retention diagnostic

MEASURED release04866375, Docker/WSL namespaces:3/3 repeats,150/150 sequential
same-process authenticated1024-byte round trips. One connection/session/channel/
stream per cycle. All six owned PIDs absent before container stop; no forced
relay cleanup. Every source per-cycle closed report and both final eleven-counter
ownership reports zero. Destination per-cycle closed ownership not separately
measured. Cooldown FD/thread counts remain6/1 source,8/2 destination.

One-Hz smaps_rollup observations provide private-resident/PSS, bound to process
identity/lifetime/CPU and local active/cooldown intervals. Final private repeat CV:
source0.406%,destination2.461%; final active CV0.406%/1.454%. Three repeats satisfy
the predeclared5% extension rule. Maximum memory capture20.152154ms; neutrality
NOT_ESTABLISHED. Existing50-cycle320-second controller allowance unchanged;
transport/readiness/cleanup/transfer timers unchanged.

DERIVED from all retained cooldown phase medians, source private first-to-last
increase3190784-3215360bytes (about3.04-3.07MiB). Second-half ranges0/4096/12288bytes;
final-ten ranges0/4096/4096bytes. Source late growth is small but not universally
zero. Destination increases161792-370688bytes. Its second-half ranges57344-225280
bytes; final-ten ranges0/90112/102400bytes. Final-ten destination slopes0,
5585.45 and12337.65bytes/cycle. Preserve these unfavorable late changes; do not
claim the whole cohort is flat. Full/second-half/final-ten slopes and every phase
are retained in analysis.json. No extrapolation beyond the measured50cycles.

Classification: functional completion and observed ownership cleanup PASS;
private-retention cause INCONCLUSIVE. These are diagnostic process totals,
not allocator attribution, qualified bytes/resource, leak proof/freedom,
performance capacity or a60-minute soak. Remaining private growth is not grounds
for speculative production optimization.

Current replay also passes the accepted older50-cycle, stream-axis and channel-axis
raw packages. No production code/security/wire change or new throughput claim.

Docker provenance diagnostic: inspect displays an olda401567d /build source path,
while read-only docker cp from8 stopped containers across4 cohorts confirms all24
source-sha/manifest/bundle files byte-identical to their requested host builds.
The cached image retains stale Docker Desktop bind labels. The precise reporting
mechanism is NOT_PROVEN; actual build bytes are verified. Diagnostic procedure
and results retained. No run discarded or raw record rewritten for this artifact.

After checksums and owned-PID absence were verified,60 exited campaign fixtures
were removed.1958019072 logical writable bytes reclaimed inside Docker;
immediate host free space increased only737280bytes. Do not present logical
Docker reclamation as host SSD recovery. Bind mounts, images, host repository source/Git and
canonical raw evidence untouched. Removal occurred after the memory cohort.

Reproduce via NATIVE_SAME_PROCESS_CYCLES.md:cycles50,memory_observer:true,
channels1,streams1,three repeats with the declared CV rule. Retained run.py/setup.py,
configs and release manifests define exact namespace commands. Independent replay:
python -B evidence/performance/v2/native-memory50-04866375/analyze.py C:/NBSR-build/native-memory50-04866375
