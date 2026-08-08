# NBSR performance benchmarks

The authoritative entrypoint is `python scripts/run_performance_validation.py`.
The harness supports `calibration`, `latency`, `capacity`, and `load`. Formal
evidence is written under `evidence/performance/`; tests use temporary paths.
The loopback manifest is descriptive and does not change the host power plan or
affinity.

No benchmark command enables 0-RTT or bypasses NBSR admission. HTTP/3 is `NOT
SUPPORTED BY CURRENT TEST SURFACE`.

