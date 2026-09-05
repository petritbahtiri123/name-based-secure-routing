# Task 4n: accept-pump observer validation

Classification: **PLATFORM_DIAGNOSTIC_LIMIT** for residual transport-handshake-progress attribution. The optional fixed-size timing observer failed the existing observer gate at both 200 and 250 offered admissions/s. No accept-pump optimization or production-capacity claim is justified by this experiment.

Twenty release runs used 512 clients, two source shards, 30 seconds established traffic and two seconds warmup, with five repeats per rate/observer cell. Rate and observer order alternated. All runs were valid and cleanup was zero. All 201 retained raw artifacts passed SHA-256 verification. Ten profiles conserved exactly 512 accepted connections and their timer histogram totals.

| Offered/s | Observer off admissions/s | Observer on admissions/s | Established goodput impact | Observer gate |
| --- | ---: | ---: | ---: | --- |
| 200 | 134.913 | 137.992 | 8.00% | FAIL |
| 250 | 94.213 | 97.653 | 7.55% | FAIL |

These are DIAGNOSTIC medians, not sustainable capacity. Unfavorable valid runs remain in the raw records. Cross-stage differences are not paired evidence of regression or improvement.

Timing covers wall time inside the existing poll scan and select operation. It includes mandatory transport polling, scheduling/preemption and legitimate waits for paced arrivals. It does not isolate CPU overhead, pure Windows timer latency, or the cause of a delayed handshake. Failed observer validation prevents using these profiles to select an optimization.

The bounded Windows receive-buffer repair and its separate no-drop captured evidence remain accepted within their measured scope. Residual delay remains unexplained; neither host saturation nor a production NBSR ceiling has been established. Further invasive Windows attribution is deferred; independent forwarding, resource, soak, packet-accounting and security work continues.

Reproduce: `python scripts/run_b4b_task4n.py --output C:\NBSR-build\b4b-task4n-NEW`. The runner refuses output reuse, retains binaries/source provenance, and preserves every run. Source identity is the parent SHA plus the retained patch and source copies; the parent SHA alone does not identify these instrumented binaries.

Validation: literal RED then GREEN for fixed-size profile accounting/exclusive output and environment restoration; focused Rust/Python tests, Rust formatting, benchmark-feature binary Clippy with warnings denied, and Ruff passed. The observer is disabled by default and no frozen semantics changed.
