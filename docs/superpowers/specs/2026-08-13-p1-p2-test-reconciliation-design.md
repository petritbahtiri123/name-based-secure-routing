# P1/P2 Test Reconciliation Design

## Goal

Restore a trustworthy green repository gate at `e62af52` before publishing
`codex/nbsr-v3-wp0-wp1`, without weakening frozen Core, federation, replay, or
stream-admission authorities. Preserve the accepted P1F replay hard cap and P2D
V1 stream-credit behavior exactly.

## Starting evidence

- The target branch fast-forwards cleanly from remote `4e25ee0` to P2D tip
  `e62af52`; `main` remains `1938154`.
- Fresh Rust all-target validation reports 180 passed, 0 failed, 1 ignored.
- Fresh full pytest reports 1,795 passed, 38 failed, 1 skipped.
- Failures cluster around byte-exact Core/federation locks, generated vectors,
  later P1/P2 edits to locked transport files, and one Windows Application
  Control failure (`os error 4551`).
- The machine-wide Git configuration enables `core.autocrlf=true`.

## Safety invariants

1. Do not edit, regenerate, or relabel a frozen authority merely to make a test
   pass. Any authority change requires evidence that the current authority
   explicitly permits the later P1/P2 surface.
2. Do not restore rejected P2C production behavior or weaken P1F replay
   semantics, V1 downgrade rejection, payload-before-ACCEPT quarantine, or
   actual Quinn stream-handle validation.
3. Treat committed bytes as authoritative. Checkout line-ending conversion
   must not silently change the bytes that lock and vector tests inspect.
4. Keep Windows Application Control classification separate from semantic test
   correctness. A policy-blocked executable is not a passing interoperability
   test and must remain visibly INCONCLUSIVE or blocked unless it runs.
5. Do not modify or push `main`. Publish only
   `codex/nbsr-v3-wp0-wp1` with an explicit refspec after all mandatory gates.

## Reconciliation approach

### 1. Classify each failure before editing

Reproduce one representative test from each failure cluster and compare its
input bytes with the corresponding Git blob. Build a closed failure inventory:

- checkout byte-conversion failures;
- legitimate later-source changes rejected by a historical lock/overlay;
- generated-vector drift caused by checkout bytes;
- environment-only execution failures;
- any independent functional regression.

### 2. Fix checkout-byte reproducibility at the boundary

Add the narrowest repository-owned text-attribute rules needed for byte-locked
authorities and generated fixtures. Prove with a disposable fresh checkout that
the working-tree bytes match the committed blobs under the user's global
`core.autocrlf=true`. Do not rewrite authority content as part of this step.

### 3. Reconcile historical locks additively

Where P1/P2 legitimately extends a file covered by an older WP8 baseline,
preserve the original lock unchanged and introduce or extend an additive,
versioned overlay only if the authority model already supports it. The overlay
must enumerate exact permitted paths and digests; every non-enumerated change,
path alias, symlink, extra field, and baseline mutation must still fail closed.
If existing authority rules do not permit such an overlay, stop and report the
conflict instead of changing the lock.

### 4. RED-first implementation

For each confirmed root cause, first add or select a focused regression that
fails for that exact reason. Record the RED result, implement one minimal fix,
then record GREEN before moving to the next cluster. Existing failing tests may
serve as RED only when their expected invariant remains authoritative.

### 5. Verification and publication

Run focused tests after each fix, then:

- full pytest;
- Rust default and all-target `benchmark-harness` tests using an external
  writable `CARGO_TARGET_DIR`;
- Rustfmt, strict Clippy, Ruff check/format, vector and authority verification,
  `git diff --check`, and LFS object checks;
- clean-tree, branch ancestry, remote/local SHA, and unchanged-main checks.

Only a fully passing mandatory suite authorizes an explicit push of local
`codex/nbsr-v3-wp0-wp1` to the same remote branch. No PR is created.

## Expected commits

Use focused commits with exact path staging:

1. tests: add failure classification and checkout-byte RED coverage;
2. fix: make byte-locked inputs checkout-stable;
3. tests/fix: reconcile only authority-permitted additive overlays, if needed;
4. docs: record fresh verification and publication evidence.

Do not use broad staging, history rewrites, merges, or rebases.

## Stop conditions

Stop before publication if any frozen authority would need replacement rather
than an explicitly permitted additive overlay, any security behavior regresses,
full mandatory validation remains red, LFS hydration is incomplete, remote
target moved unexpectedly, or `main` differs from `1938154`.
