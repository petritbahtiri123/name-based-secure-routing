# Task 6 CloseGeneration Ownership Supplement

**Status:** HUMAN APPROVED on 2026-08-14

**Immutable implementation-plan baseline:** `10f6b72382d95a1ef4967479145eda17f497b9d0`

This supplement resolves one file-ownership omission in Task 6 of
`docs/superpowers/plans/2026-08-14-production-go-client-tranche1-bounded-core-state.md`.
It does not modify or replace that immutable plan baseline.

## Authorized correction

Task 6 additionally authorizes modifying:

- `client/nbsr-go-client/internal/corestate/handle.go`
- `client/nbsr-go-client/internal/corestate/handle_test.go`

The only authorized change in that file is to remove the existing public
`CloseGeneration` method so that its implementation can move to Task 6's
`teardown.go`. `handle.go` retains `OpenGeneration` and all generation-scoped
handle allocator state and methods without semantic change.

`teardown.go` owns the coordinated `CloseGeneration` implementation required by
Task 6: generation closure/destruction under the Store lock and one aggregate
`EventGenerationClosed` callback after unlock.

The only authorized `handle_test.go` change is to replace the superseded Task 2
expectation that a nonempty generation close is rejected. Its replacement must
assert the approved Task 6 coordinated-close behavior, allocator deletion, and
rejection of stale reopen/use; it must not weaken unrelated allocator coverage.

## Unchanged boundaries

- The public method signature and frozen event set remain unchanged.
- No wrapper, duplicate method, new public interface, or allocator behavior is
  introduced.
- Every other Task 6 file, behavior, test, command, and acceptance condition
  remains exactly as specified by the approved plan.
- Task 7 and later tasks remain excluded.
- Main and all protected interop, Rust, protocol, vector, and evidence paths
  remain frozen.
- This supplement and Task 6 are local-only unless a later instruction
  explicitly authorizes a push.
