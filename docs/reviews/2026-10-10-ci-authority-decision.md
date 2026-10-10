# CI authority reconciliation decision — 2026-10-10

**Status: decision required; no authority or validator changed.**
The private-origin connector implementation remains deferred. CI implementation
HEAD remains `f6400959e93f32f3eec32372c60773c115344583`; no commit or push was
made for this investigation.

## Exact failure and contract

The clean-tree failure is
`tests/federation/test_baseline_immutability.py::test_core_v02_baseline_accepts_exact_110_artifact_inventory`.
Its fixture copies current candidate artifacts; it calls
`assert_demo_ack_core_overlay`, which reads actual bytes and raises at
`nbsr/federation/profile.py:589` for:

```text
modified Core v0.2 parent P1/P2 overlay replacement: crates/nbsr-transport/src/lib.rs
```

The validator is enforcing an exact-source authority chain, not merely checking
whether the wire protocol appears compatible. Frozen baseline, F75, P1/P2 and
ACK document digests, closed replacement sets, lengths, hashes and inventory
are mandatory. There is no wildcard allowance for later implementation changes.

The intended split is explicit:

- `docs/superpowers/plans/2026-08-13-p1-p2-test-reconciliation.md:281` says to
  update the **current-HEAD positive assertion**, while retaining historical
  F75 fixture tests. Its authority checkpoint requires explicit approval of
  exact paths, lengths, hashes, parent binding and activation semantics.
- `docs/reviews/2026-08-13-p1-p2-test-failure-classification.md` previously
  classified later P1/P2 bytes as an authority conflict and prepared an inactive
  candidate instead of rewriting the older authority.
- `aa48b24f277a7c388e6916c45c983ee2c15fc730` activated the P1/P2 overlay.
- `94a1e4a2da528534ce9e2c62bc9d7a6335bd81ab` added the ACK overlay, pinned
  P1/P2-specific historical fixtures to `aa48b24f`, and deliberately made the
  main baseline fixture use current candidate bytes plus the ACK validator.

Therefore changing the main baseline fixture to a historical commit would
remove its current-source check. Historical ACK-specific fixtures can later be
separated like P1/P2 fixtures, but that cannot replace the current-tree gate.

## Source history and complete mismatch set

Both active overlay documents remain byte-identical to their creation commits.
Comparing all 110 artifacts against baseline + F75 + P1/P2 + ACK on the clean
`f6400959` tree finds exactly these two mismatches:

| Path | Approved bytes / SHA-256 | Current committed bytes / SHA-256 |
| --- | --- | --- |
| `crates/nbsr-transport/src/lib.rs` | 6634 / `c3dd27a6b11a53e53f1fcb7cce1b0b3f52c4c616c9c70f07d281d435022c6d3e` | 6817 / `3db5a0a615e12d4d67ed0380f07e9ad9778bde98a8879817992a0df000f99e43` |
| `crates/nbsr-transport/src/quinn_adapter.rs` | 69638 / `d0adae2f00ecab195ebd156a2b5811929e65687059245c931e11874f7e7f2acc` | 95337 / `503ebf04ad6078be8e17df48a26c77cd5ac57e1de64b8059f6a8affb55c2bd85` |

`lib.rs` changed in three commits after the approved snapshot:

1. `2ee765e70ae8b80471f3867771868ecaf246f638`: add the `udp_socket` module
   for bounded Windows UDP receive buffering; this is the first byte divergence.
2. `3c9f966b8c8326cba1af0023aa486ef5f92ba4e6`: benchmark-feature-gated
   `benchmark_bind` module and `benchmark_connect_from` export.
3. `bea16625ab78d2a5404ce02d0c0b5d82e9e6929d`: export `OwnedSendOperation`.

The complete subsequent `quinn_adapter.rs` commit sequence is:

| Commit | Recorded change |
| --- | --- |
| `2ee765e7` | Windows listener UDP receive buffer bound |
| `36e8970b` | Bounded benchmark close-category diagnostics |
| `3c9f966b` | Explicit native IPv4 benchmark placement |
| `6c75e4f1` | Connection-close isolation and evidence verification |
| `0cf752d7` | Bounded live lifecycle diagnostics/archive evidence |
| `1ca9fd8a` | Control-accept cancellation ownership documentation/tests |
| `40b7f830` | Retained control reads and revoked ACK waits |
| `bcd5f5df` | Retained partial application payloads across cancellation |
| `bea16625` | Resumable owned sends and interrupted borrowed-send guard |
| `e245bc35` | Reset interrupted echo responses |
| `8e548588` | Revoked benchmark-frame interruption and cancellation docs |

The two-file diff from the ACK snapshot is 702 insertions and 108 deletions.
These are substantive recorded implementation changes, not a newline-only
problem. This investigation identifies their provenance; it does **not** certify
all changes as semantically equivalent or infer protocol approval from commits.
The byte mismatch alone likewise does not establish an unauthorized wire change
or justify reverting the later fixes.

## Diagnostic regression evidence

The previous clean current-tree positive remains **1 failed in 9.66 s**; its
failure is retained in `docs/CI_VALIDATION_2026-10-10.md`.

A temporary diagnostic test module reconstructs exactly the 110 historical
artifacts and four authority documents from `94a1e4a`, without editing the
repository, then substitutes each current file independently. Command:

```text
python -m pytest -v -p no:cacheprovider --durations=10 <task-temp>/test_nbsr_ci_authority_history.py tests/federation/test_p1p2_core_overlay.py::test_exact_approved_p1p2_overlay_passes
```

Result: **4 passed in 10.97 s**, supervisor elapsed **12.04 s**, exit 0,
no timeout/resource abort. Cases:

1. Historical ACK snapshot passes the unchanged validator.
2. Substituting clean `f6400959` `lib.rs` produces exactly the parent-P1/P2
   replacement rejection.
3. Substituting clean `f6400959` `quinn_adapter.rs` produces exactly the ACK
   replacement rejection.
4. Existing historical P1/P2 positive test passes unchanged.

Passing negative diagnostics does not convert the current-tree failure to PASS.
Logs/result JSON are retained in the local `nbsr-ci-clean-evidence` directory
under label `authority-history`. No compilation, dependency fetch or service
startup was needed. Independent read-only review confirmed the current-tree
contract and rejected replacing it with a historical-only gate.

## Smallest justified path and exact decision

An inactive proposal is saved beside this report as
`2026-10-10-transport-authority-overlay.candidate.json`, explicitly marked
`CANDIDATE_NOT_AUTHORITY`. It is not in the active registry and is not consumed
by validation. It contains only the two exact committed replacements above,
bound to the unchanged ACK parent digest
`99fe7153f251c4d68d836596bb532cf7bb32eb55f41d6c69b6fc04b281167801` and the
original baseline digest. It excludes the four uncommitted transport/report
files, including the additional body-pending test instrumentation in dirty
`quinn_adapter.rs`. Approval of this snapshot would not cover those later bytes.

**Decision needed:** after reviewing the listed implementation delta, should
the exact two-file `f6400959` snapshot be recognized by a new additive authority
layer with closed, fail-closed semantics, while preserving all historical
authority documents and the current-tree gate? Alternatively, select specific
implementation changes for separately scoped correction; do not revert them
merely to satisfy a historical hash.

If explicit authority approval is given, the minimal follow-up is:

- Add a separately versioned active overlay bound to the approved candidate;
  never refresh hashes inside the existing baseline/F75/P1/P2/ACK documents.
- Add a closed validator that validates the entire ancestor-document chain,
  exact two-file set, current inventory and every unaffected artifact. Existing
  historical validators retain their behavior.
- Pin ACK historical unit fixtures to their accepted snapshot, as P1/P2 already
  does; retain the main baseline positive as current-candidate validation using
  the new layer. Do not remove it from CI.
- Require literal RED/GREEN tests for the approved current snapshot, each
  replacement mutation, ancestor-document mutation, wrong parent, omitted or
  extra replacement, duplicate/unsafe path, malformed length/hash and missing
  or unlisted artifact. Also prove old snapshot validation and rejection of
  current substitutions by old validators remain unchanged.
- Rerun those focused checks in bounded groups, then the relevant clean
  federation groups; obtain independent correctness/security review before a
  local authority commit. Publication remains separately authorized.

Activating this would change which source bytes the authority chain accepts.
That is the evidence-trust boundary the user instructed us to stop at. No
active overlay, protocol file, test selection or validator was changed.

Final independent read-only review of this report and the inactive candidate
found no blocker: exact committed-byte scope, parent binding, historical/current
test distinction and exclusion of dirty follow-up bytes are explicit. No tests
were rerun by the reviewer. Final cleanup found zero owned diagnostic processes,
12.18 GiB free disk and 6.23 GiB free RAM. The four original dirty transport/report
file hashes remain unchanged; the index is empty and `git diff --check` passed.
