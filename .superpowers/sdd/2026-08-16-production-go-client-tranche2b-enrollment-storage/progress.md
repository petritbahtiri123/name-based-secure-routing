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
- ACP Git blob OID: `fb5dfe3c31cb5e42f799b19061c73c3b9708eebd`; SHA-256: `0b84be9caaa2e9b15c58fb789e7da9046fa5d64b82b6d72e7566fe327a9be42f`.
- Enrollment Git blob OID: `4ea066e125d54832d96b498fc39a8b8f2d6346ac`; SHA-256: `9d73983828f48b51a2b2e31c4637f1fe6f00b1505071faeef0be43d0e9504cd0`.

Current working branch: `codex/nbsr-v3-wp0-wp1`.
Verified local and remote branch SHA at recovery: `8d9b2a4a22248353a278810e560b5a39fbe4ce8f`.
Working-branch history from frozen anchor: `420b2685a4f11157bedf87ce5bb80908496666fe` (3R-B tip) plus this progress repair chain.

NEXT_TASK = Tranche 2B transport + enrollment control-plane runtime (HTTP/TLS provider/enrollment wire implementation).

## Spark 5.3 audit repair

- Audit starting SHA: `891ea07218977630aa80a073b1625db4cfcd515b`.
- Storage repair commit: `aa734d755453ca2a7f18623e68102e4c0e4cd805`.
- Validated findings repaired: production path/lock bypass, accidental replace-existing install, replaceable/non-idempotent lock lifecycle, unbounded reads/orphans, and incomplete ACL policy.
- Added genuine RED regressions for OS-lock bypass, no-overwrite installation, lock replacement, crash-orphan recovery, missing SYSTEM/broad writers, corruption/tamper variants, and bounded parsing.
- Fresh GREEN evidence: authority and identity tests; authority and identity race tests; Windows fixture gates with zero skips; real subprocess writer/lock/crash tests; 5-second parser fuzz (205398 executions); Go vet; Linux compile-only; gofmt; `git diff --check`.
- Independent spec, security, and scoped Windows/storage re-reviews: no remaining Critical, Important, or Minor code findings.
- Formal Codex Security diff scan `09bc15e3-94f1-41d2-bc13-52b8b18fd365`: five original findings (four High, one Medium), all remediated by `aa734d755453ca2a7f18623e68102e4c0e4cd805`.
- Frozen protocol sources remained byte-identical at the Git blob OIDs and SHA-256 values above.
- Remote working branch intentionally remains `891ea07218977630aa80a073b1625db4cfcd515b`; audit commits were not pushed.
- Acceptance blocker: this host has no provisioned dedicated NBSR Windows service identity/service profile. DPAPI same-token subprocess restart behavior is covered, but the required SCM stop/start proof under the selected service identity must be executed as an external deployment gate. No fallback keystore or machine-scope DPAPI was introduced.
- Task 3R-C remains NOT STARTED.
