# Preserve B5 receive-clock evidence

Measured problem: the retained `b5-pdh-baseline-failure-1cca67ad` abort has
process monotonic timestamps and source elapsed times, but not the already
computed first-progress receive origin. Its resource-window alignment cannot
be reconstructed under the controller's original convention.

Keep `LiveGuards` timing, drift thresholds, workload and cleanup unchanged.
Serialize the existing `origin_ns` in qualification metadata, explicitly null
when no progress was observed, and preserve that snapshot on failed as well as
successful results. Write it only in the existing final result path, after
sampling/process cleanup. This adds no timed writes or clock reads and does
not turn approximate receive-clock alignment into exact source timing.

- [x] Literal RED: qualification exposes null/first origin and never rebases on
  a later delayed progress record; process integration preserves that origin
  after parser and ownership failures as well as success.
- [x] Minimal implementation in `scripts/run_b5_v2.py`.
- [x] Focused controller tests, Ruff and one scoped review.
- [x] Preserve RED/GREEN/source hashes and atomic commit. Historical missing
  timestamps remain unavailable; no retroactive reconstruction or capacity claim.
