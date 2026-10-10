# Windows demo fixture correction — 2026-10-10

Base: `c822a0dd75a137f94482420a225e5f81c845fe60`. This correction is verified and reviewed for the authorized scoped local commit; publication and hosted confirmation remain pending.

Hosted run 38057636484 finished with six passing jobs and Windows Go failing in the demo module. Rust Windows passed. Hosted logs expose error 24 but not the underlying path. A controlled local short-name TMP/TEMP reproduces error 24 in the existing fixture test (RED); resolving fresh test-owned roots clears it (GREEN). This is evidence for the fixture correction, not hosted confirmation.

Seven demo test files now use `internal/testfixture.TempDir`, which resolves only their own fresh temporary directories. Production startup and path validation are unchanged. A Windows regression requires raw caller alias rejection and successful fresh canonical setup under short TMP/TEMP in a child subtest.

Full demo suite under short TMP/TEMP: 73 passing test events (50 top-level, 23 subtests), seven packages pass; four existing real-transport tests skipped because external prerequisites are absent. The helper package has no tests. The new Windows regression and its child subtest ran and passed. Offline bounded vet passed. Full-suite supervisor duration 10.84 seconds; vet 9.94 seconds. Exact commands, logs/hashes, skip diagnostics and source hashes are in the adjacent JSON. Expected failing RED is retained.

Independent static review by full_delta_review found no blocking findings. Production behavior, authority pins and workflow are unchanged. Hosted confirmation requires separately authorized publication. No ACK work was performed.
