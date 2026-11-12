# Demo evidence journey implementation plan

Goal: show the proven allow/reject boundary without inventing per-hop telemetry, and fail clearly on dashboard disconnection.
Architecture: extend existing vanilla JS/HTML/CSS only; keep runner/verifier/protocol and API unchanged. The human requested implementation of this scope after finishing the base test. No new dependencies or architecture.

- Add deterministic scenario descriptions tied to exact source/test assertions. Mark path setup as schematic, terminal assertion as verified only when current outcome PASS, scenario_outcome PASS, cleanup CLEAN and errors empty. Failure/cancellation/running never highlight success. Live application body/backend count are endpoint evidence, not individually timed authorization hops.
- Add explicit disconnected/stopped states; abort bounded HTTP waits, disable remote actions, preserve last evidence labeled historical, never replay POST; provide terminal recovery guidance. Guard late responses from clearing disconnected state. Show submitting immediately; update all controls together.
- Add Node built-in VM regression harness for actual app.js using a minimal fake DOM/fetch, including pending POST network failure, stale poll response, unchanged old evidence, PASS/CLEAN gating and all six scenarios. Node is dev-only, not runtime prerequisite.
- Update README and area guidance, review diff/security boundaries. Retain current manifest before rebuilding with existing isolated caches and unchanged cumulative limits, coordinated with benchmark owner. Native macOS remains unverified. No commit/push/send.
