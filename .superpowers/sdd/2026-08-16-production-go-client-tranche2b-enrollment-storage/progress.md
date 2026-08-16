# SDD ledger — reconstruction: Tranche 2B secure enrollment-state persistence

Starting SHA (Tranche 2B frozen/anchored main): `1938154d498b32d81a3564319969430644e8a688`.
Working branch: `codex/nbsr-v3-wp0-wp1`.

Task 3R-A: COMPLETE (`10be800200b68f568d3c373d0f9d69a501553092`)
Task 3R-B: COMPLETE (`420b2685a4f11157bedf87ce5bb80908496666fe`)

- 3R-A scope completed:
  - trusted Windows production root derivation to `%ProgramData%\NBSR\GoClient\Enrollment\`
  - fixed lock path + LockFileEx acquisition lifecycle
  - path reparse/Junction/ACL enforcement
  - typed storage-path and storage-busy errors
- 3R-B scope completed:
  - Windows enrollment envelope format and on-disk authenticated state
  - DPAPI-based (or equivalent OS-kept) enrollment integrity key material lifecycle
  - bounded atomic write semantics with crash-orphan protections
  - envelope signature/tamper validation + deterministic state rejection paths

Evidence run for repaired ledger:
- `go test ./internal/authority -count=1`
- `go test ./internal/identity -count=1`
- `go test ./internal/authority -run 'Test.*(EnrollmentState|Storage|Lock|DPAPI|Windows).*' -count=1`
- `go vet ./internal/authority ./internal/identity`
- `git diff --check`
- local and remote branch SHA equality checked for recovery precondition and post-commit

Tranche 2B protocol freeze hash checks (unchanged):
- `fb5dfe3c31cb5e42f799b19061c73c3b9708eebd` (`docs/protocol/tranche2b-acp-wire-semantics-draft.md`)
- `4ea066e125d54832d96b498fc39a8b8f2d6346ac` (`docs/protocol/tranche2b-enrollment-wire-semantics.md`)

NEXT_TASK = Tranche 2B transport + enrollment control-plane runtime (HTTP/TLS provider/enrollment wire implementation).
