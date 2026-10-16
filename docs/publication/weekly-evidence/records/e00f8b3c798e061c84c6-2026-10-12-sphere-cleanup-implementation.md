# Local relay cleanup failure isolation â€” 2026-10-12

Implemented the approved cleanup proposal in the isolated ad77d597 source. A cleanup
exception no longer skips other owned relays. Partial startup retains the exact
child and closes available handles. Outcomes retain unconfirmed ownership and at
most 16 distinct stage/type errors per role (type names capped at 64 characters).
Both finite and lifecycle coordinators reject incomplete local cleanup before PASS.
Driver failure type evidence is attempted even when cleanup-result persistence fails.

Validation: 56 focused tests and 10 post-close neighbors passed (66 distinct tests).
The original regression run retained 7 expected failures. An intermediate 22-test
pass emitted two fake-stream finalizer warnings; fixture teardown was corrected and
the final runs emitted none. Independent review identified an old positive-cleanup
fixture: its exact test failed before correction, then all 10 post-close tests passed
with the original mode-mismatch assertion unchanged. Production source review found
no further scoped defect. Ruff passed for all five changed Python files. Final independent review verified
the counts and eight implementation/document hashes.
All commands, resource readings and direct-child reap outcomes are in the adjacent
JSON manifest and external retained cleanup-* logs.

These tests use fake processes, readers and clocks. No SSH, network, remote process,
credentials, signatures, production trust or settings were changed. The supervisor
owned only the bounded local test workers. Prior KAR and offline-config artifact
hashes were checked unchanged; their historical coordinator hashes remain snapshots.
The original dirty repository was not edited. No commit or publication occurred.

Remaining prerequisite: a separate cleanup-inclusive whole-trial watchdog. Existing
per-operation timeouts do not establish a 120-second total bound; blocking pipes,
writer-thread tracking, host loss and remote cleanup proof remain outside this slice.
`REQUIRES_EVIDENCE` is not remote cleanup confirmation or READY.

Final process inventory: CIM access was unavailable. The fallback Get-Process
query found no python/cargo/rustc/git/ssh processes. Every supervised worker
reported direct-child reap; no remote resources were created.
