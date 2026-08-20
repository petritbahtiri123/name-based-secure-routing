# Tranche 2B implementation status (recovered ledger)

- Starting verified frozen baseline: `1938154d498b32d81a3564319969430644e8a688` (`main`).
- Audit starting local and remote working-branch SHA: `891ea07218977630aa80a073b1625db4cfcd515b`.
- Current local audit repair commit: `aa734d755453ca2a7f18623e68102e4c0e4cd805`; remote remains unchanged because this audit forbids push.
- No dedicated Tranche 2B plan file was found in-repo; this status is reconstructed from
  - protocol freezes (`docs/protocol/status.md`, `docs/protocol/tranche2b-...`)
  - authoritative commit history from the tranche baseline
  - implementation evidence in `client/nbsr-go-client/internal/authority`.

## Tranche 2B task map (recovered)

| Task | Scope | Commit | State |
| --- | --- | --- | --- |
| 3R-A | Windows trusted enrollment storage root/path/ACL/reparse protection + fixed-path lock target + real cross-process exclusive LockFileEx lock acquisition | `10be800200b68f568d3c373d0f9d69a501553092` | COMPLETE |
| 3R-B | Windows secure enrollment-state persistence + DPAPI-backed integrity key material + bounded state installation + envelope verification, load, and corruption handling | `420b2685a4f11157bedf87ce5bb80908496666fe` | COMPLETE |
| 3R-C | transport/enrollment ACP runtime implementation | Task 1: this commit | IN PROGRESS — Task 1 complete; Tasks 2–4 not started |

## 3R-C Task 1 — frozen ACP wire codec

- Status: COMPLETE.
- Starting SHA: `1dad39dda6083202bf210c86ce192eb48dbea089`.
- Final commit: this Task 1 commit (`feat(go-client): implement frozen ACP wire codec`); exact SHA is recorded by Git history and the task report because a commit cannot contain its own SHA.
- Files changed: ACP wire codec/tests, static ACP-result issuer resolver, authority package comment, this recovery status, and the 3R-C plan.
- Focused verification: ACP focused tests PASS; complete authority package PASS; bounded `FuzzParseVerifiedACPResult` PASS; `go vet` and whitespace gates PASS.
- Reviewer verdict: Codex Security diff scan `8eebbc2b-7485-4a50-8d2e-12e824117644` found no reportable security finding. Two correctness candidates (transport text validation and signature length) were reproduced RED, fixed, and passed the single scoped re-review.
- Frozen protocol SHA-256: ACP `e795abf0a078c2dfe9bdf56d705fde67a1355bd28eb1cd35b5dc6efb0a5dad24`; Enrollment `9d73983828f48b51a2b2e31c4637f1fe6f00b1505071faeef0be43d0e9504cd0`.
- Remote SHA: must equal this Task 1 commit after the authorized normal push; exact SHA is recorded in the task report.
- Next task: 3R-C Task 2 — Go HTTP/2 ACP and Enrollment clients. Tranche 3 has not started.

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

## Frozen-spec hash verification and ACP reconciliation


- `docs/protocol/tranche2b-acp-wire-semantics.md`:
  - Git blob OID `2c49f29017e1b7618a7af563332274c28afeef45`
  - SHA-256 `e795abf0a078c2dfe9bdf56d705fde67a1355bd28eb1cd35b5dc6efb0a5dad24`
  - Reconciliation note: the prior OID `fb5dfe3c31cb5e42f799b19061c73c3b9708eebd` and SHA-256 `0b84be9caaa2e9b15c58fb789e7da9046fa5d64b82b6d72e7566fe327a9be42f` identified the old pre-decision draft, not the later approved freeze; that evidence was stale and is superseded by this single final authority.

- `docs/protocol/tranche2b-enrollment-wire-semantics.md`:
  - Git blob OID `4ea066e125d54832d96b498fc39a8b8f2d6346ac`
  - SHA-256 `9d73983828f48b51a2b2e31c4637f1fe6f00b1505071faeef0be43d0e9504cd0`

## Protected refs and lineage

- Main/reference anchor (`main` and `origin/main`): `1938154d498b32d81a3564319969430644e8a688`.
- Local working branch contains audit repair commit `aa734d755453ca2a7f18623e68102e4c0e4cd805`; remote working branch intentionally remains `891ea07218977630aa80a073b1625db4cfcd515b`.

## Spark 5.3 audit status

- Formal diff scan: `09bc15e3-94f1-41d2-bc13-52b8b18fd365`.
- Original validated findings: four High and one Medium across path/lock integration, no-overwrite installation, lock lifecycle, bounded storage, and ACL enforcement.
- Repair commit: `aa734d755453ca2a7f18623e68102e4c0e4cd805`.
- Fresh tests passed: complete authority/identity; both race suites; real subprocess contention, writer race, abnormal lock teardown, and crashes before/after installation; required reparse/ACL fixtures with zero skips; parser fuzz; vet; Linux compile-only; formatting and whitespace checks.
- Independent spec, security, and Windows/storage scoped re-reviews found no remaining Critical, Important, or Minor code issue.
- Dedicated-service-account DPAPI restart stability is verified by the elevated SCM gate at local HEAD `ebc06891234a184c709e7ccafac451c14754db50`: STORE plus two fresh-process LOAD operations succeeded under `NT SERVICE\NBSRClient`, used three distinct PIDs, recovered the exact identity with `Ready=false`, and retained stable protected-key and authenticated-state hashes.
- 3R-C remains NOT STARTED.

### Approved Windows service gate profile

- Service: `NBSRClient` as an own-process SCM service.
- Identity: Windows Virtual Service Account `NT SERVICE\NBSRClient` with no password.
- Profile/key model: user-scoped DPAPI under that virtual service identity; no machine-scope, plaintext, or alternate-keystore fallback.
- Provisioning boundary: the installer owns service creation and the trusted ProgramData directory/ACL.
- Test-only harness: `cd3a33bd41eaf1eec4022f47d711e35ec8b4a0a8`.
- Status: COMPLETE. Elevated SCM STORE → stop → LOAD → stop → LOAD ran successfully under SID `S-1-5-80-791066319-2577492049-1163703186-265042808-2809310517` with service profile `C:\WINDOWS\ServiceProfiles\NBSRClient`. Authority and identity suites passed normally and with `-race`; `NETWORK_CONFIGURATION_CHANGED=NO`; exact test service/tree cleanup succeeded. The different-identity negative test was not executed and is retained as a bounded residual evidence gap. 3R-C remains NOT STARTED.

## NEXT_TASK (from current available plan artifacts)

`Tranche 2B transport + enrollment control-plane runtime` (HTTP/TLS provider/enrollment wire integration and runtime orchestration), which is not yet implemented in this branch.
