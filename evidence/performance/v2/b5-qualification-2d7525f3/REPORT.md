# B5 qualification at 2d7525f3

Status: PARTIAL / NOT A FINAL FREEZE. Windows loopback, one selected logical processor on one verified physical core; source and destination share that core. No production change in this stage.

## Finite references (MEASURED, exact stage)

The 64-stream 1 KiB reference retained all ten valid results. Direct median 0.863206 Gbit/s is STABLE. NBSR median 0.854402 is SATURATED under the classification gates: CV 10.58%, including the valid 0.666373 result and a p99 ratio up to 2.23346. It cannot qualify a soak. Its unfavorable run is retained; no causal attribution is established.

The separately declared 32-stream 1 KiB ladder retained 22 valid runs. Depth 1 Direct/NBSR are STABLE at 0.822045/0.812138 Gbit/s. Depths 2 and 4 are SATURATED for both paths. No degraded cell was observed in this shape. This different workload does not replace or repair the 64-stream result. The exact NBSR 70% offered rate is 5206274500000 / 150044089 operations/s.

## Post-buffer-reuse and observer evidence (DIAGNOSTIC)

Three fixed-load 120-second 64-stream NBSR runs completed at 0.587282, 0.587801, and 0.589239 Gbit/s. Both final eleven-counter reports are zero in every run. The short private-growth alarm did not recur; this is not a long-run leak-fix claim. Goodput CV was 0.1724%; source private-peak CV was 0.3908%.

The 32-stream ownership off/on comparison completed three counterbalanced pairs, each 120 seconds. Median goodput impact was 0.02795%, median steady-window p99 impact 0.80331%; all four CVs were below 0.5%. The predeclared 5% observer gate passed. Both arms retain final eleven-counter reports. This qualifies periodic ownership observation for this NBSR workload only, not arbitrary workloads or Direct performance. Quantiles are medians of window p99 values, not pooled-operation p99.

## Ten-minute gates (FAIL / PARTIAL, all attempts preserved)

The matched Direct/NBSR controller stopped on its first Direct cell: 4,199,083 completed of 20,818,978 offered operations, 0.114662 Gbit/s, 20.1695% achieved/offered, below the unchanged 95% gate. Errors/timeouts were zero and process joins completed. Direct runtime ownership was NOT_MEASURED. Low goodput and high p99 existed in the first 30-second window; the cause remains UNRESOLVED. This is not evidence of NBSR overhead or a measured host ceiling. NBSR was not executed by that aborted matched controller.

A separate NBSR-only qualification then completed one ten-minute accounting run: 0.555331 Gbit/s, 97.6842% achieved/offered, zero errors/timeouts, both final eleven-counter reports zero, sampled ownership SAMPLED_NO_SUSTAINED_GROWTH. Repeat 2 aborted at its first 30-second progress window on live private growth in the source. No replacement and no third repeat. Its source private bytes reached 2,887,680; startup-inclusive resource samples do not establish the steady-growth cause. The qualification cohort therefore FAILS; one valid repeat is not stable soak evidence. No 30/60/120-minute stage is authorized by these results.

## Integrity and next work

raw-evidence.json identifies six retained raw roots and SHA-256 indexes; all 470 indexed artifacts were freshly verified. Binaries, unfavorable valid results, failed partial runs, raw telemetry and ownership reports remain in those roots. Copied analyses and logs have this package's independent checksums. Original bytes are preserved. No source, production, timeout, workload gate or security semantics changed in this evidence stage.

Next: attribute the paced Direct loss and the second NBSR private-growth abort without relaxing gates; preserve the successful ten-minute prefix. A diagnostic repeat is a new explicitly bounded experiment, never replacement evidence. The larger mission still needs long-soak closure, portable Linux B5 execution/full external definition, and final quality/security/privacy/evidence freeze. No server or live-runtime federation claim is established.
