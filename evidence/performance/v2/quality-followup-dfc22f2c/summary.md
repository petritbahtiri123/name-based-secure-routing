# September 25 quality and safe-storage follow-up

Scoped quality closure; not final performance/security certification or funding
freeze. No production transport, wire, authority or security behavior changed.

| Check | Observed result |
|---|---|
| Python performance suite | Initial 5 FAIL /1600 PASS /3 SKIP retained; after focused repairs,1612 PASS /3 SKIP in208.71s |
| Rust release benchmark-harness suite | Initial one CloseTimeout retained; unchanged focused test5/5 PASS; full isolated `--test-threads=1` rerun406 PASS /2 ignored, including16 doc tests |
| Rust release all-target Clippy | PASS with `-D warnings` |
| Cargo fmt | PASS |
| Go race suites | Client, interoperability peer, ISP adapter PASS; demo initial cancellation-fixture failure retained, then full demo PASS after test-only repair |
| Go vet | All five modules PASS; affected demo package rechecked PASS |
| Federation verifier | FAIL_RETAINED: `TestCheckedInPackage: untrusted manifest digest`; existing BLOCKED_ARCHITECTURAL, trust binding unchanged |
| Python Ruff | Initial three test-style errors retained; final scoped check PASS |
| Dependencies / privacy | PASS, original manifests unchanged; privacy119 scoped files |

The isolated Rust rerun does not erase the concurrent-load failure or prove its
cause. Production Rust remained unchanged. Python and Go follow-ups bind their
own source commits in raw provenance; this is not an all-tests-at-one-SHA claim.
The Python skips and Rust ignored tests are not passes.

Windows durable cleanup: a real parent-exits/child-survives RED proved false
authority eligibility in the old ancestry-snapshot runner. `ce67f206` assigns a
suspended child to an owned kill-on-close Job Object, checks zero active members,
and rejects successful parent exits leaving descendants. Query/launch errors
cannot claim verified cleanup.41 affected tests, actual Windows regressions,
Linux completion/timeout smoke, Ruff and focused review pass. Ordinary benchmark
descendants are covered; no malicious-process sandbox or crash-proof preassignment
claim. Workload deadlines and protocol semantics are unchanged.

Three short timeout tests now prepare their fixtures before their unchanged0.4s
deadline; an unprepared-child regression still times out. `dfc22f2c` reuses the
existing bounded authority-worker idle assertion in the Go phase fixture. The
same zero counters remain required;20 focused race repeats and the full demo
race suite pass. No production leak or performance improvement is claimed.

Safe storage maintenance compressed1061 exact indexed completed native raw files
in place. Every original SHA256, logical size, path and modification time was
verified unchanged; no file was deleted. Allocated-byte savings2,290,399,694
(approximately2.13GiB). Host free space was separately recorded and is affected
by concurrent unrelated writes. All selected inputs, commands, per-file before/
after hashes and allocation counts remain in the two raw maintenance packages.
No active benchmark executable, source, Git data or personal files were targeted.

Reproduction commands and source archives are retained in the referenced raw
roots. `raw-evidence.json` binds each full raw index. Original unfavorable logs
and focused RED captures remain alongside follow-ups. Remaining platform timing,
qualified soak, production-ceiling and external-hardware gaps are unaffected.
