# Tranche 2B implementation status (recovered ledger)

- Starting verified frozen baseline: `1938154d498b32d81a3564319969430644e8a688` (`main`).
- Current local and remote working-branch SHA: `420b2685a4f11157bedf87ce5bb80908496666fe`.
- No dedicated Tranche 2B plan file was found in-repo; this status is reconstructed from
  - protocol freezes (`docs/protocol/status.md`, `docs/protocol/tranche2b-...`)
  - authoritative commit history from the tranche baseline
  - implementation evidence in `client/nbsr-go-client/internal/authority`.

## Tranche 2B task map (recovered)

| Task | Scope | Commit | State |
| --- | --- | --- | --- |
| 3R-A | Windows trusted enrollment storage root/path/ACL/reparse protection + fixed-path lock target + real cross-process exclusive LockFileEx lock acquisition | `10be800200b68f568d3c373d0f9d69a501553092` | COMPLETE |
| 3R-B | Windows secure enrollment-state persistence + DPAPI-backed integrity key material + bounded state installation + envelope verification, load, and corruption handling | `420b2685a4f11157bedf87ce5bb80908496666fe` | COMPLETE |
| 3R-C | transport/enrollment ACP runtime implementation | not started in recovered record | NOT STARTED |

## 3R-A completion evidence

- Files changed:
  - `client/nbsr-go-client/go.mod`
  - `client/nbsr-go-client/go.sum`
  - `client/nbsr-go-client/internal/authority/errors.go`
  - `client/nbsr-go-client/internal/authority/storage_common.go`
  - `client/nbsr-go-client/internal/authority/storage_unsupported.go`
  - `client/nbsr-go-client/internal/authority/storage_windows.go`
  - `client/nbsr-go-client/internal/authority/storage_windows_test.go`
- Focused verification performed:
  - `go test ./internal/authority -count=1`
  - `go test ./internal/identity -count=1`
  - `go test ./internal/authority -run 'Test.*(EnrollmentState|Storage|Lock|DPAPI|Windows).*' -count=1`
  - `go vet ./internal/authority ./internal/identity`
  - `git diff --check`
- Review artifacts found in this tree for 3R-A specifically: none dedicated.

## 3R-B completion evidence

- Files changed:
  - `client/nbsr-go-client/internal/authority/enrollment_state.go`
  - `client/nbsr-go-client/internal/authority/enrollment_state_test.go`
  - `client/nbsr-go-client/internal/authority/enrollment_state_unsupported.go`
  - `client/nbsr-go-client/internal/authority/enrollment_state_windows.go`
  - `client/nbsr-go-client/internal/authority/storage_common.go`
- Focused verification performed:
  - `go test ./internal/authority -count=1`
  - `go test ./internal/identity -count=1`
  - `go test ./internal/authority -run 'Test.*(EnrollmentState|Storage|Lock|DPAPI|Windows).*' -count=1`
  - `go vet ./internal/authority ./internal/identity`
  - `git diff --check`
- Review artifacts found in this tree for 3R-B specifically: none dedicated.

## Frozen-spec hash verification (pre/post 3R-B)

- `docs/protocol/tranche2b-acp-wire-semantics-draft.md`:
  - pre/post SHA256 `fb5dfe3c31cb5e42f799b19061c73c3b9708eebd`
- `docs/protocol/tranche2b-enrollment-wire-semantics.md`:
  - pre/post SHA256 `4ea066e125d54832d96b498fc39a8b8f2d6346ac`

## Protected refs and lineage

- Main/reference anchor (`main` and `origin/main`): `1938154d498b32d81a3564319969430644e8a688`.
- Working branch (`codex/nbsr-v3-wp0-wp1`) and remote branch are both at `420b2685a4f11157bedf87ce5bb80908496666fe`.

## NEXT_TASK (from current available plan artifacts)

`Tranche 2B transport + enrollment control-plane runtime` (HTTP/TLS provider/enrollment wire integration and runtime orchestration), which is not yet implemented in this branch.
