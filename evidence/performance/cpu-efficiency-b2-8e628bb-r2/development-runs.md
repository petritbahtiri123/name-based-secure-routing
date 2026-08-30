# B2 Development Runs

`evidence/performance/cpu-efficiency-b2-8e628bb/` is a complete valid 36-repeat run. A post-run formatter check showed that four Python harness files required formatting. Formatting did not change benchmark semantics, but it changed their recorded source hashes, so the full matrix was rerun rather than presenting the earlier run as the final-source baseline.

This `-r2` directory is the authoritative final-source run. The earlier run remains available for audit and is not merged into the final medians.
