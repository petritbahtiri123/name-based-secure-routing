# Fresh Task 4i admission progression

Status: synthetic runner verification only; this document contains no new measured result.

The unchanged default is one source shard and rates 25, 50, 75, 100, 125, 150,
200, 250, 300, 400 admissions/s. The bounded fresh campaign selects two existing
benchmark source shards explicitly:

```powershell
python scripts/run_b4b_task4i.py --output C:\NBSR-build\evidence\task4i-fresh-UNIQUE --source-shards 2 --offered-rates 25 50 75 100 125 150 200 250
```

Use a fresh output path. This command builds and runs benchmarks; synthetic
verification does not execute it. No physical-core affinity is assigned by this
patch. Environment evidence records the chosen rates and shard count, command,
binary hashes and captured source hashes, including shard scheduling and resource
sampling sources. Every attempt retains its JSON and underlying raw evidence.

Each rate requires three valid repeats, increased to five when the first three
valid repeats exceed 5% CV in admission rate or established goodput. An invalid
attempt does not count: after the scheduled three/five attempts, insufficient
valid evidence stops progression as PARTIAL without publishing that cell's
classification. Invalid attempts remain retained and counted. This introduces
no automatic retry or relaxed timeout. Valid but bad measurements still contribute
all errors, timeouts, minimum admission success and cleanup failures; they are
not discarded as invalid. The existing progression stops on saturation only
after a preceding stable cell.

The workload remains a finite batch of 512 clients, at the requested offered
admission rate, with the existing 30-second established-forwarding duration and
2-second warmup defaults. Its admission release window is limited by that batch
(roughly 512/rate seconds); it is not a sustained admission soak or a production
capacity claim. No workload, authority, protocol, deadline or timeout changes are
part of this patch.

Focused synthetic verification:

```text
python -m pytest -q tests/performance/test_task4i_fresh_progression.py tests/performance/test_task4i_rate_capacity.py tests/performance/test_task4k_admission_shards.py
```
