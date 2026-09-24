# Paired native live observer qualification

Release/source: 94209a9c97b9fbf0442e0423f14f1ca23f5bfbb8.
REJECTED_OBSERVER_GATE. Ten functional cells pass with zero errors/timeouts,
all requested NBSR eleven-counter cleanup reports zero and twenty exact owned
PIDs absent before Docker fixture stop. All five counterbalanced pairs retained.

Both arms: NBSR, 1,000 offered ops/s, 16 KiB, eight streams, depth one,
3-second warmup/20-second issue, guest CPU 0 per peer, post-close reports ON.
Only source/destination live guards and management telemetry change off/on.
Fresh authority per repeat; exact certificate bytes within each pair.

Predeclared gates remain absolute median paired goodput and p99 effects <=5%,
with goodput CV <=5% in both arms. Median paired goodput effect is -0.049127%;
median paired p99 effect is +29.339579%. Goodput CV: off 0.093985%, on 0.127981%.
Latency uses median steady-window p99, not a pooled quantile. All per-pair effects,
drift failures and latency dispersion are retained in analysis.json.

This does not establish causal observer cost: latency varies materially in both
arms, including one pair where ON is substantially faster. It does establish
that this experiment fails the agreed timing qualification. No optimization or
repeat-until-PASS follows. New live guards cannot yet support qualified timing
at this workload, much less near-ceiling or long-duration stable claims.
Functional accounting, bounded cancellation and independent resource-log replay
remain useful within their separately accepted diagnostic scopes.

Historical CPU appendix reuses unchanged ac40740c post-close raw evidence.
Summed peer CPU deltas divided by the union of their overlapping sampled lifetime
intervals give median allocated guest-CPU occupancy of 95.908726% Direct and
97.703343% NBSR. Both peers selected guest CPU 0 in the same local Docker/WSL
engine. This is DERIVED/HISTORICAL/DIAGNOSTIC: includes startup/warmup/drain,
excludes harness CPU, and is not steady CPU ns/op, physical-core verification,
a whole-host ceiling, a stable reference or production call-stack attribution.
Never combine independent remote monotonic clocks with this formula.

Reproduce:

```powershell
python evidence/performance/v2/native-paired-observer-94209a9c/analyze.py --root C:/NBSR-build/native-paired-observer-94209a9c
python evidence/performance/v2/native-paired-observer-94209a9c/cpu_diagnostic.py --root C:/NBSR-build/native-post-close-ac40740c
```

No production/security change. Qualified native reference, reference-bound
long-duration orchestration and genuine 60/120-minute near-ceiling soak remain
open. Do not substitute this short, low-rate comparison for any of them.
