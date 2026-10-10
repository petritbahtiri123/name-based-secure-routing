# Transport lifecycle authority activation checkpoint

The additive validator recognizes the explicitly approved source snapshot
`99ac954e0c0d90a221b42492a59fa4d5b962ea5d`. The implementation and evidence at this
checkpoint are local changes over approval-package commit
`8afe21f2741772f1658014bc424c4c986bde08fb`; publication remains paused.

The new authority preserves the four frozen baseline/F75/P1P2/ACK documents and
all 110 legacy inventory entries. It replaces only `lib.rs` and `quinn_adapter.rs`
and checks the closed five-file supplemental inventory: `owned_send.rs`,
`udp_socket.rs`, `benchmark_bind.rs`, `Cargo.toml`, and `Cargo.lock`. All paths
are relative to `crates/nbsr-transport/` (Rust modules are under `src/`). The six
verification sources remain evidence, not additional runtime authority inputs.
This is selected-source acceptance, not complete build closure or production proof.

## Provenance correction discovered during activation

The original inactive proposal and its review results are preserved unchanged.
Their claim that every proposed hash represented raw Git bytes was incorrect:
Windows `git archive` converted the two Cargo files' line endings. The original
37-test proposal result and initial 41/59-test activation results used that same
transformed fixture, so they did not establish raw-source equivalence.

The current-source positive failed on Cargo.lock. A replacement fixture using
`git ls-tree` and binary `git cat-file --batch` reproduced that failure against
the actual approved commit. Comparing all 13 proposed source/evidence entries
found exactly two discrepancies:

| File | Proposal bytes | Raw Git bytes | Raw Git SHA-256 |
| --- | ---: | ---: | --- |
| Cargo.lock | 32155 | 30942 | `976ace41027ae90bebbe2229a1575c1f0c7bc5e71b1847804f4d6d33404c21f8` |
| Cargo.toml | 1018 | 991 | `81103d93ae135c3e7763c5f81ca4960efd581bd881a1de5016a2731054af0d11` |

Only the new activation document's two metadata entries were corrected to the
raw bytes of the explicitly approved source commit. No Rust source, old proposal,
old authority, inventory scope, or accepted inherited limitation was changed.
The active document's independent validator pin is
`d6cc7cf54e0e4752e5662c9a8ee049cb869c3797f4c4770175bf273db9992a79`.
The adjacent JSON retains both old and corrected entries and every trial outcome.

## Validation and independent review

The corrected immutable raw-Git fixture passed **59 tests**: 43 new authority
cases and 16 historical ACK cases (21.28 seconds; supervised 22.49 seconds).
The separate current-source gate passed **4 tests** (57.54 seconds; supervised
58.83 seconds). Both runs completed without resource abort and reaped their
direct child. The historical ACK validator still rejects the later source;
its own positive fixture remains bound to its original `94a1e4a` snapshot.

Negative coverage includes each bound file, missing dependencies, legacy
mutation/removal/addition, malformed or widened inventories, unsafe paths,
duplicate JSON fields, metadata changes and symlinks. Ruff on the four changed
Python files passed. `git diff --check` passed.

Independent read-only review found no technical blocker. It separately read all
seven bound files from `99ac954e` with `git cat-file blob`, verified every length
and hash plus the active document pin, and checked the raw fixture and unchanged
historical behavior. The reviewer did not execute tests; measured test results
are executor evidence. Remaining neighboring results are recorded in the JSON.

Retained negative attempts: missing-API collection failure; the initial
archive-fixture passes; current-source 1 failed / 3 passed; and raw-Git positive
1 failed before correcting the new Cargo entries. None is relabeled as passing.

No hosted CI matrix, clean checkout matrix, Rust rerun, deployment, publication,
or larger network benchmark is claimed. Rust source is unchanged in this
activation. The inherited receive/ACK revoke-then-drop-without-repoll limitation
remains separate work requiring its own reviewed versioned source authority.
No exploratory ACK or operator implementation was started at this checkpoint.

## Remaining local validation blocker

The bounded neighboring federation run completed with **545 passed / 2 failed**
in 33.35 seconds (supervised 34.95 seconds, no resource abort). The two failures
are packet-evidence checks requiring absent local files:
`evidence/wp8-task10/capture-manifest.json` and
`evidence/wp8-task10b/capture-manifest.json`. Git lists both paths as tracked;
their working copies are absent. No evidence was fabricated, downloaded,
restored, or excluded to manufacture a pass. This blocks a full local federation
success claim and is independent of the 63 passing focused authority checks.

That neighboring command excluded the already-run three authority modules,
the unchanged older F75/P1P2 modules, and the independent-wire-peer build test.
Its exact selection and failure logs are embedded in the adjacent JSON. The
older F75/P1P2 standalone modules were not rerun in this activation; the new
validator tests exercise the retained ancestor chain. No expensive retry was
made after discovering the missing evidence. All changes remain uncommitted.

## Sparse evidence resolution before local commit

Read-only Git inspection resolved the two failures: `core.sparseCheckout=true`,
both manifests and captures have `S` (skip-worktree) index flags, and exact
negative entries in `.git/info/sparse-checkout` exclude them. These are committed
assets omitted from this local checkout, not ignored/generated inputs, archive
loss, or missing repository packaging. No user deletion was overwritten.

The expected revision for the packet tests is current HEAD
`8afe21f2741772f1658014bc424c4c986bde08fb`. The task10 manifest was last changed in
`695b583de447ce166f4d051c16550c073874ad1d`; task10b in
`c9ef9660c9d76e343ccc0ffaa8e23d4636b77873`. All four required artifact blobs are
available locally. The adjacent JSON records exact blob IDs, sizes and SHA-256.

Six raw HEAD blobs (the unchanged test module, its capture script and four
artifacts) were materialized with `git cat-file blob` in a fresh task-owned
temporary directory. The unchanged packet test module then passed **3 tests in
0.68 seconds**, supervised **1.81 seconds**, exit 0, no abort, direct child
reaped. This legitimately resolves the two artifact-validation failures in that
materialization. The earlier **545 passed / 2 failed** working-tree outcome stays
visible: the sparse working tree itself remains unchanged and would still lack
those inputs. No blanket skips, weakened assertions, regenerated evidence,
downloads, or full-suite success claim were introduced.

For Cargo, raw `git cat-file blob 99ac954e:<path>` bytes are authoritative.
`core.autocrlf=true` with unspecified text/eol attributes led the earlier
archive fixture to convert LF to CRLF; the proposed lengths exceed raw lengths
by the added carriage-return counts (1213 and 27). The activation corrects only
those two entries to the approved source bytes. The pinned inventory remains
exactly two legacy replacements plus five supplemental files; six test-source
hashes remain evidence only. No authority scope was broadened.

This resolution requires no evidence-file or test-contract code fix. Local
sparse-checkout validation should use exact temporary materialization when
required committed evidence is intentionally excluded. Hosted and whole-suite
validation remain separate unperformed gates; ACK runtime changes stay deferred.

Independent follow-up review verified all six materialized files against Git,
sparse omissions, corrected Cargo pins and the preserved evidence distinction.
It found no remaining blocker to the user-authorized scoped local commit. The
earlier uncommitted statements above describe their checkpoint times. The final
commit is to contain only this authority implementation, its focused tests,
guidance and evidence; it does not authorize push or a signing/protection bypass.
