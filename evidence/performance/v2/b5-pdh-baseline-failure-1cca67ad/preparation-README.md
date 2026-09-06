# Authored PDH observer diagnostic — NOT RUN

Only the external driver and pure fixture tests were executed for preparation.
No prebuild, typeperf, controller workload, or cohort has run from this recipe.
Parent must coordinate a clean-SHA quiet slot before either invocation below.
No tests, builds, Docker, or checkout edits may overlap timed cells.

From the NBSR repository PowerShell, replace SHA with the approved full clean
commit and use a fresh prepared manifest and fresh output root. Retain console
stdout/stderr, which include the existing controller's cargo output:

```powershell
$sha = 'REPLACE_WITH_FULL_CLEAN_SHA'
$driver = 'C:/NBSR-build/b5-pdh-observer-preparation/driver.py'
$prepared = "C:/NBSR-build/b5-pdh-prebuilt-$sha.json"
$repo = 'C:/Users/bajra/OneDrive/Documents/NBSR'
$target = 'C:/NBSR-build/b4b-task4k'
python $driver prepare --sha $sha --repo $repo --target $target --prepared $prepared *> "C:/NBSR-build/b5-pdh-prebuild-$sha.log"
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed; preserve log' }
# Parent quiet-slot clearance is required here; this recipe does not grant it.
python $driver run --sha $sha --repo $repo --target $target --prepared $prepared --output "C:/NBSR-build/b5-pdh-observer-$sha" *> "C:/NBSR-build/b5-pdh-observer-$sha.log"
```

The rate is historical fixed rational 421624000000/150013467 operations/s,
not 70% of current capacity. NBSR only, 16 KiB, eight streams, one group,
depth one, mask1, warmup3s, duration120s, progress30s. Both arms disable periodic
ownership sampling; existing final cleanup checks remain enabled. The controller
still calls its normal build helper each cell. A wrapper verifies the prepared
binary hashes after that helper returns and only then starts typeperf. Cargo is
therefore outside observation and workload. A changed binary rejects the cohort.

Six counters: logical0 busy/user/privileged/interrupt/DPC, logical1 busy. Existing
topology must confirm mask3 is one SMT core. typeperf samples once per second,
has a 300-sample lifetime bound, and its exact owned process is terminated and
joined after each cell (5s wait, then bounded kill fallback). Planned termination
exit is not a PDH failure; an exit before stop is a failure. Raw CSV/stdout/stderr,
PID and UTC/monotonic anchors remain external. A truncated/missing/invalid CSV or
unexpected exit invalidates the whole cohort, including its prefix. No restart
or replacement cell occurs. At most ten controller cells run.

Coverage also requires strictly increasing timestamps in the explicitly observed
`MM/dd/yyyy HH:mm:ss.fff` format; unknown locale formats fail. Convert using the
recorded local UTC offset, reject any offset change and any wall/monotonic
anchor-interval discrepancy above3s. Every adjacent sample gap must be at most3s;
the first sample must precede readiness, and the last must reach stop minus3s.
Samples outside the launch/join envelope plus3s also fail. Coverage results retain
the3s boundary uncertainty; timestamps do not establish exact phase causality.

Three alternating pairs expand to five if either arm's rate or p99 metric CV
exceeds5%. Rate is the controller's completed application Gbps. Per-repeat p99
metric is the median of at least three retained steady-window p99 values, not
a pooled per-operation percentile. Absolute between-arm median changes above5%
reject the observer; remaining dispersion is separately marked unresolved.
An incomplete/failed cohort never qualifies the observer, even if a prior prefix
comparison looked acceptable.

Derived counter labels contain no hostnames; raw PDH headers can contain local
hostnames and are not public derived fields. Timestamp strings are typeperf's
local wall clock. UTC offset/monotonic anchors bracket launch/readiness/stop, not
exact counter collection instants. Existing controller resource-phase alignment
remains approximate. Do not infer precise causality from aligned-looking curves.
Busy minus tracked process CPU is not evidence of unrelated applications:
interrupts, DPCs, privileged execution and other OS activity can contribute.
These counters prove neither effective clock, temperature, nor thermal throttling.

On failure, preserve top-level redirected console logs as well as the driver's
checksum-indexed output directory; console/prebuild logs sit outside that index
and must be separately hashed when evidence is packaged.
