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
- The former service-identity acceptance blocker was closed by the elevated SCM gate recorded below. No fallback keystore or machine-scope DPAPI was introduced.
- Task 3R-C remains NOT STARTED.

## Windows service identity decision and gate harness

- Approved production service: `NBSRClient`, own-process SCM service.
- Approved account model: Windows Virtual Service Account `NT SERVICE\NBSRClient`, with no password.
- Installer provisioning owns service creation plus `%ProgramData%\NBSR\GoClient\Enrollment` creation and its SYSTEM/service-identity ACL; enrollment runtime does not provision or weaken the boundary.
- DPAPI remains user-scoped under the virtual service account; machine-scope, plaintext, and alternate-keystore fallbacks remain forbidden.
- Test-only SCM gate harness commit: `cd3a33bd41eaf1eec4022f47d711e35ec8b4a0a8`.
- Elevated SCM gate: COMPLETE at local HEAD `ebc06891234a184c709e7ccafac451c14754db50`.
- Real service evidence: own-process `NBSRClient` ran as `NT SERVICE\NBSRClient`, SID `S-1-5-80-791066319-2577492049-1163703186-265042808-2809310517`, with profile `C:\WINDOWS\ServiceProfiles\NBSRClient`.
- Restart sequence: STORE PID 13516, LOAD PID 6720, LOAD PID 18108; all three operations succeeded, recovered the exact identity, and returned `Ready=false`.
- User-scoped DPAPI evidence: protected integrity-key SHA-256 remained `6116AA561CA6435F156763D3A3CE4328BF4E49795184D55045B0C942D148F59B`; authenticated-state SHA-256 remained `0BF2BCC8F87052205E616B1E231873CEE0549BD8A79362C0E5F5D239AE5E8B4A` across both fresh-process loads.
- Fresh elevated regressions: authority and identity suites passed normally and with `-race` (12.104s, 0.549s, 17.045s, 1.714s respectively).
- Host safety: `NETWORK_CONFIGURATION_CHANGED=NO`; cleanup removed the temporary service and exact test-owned `C:\ProgramData\NBSR` tree. No reboot/logoff was performed.
- Corrective commits discovered by the real gate: `aefa5e9` (SCM argument tokenization), `1036386` (preserve service ownership), `994f866` (deterministic elevated fixture owner), and `ebc0689` (validate Windows `TokenOwner`).
- Residual evidence gap: the optional negative different-identity DPAPI test was not executed. It does not invalidate the positive dedicated-service restart-stability proof; cross-identity access remains denied by the trusted-root ACL design and no broader claim is added.
- Task 3R-C remains NOT STARTED.
