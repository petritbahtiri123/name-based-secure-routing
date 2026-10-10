# Corrected transport candidate: approval checkpoint

## Current source and recommendation

The corrected local commit is
`99ac954e0c0d90a221b42492a59fa4d5b962ea5d`, directly on CI commit
`f6400959e93f32f3eec32372c60773c115344583`. It is signed off but not
cryptographically signed. No push or authority activation occurred. Git emitted
the existing `.git/worktrees/nbsr-name-routing` cleanup permission warning;
commit creation and its parent/inventory were independently verified afterward.
No hooks, signing settings or branch protections were bypassed for this commit.

Recommend approving this exact corrected implementation for a narrowly versioned
authority update, **with the selected dependency scope and inherited limitation
below explicitly accepted**. Independent review reconciled the whole ACK-to-CI
delta with the fix: the owned-send P2 is closed, the partial-body regression is
test-only, and no new blocking issue was found. This is not a production-readiness
or universal cancellation-correctness certification.

Older reports saying "uncommitted" and the previous two-file `f6400959` proposal
remain historical checkpoints. They are not this corrected proposal. The new
candidate and this approval package are separate review artifacts created
after the source commit, so their `source_commit` identifies it exactly. An
evidence-only packaging commit does not change the selected source bytes.

## Exact local commit inventory

1. `crates/nbsr-transport/src/control_read_tests.rs`: verified partial-body
   regression plus test-fixture visibility for the owned-send tests.
2. `crates/nbsr-transport/src/quinn_adapter.rs`: benchmark-test-only body checkpoint.
3. `crates/nbsr-transport/src/owned_send.rs`: six-line revocation cleanup guard,
   precise documentation, and zero/partial-progress retained-owner regressions.
4. `docs/CI_VALIDATION_2026-10-10.md`: retained clean-tree diagnosis.
5. `docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-10.md`: partial-body evidence.
6. `docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-10.json`: its evidence manifest.
7. `docs/reviews/2026-10-10-ci-authority-decision.md`: historical authority analysis.
8. `docs/reviews/2026-10-10-owned-send-revocation-fix.md`: corrected P2 evidence.
9. `docs/reviews/2026-10-10-owned-send-revocation-fix.json`: commands and hashes.
10. `docs/reviews/2026-10-10-transport-authority-overlay.candidate.json`: preserved
    old inactive proposal, bound only to `f6400959`.

Unrelated outreach/evidence files and the operator-package design plan were not
staged. The index is empty after committing. No earlier evidence was relabeled.

## Tested-tree equivalence

Before commit, all three staged source blobs were compared with the retained
final-source SHA-256 manifest. Working bytes matched exactly; staged bytes
differed only by Git's CRLF-to-LF normalization. The commit contains those staged
blobs. The applicable checks remain 108 library passes / one existing ignored
soak, 4 application-stream and 12 stream-credit passes, 16 documentation passes,
all-target Clippy with warnings denied, default-feature check and formatting.
The library run preceded only three documentation lines; later Clippy/default/
doc checks included them. No code changed while preparing this commit, so no
Rust suite was repeated merely for a new commit identifier.

## Inactive proposal and explicit scope choice

`2026-10-10-corrected-transport-authority.candidate.json` is marked
`CANDIDATE_NOT_AUTHORITY`, outside active registries and unconsumed by production
or CI. Its SHA-256 is
`854df440f81edec41177776eaef6722d35cb7936415cf8ae88441158429f3c10`.
It pins canonical Git blob bytes, not platform-dependent checkout line endings.
The proposal document is retained with LF endings; canonicalizing its initial
CRLF serialization did not change the JSON values tested below.

The proposed minimal layer preserves all four baseline/F75/P1P2/ACK document
digests and all 110 legacy inventory entries. It replaces only the exact
`lib.rs` and `quinn_adapter.rs` entries, while proposing a **new closed five-file
supplemental implementation/build inventory**:

- `crates/nbsr-transport/src/owned_send.rs`
- `crates/nbsr-transport/src/udp_socket.rs`
- `crates/nbsr-transport/src/benchmark_bind.rs`
- `crates/nbsr-transport/Cargo.toml`
- `crates/nbsr-transport/Cargo.lock`

This scope extension is a user approval decision, not an already approved
contract. It prevents the two legacy replacement hashes from being presented
as an attestation of unbound newly introduced helper implementations. It does
not claim to freeze every module, toolchain binary, external crate's source,
build script or environment input. Unselected additions outside legacy scopes
are not discovered by this selected-file inventory. Full crate/build closure
would require a separately designed broader policy, not a silent expansion.

The proposal also binds six verification sources for evidence identity:
`src/control_read_tests.rs` and `tests/{application_stream,stream_credit_integration,
handshake,control,benchmark_connect_from_tests}.rs`, all under the crate.
These are review-evidence inputs. The proposed production acceptance gate would
check the legacy 110 artifacts plus the five explicit supplemental dependencies;
the six test-source hashes remain versioned evidence, not a silently imposed
runtime protocol rule. Confirm this distinction when approving the layer.

## Review-only checks and activation requirements

Command:

```text
python -m pytest -q -p no:cacheprovider docs/reviews/test_corrected_transport_candidate.py
```

Result: **37 passed in 0.88 s**, supervised elapsed **2.63 s**, no abort.
The checker reads 125 selected regular files directly from immutable commit
`99ac954e`: 110 legacy + four authority documents + five dependencies + six
verification sources. It checks exact positive bytes, each of 17 bound-file
mutations, missing/extra inventories, an unchanged legacy mutation, and 14
proposal/schema/parent/path/length/hash mutations. The checker is review-only,
not imported by CI or the production authority implementation.

Independent proposal review found no blocker, while confirming two limits:
this is not whole-crate closure, and entry hashes originate in the proposal.
**Activation must separately pin the explicitly approved authority document
digest.** Passing this review checker is not proof that a future production
validator is secure. That future validator still requires exact-positive and
negative regression coverage after implementation.

No active validator, historical authority document or current-source gate has
been changed. Its expected failure remains a blocker, not a waived CI result.

A fresh check of `tests/federation/test_baseline_immutability.py` on the corrected
source produced **1 failed / 3 passed in 44.80 s** (supervisor 45.97 s): the
positive still reports the exact parent-P1/P2 `lib.rs` mismatch; mutation gates
pass. An initial attempt had four setup errors because pytest could not create
its sandbox-default temporary directory. The one justified retry used a new,
previously absent task-owned `--basetemp`; both attempts remain retained. No
guard was extended and no test was skipped. The adjacent evidence JSON records
commands, outcomes and log hashes.

## Known inherited limitation

`receive_payload` and ACK wait can release retained byte accounting on revocation
yet leave RESET/STOP pending if the waiting future is dropped without repolling
while the stream owner stays alive. The underlying receive/try-lock behavior
predates the approved ACK snapshot; the corrected owned-send guard does not fix
those APIs. Accepting this source must not imply prompt transport termination
for every cancellation ordering. Keep that next test-first work separate.

## Exact next steps after explicit approval

1. Approve the source commit, proposal digest, two replacement paths, five
   supplemental gate inputs, test-evidence distinction and inherited limitation.
2. Add a separately versioned active authority document and a fail-closed
   validator with its approved digest pinned independently. Validate the whole
   unchanged ancestor chain, exact legacy inventory, closed new dependency set,
   lengths/hashes, safe unique paths, and absence of fallback. Do not refresh
   hashes inside any existing authority document.
3. Retain the main baseline positive as a current-source check using the new
   layer. Pin historical ACK unit fixtures to `94a1e4a` as P1/P2 fixtures already
   are pinned. Prove old authorities still accept only their old snapshots.
4. Run literal positive/negative regressions for changed/omitted/extra artifacts,
   each ancestor, wrong parent/digest, duplicate/unsafe paths and malformed
   metadata, including every supplemental dependency. Obtain independent review
   of the actual new validator and then a bounded clean-source federation run.
5. Commit the approved activation and evidence separately. Before publication,
   recheck remote tip and required checks/signatures. These local commits are
   unsigned; do not repeat the earlier one-time bypass. Publish only through an
   authorized compliant path, then inspect all seven hosted CI jobs. Hosted
   success, deployment readiness and larger network testing remain unproven.

No exploratory fixes or operator implementation should precede this decision.
