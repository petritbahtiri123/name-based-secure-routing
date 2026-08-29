# B4 Mixed Workload

Classification: **PASS**

Established NBSR application streams and newly admitted application streams share one authenticated connection, route, control stream, destination runtime, and process. Admissions are paced serially because the frozen control-session state machine is single-owner.

| Offered admissions/s | Repeats | Established Gbit/s | Goodput/baseline | Established p99 ns | p99/baseline | Successful/scheduled | Failures | Timeouts | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 0 | 3 | 0.373 | 1.000 | 817000 | 1.000 | 0/0 | 0 | 0 | BASELINE |
| 25 | 3 | 0.370 | 0.990 | 817700 | 1.001 | 250/250 | 0 | 0 | STABLE |
| 50 | 3 | 0.373 | 0.999 | 811900 | 0.994 | 500/500 | 0 | 0 | STABLE |
| 100 | 3 | 0.371 | 0.993 | 818000 | 1.001 | 1000/1000 | 0 | 0 | STABLE |
| 400 | 3 | 0.369 | 0.987 | 821400 | 1.005 | 4000/4000 | 0 | 0 | STABLE |
| 800 | 3 | 0.360 | 0.965 | 830600 | 1.017 | 8000/8000 | 0 | 0 | STABLE |

No saturation point was observed in the bounded sweep.

## Resources and backpressure

- 0 admissions/s: 12.78 median aggregate CPU-seconds over the sampled process lifetimes, 18.7 MiB summed peak working set, 6.0 MiB summed peak private bytes, 0.000 ms median maximum scheduling lateness.
- 25 admissions/s: 12.47 median aggregate CPU-seconds over the sampled process lifetimes, 19.1 MiB summed peak working set, 6.3 MiB summed peak private bytes, 0.769 ms median maximum scheduling lateness.
- 50 admissions/s: 12.64 median aggregate CPU-seconds over the sampled process lifetimes, 19.3 MiB summed peak working set, 6.4 MiB summed peak private bytes, 1.508 ms median maximum scheduling lateness.
- 100 admissions/s: 12.67 median aggregate CPU-seconds over the sampled process lifetimes, 19.5 MiB summed peak working set, 6.6 MiB summed peak private bytes, 1.416 ms median maximum scheduling lateness.
- 400 admissions/s: 13.42 median aggregate CPU-seconds over the sampled process lifetimes, 20.2 MiB summed peak working set, 7.4 MiB summed peak private bytes, 1.713 ms median maximum scheduling lateness.
- 800 admissions/s: 14.34 median aggregate CPU-seconds over the sampled process lifetimes, 21.0 MiB summed peak working set, 8.2 MiB summed peak private bytes, 9.585 ms median maximum scheduling lateness.

Per-role CPU, working-set, private-byte, and thread samples are stored in each raw record. Maximum admission scheduling lateness is the available backpressure signal.

Limitation: this validates application-stream admission on an existing authorized route. It does not prove concurrent new transport connections or new route admissions; that requires a broader benchmark-only multi-connection server mode and remains external B4 closure work.

Base Git SHA: `e8d61c7bd6a5fd0467381163f5a1bbac20b8d2bb`
Host: Windows-11-10.0.26200-SP0 / Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz
Command: `scripts/run_b4_mixed_workload.py --output 'evidence\performance\mixed-workload-b4-e8d61c7' --repeats 3 --admission-rates 0,25,50,100,400,800 --duration-seconds 10`
