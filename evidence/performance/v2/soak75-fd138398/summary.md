# Three one-hour Windows soak observations

Source fd138398549a579b50dd0693fc278d3998b0b3e0; release, one verified physical
core, one endpoint group, eight streams, 16 KiB, depth one, NBSR only. Offered
load is 75% of the fresh strict-stable reference (approximately 0.773375 Gbit/s).
Three independent 3600-second repeats completed 31,139,327 operations with zero
errors/timeouts. Goodput: 0.753500499, 0.754762335, 0.759233408 Gbit/s;
median 0.754762335, repeat CV 0.399%.
Achieved/offered: 97.430%, 97.593%, 98.171%. All issued operations drained;
all process joins passed; both final eleven-counter ownership reports were
zero in all three repeats.

Early-to-late steady-window median goodput changes: -0.800%, +0.093%, -0.193%.
Corresponding sampled p99 changes: +1.347%, -7.601%, +2.622%. Existing live
drift/private-growth guards passed. These are window statistics, not pooled
run latency percentiles. Raw resource samples and diagnostic summaries remain
available; final zeros do not prove continuous ownership stayed bounded.

Classification: ACCOUNTING_PASS_QUALIFICATION_PENDING / PARTIAL_B5.
Periodic ownership qualification stopped on its first enabled trial at 30s
with live goodput drift; the preceding disabled 60s trial completed. The planned
five matched pairs were not completed: observer causality is INCONCLUSIVE.
Both attempts are retained. The long cohort used the same 75% offered workload
without optional periodic ownership, retaining baseline process telemetry and
final cleanup. No threshold or timeout was relaxed. Continuous ownership,
thermal/power attribution, full observer neutrality, Direct long-run comparison
and universal stable capacity remain NOT_PROVEN. No qualified full B5 closure
or two-hour uninterrupted run is claimed.

Reproduce from the stated clean source, choosing a fresh output directory:

```powershell
python -B scripts/run_b5_v2.py --output C:/NBSR-build/soak75-fd138398-20260926 --target C:/NBSR-build/b4b-task4k --reference C:/NBSR-build/soak-reference-fd138398-20260926 --paths nbsr --percent 75 --cores 1 --groups 1 --streams 8 --depth 1 --payload 16384 --duration 3600 --progress 30 --warmup 3
```

raw-evidence.json binds verified retained indexes, including the failed observer
qualification. All indexed bytes were verified after the run. The compression
root records 913 files and 2,115,373,762 allocated bytes recovered without
deletion or content changes. No capture was repeated, no main branch modified,
and no production or frozen security semantics changed.
