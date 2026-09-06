# B5 explicit path selection

Classification: harness controller change; live capacity NOT_MEASURED.

The NBSR sustained program can select `--paths nbsr`; the default remains
Direct plus NBSR in alternating order. A single-path cohort establishes no
Direct/NBSR comparison. Offered rate, duration, ownership, drift, timeout and
three-to-five repeat gates are unchanged. This avoids requiring a duplicate
long Direct soak merely to obtain NBSR lifecycle evidence.

Literal RED: 14 tests failed before implementation. GREEN: 31 controller tests
passed; parent reran all 31 successfully. Ruff and diff checks passed. A focused
parent review found no important correctness/security issue in the change.
Tests cover fixed 7200-second configuration and both three/five repeat outcomes
with mocked live execution; these are controller tests, not sustained results.

Raw evidence: `C:/NBSR-build/b5-path-selection-redgreen-d56ce7f6`.
The retained raw index binds six original artifacts. Canonical text copies here
are normalized independently and do not replace original bytes.
