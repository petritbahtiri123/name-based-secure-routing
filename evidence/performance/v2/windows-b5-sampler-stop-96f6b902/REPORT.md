# Windows calibration and interrupted B5 observer cohort

Measured source: `96f6b9022da77d671208f51124da054e3a1efa9b`, clean feature branch.
Scope: Windows loopback, release binaries, verified physical-core representative
affinity; the operating system was not isolated from those cores.

## Finite calibration

Fifty valid repeats are retained across the three indexed calibration roots.
The one-core shape used one endpoint group, 64 streams, 1 KiB, and one worker.
The four-core shape used four groups with 64 streams each. The depth-eight
refinement has matching source, binaries, topology and workload parameters;
it adds a distinct depth and does not replace unfavorable repeats.

| Shape/path | Depth | Median Gbit/s | Classification |
|---|---:|---:|---|
| One core Direct | 1 | 0.862839 | STABLE |
| One core NBSR | 1 | 0.873115 | STABLE |
| One core NBSR | 2 | 0.936715 | DEGRADED |
| One core NBSR | 4 | 0.968077 | SATURATED |
| Four cores NBSR | 1 | 2.182004 | UNRESOLVED: repeat dispersion |
| Four cores NBSR | 2 | 2.391092 | DEGRADED |
| Four cores NBSR | 4 | 2.465095 | DEGRADED |
| Four cores NBSR | 8 | approximately 2.434691 | SATURATED |

These are finite workload results, not maximum production capacity. The
four-core shape has no accepted strict-stable baseline. Full classifications,
repeat ranges and CPU estimates are in the two retained analysis files.

## B5 observer qualification: INVALID_PARTIAL_DIAGNOSTIC

The predeclared comparison ran 120 seconds at 70% of the one-core NBSR finite
reference, with periodic ownership collection off/on. Three complete pairs
were valid diagnostics. Latency dispersion required five pairs. The next
cell, `on-r4`, failed; no replacement or later cell was run.

The three-pair median impact was within the observer point thresholds, but
that prefix DOES NOT qualify the observer. `comparison.json` is the final
classification; `comparison-after-3.json` retains the intermediate calculation.
Several valid diagnostics achieved less than 95% of offered operations. They
do not qualify as sustained capacity even though their diagnostic accounting
passed. Individual latency spikes remain in the raw progress records.

The failing cell reported `B5 stream failed: authoritative resource sampling
stopped`. Its last source resource record was about 123.255 seconds after
sampler startup, following a destination record at 122.748 seconds. Terminal
mixed progress was retained, but no source final result or completed source
ownership report was obtained. Destination PASS/cleanup alone does not prove
successful source completion.

Source inspection shows the sampler can stop after a ProcessLookupError once
all roles have been observed, while discarding that original exception. The
controller correctly rejects stopped sampling while the source is active.
The original failing PID, API location and OS error were not preserved.
**The live cause remains UNRESOLVED; no lifecycle race or NBSR defect is proven.**

## Focused diagnostic repair

Retain the original lookup exception, attach the attempted role/PID, and chain
it into the existing stopped-sampler error. Persist a bounded exception
traceback in failed B5 records, without local-variable dumps. This changes no
sampling calls, cadence, stop acceptance, workload, deadlines, success gates,
production code, wire behavior or security semantics. It repairs missing
diagnostic evidence; it does not claim to fix the underlying live failure.

Literal RED: two new sampler cases failed for absent notes/cause; the B5
failure-retention case failed for missing traceback. GREEN: 71 focused tests
passed across resource sampling, B5 framing and B5 controller modules. Ruff
and `git diff --check` passed. One focused parent review found no Important
correctness/security issue in this diagnostic-only change. Successful ACK,
failure-tail preservation and rejection behavior remain covered.

All 597 indexed external artifacts were freshly hashed before packaging.
`raw-evidence.json` identifies retained canonical external roots and index
hashes. Nested indexes are included; these counts overlap where an index
references another retained artifact. No evidence or build cache was deleted.

Next: a separately declared diagnostic may reproduce the sampler failure
with retained causal detail. Do not pool it with this stopped cohort or claim
that the observer/long soak has qualified. B5 near-ceiling closure remains
NOT_PROVEN.
