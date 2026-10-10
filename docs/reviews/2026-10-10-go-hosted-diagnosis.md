# Targeted Go hosted-failure diagnosis

Base/published SHA: `2251ea9529fcef54f4e40d3fe5ccc27597126d4e`.
Hosted run [38054824820](https://github.com/petritbahtiri123/name-based-secure-routing/actions/runs/38054824820) has five passing jobs and two failing Go jobs. This follow-up is local and uncommitted. No push, bypass, ACK implementation, production security change or authority activation occurred.

## Federation: exact authority decision

The independent Go verifier authenticates the raw manifest before parsing semantics, then authenticates its artifact inventory and upstream authority bytes. Its baseline is `0849b986d065105441e116dce15294250a323926`; the package was published at `af75e17cdde36ddbd02f5236f2ed16503f3f7c1e`, and the independent verifier/pin was introduced at `7af982239dc8fbc67ae142037f192458c797f4d4`.

`a6ac60c21c6a7aeca659e0cfa9ba0aa986c641b7` assigned ACP_RESULT_SIGNING=15. `af15649678540d57770fd08ad09934a43c1f9241` assigned ENROLLMENT_RESULT_SIGNING=16. Compared with the verifier baseline, these are the only added entries in `/registries/key_purposes`; `/reserved_ranges/key_purposes/0/0` changes from 15 to 17. The registry grows from 78,624 to 78,881 bytes. This changes which key-purpose numbers are valid, so it is an authority-semantic change even though the existing vector payloads were not changed.

`e15b2511bc9cc0c0917b74bdd09e354422c805d6` subsequently updated the Python generator's registry lock and regenerated the lock/manifest without changing `package_version=federation-v0.1-development-v1` or the accepted baseline commit. Exact changed fields:

| File/field | Original | Current |
| --- | --- | --- |
| authority-locks `/authorities/2/length` | 78624 | 78881 |
| authority-locks `/authorities/2/sha256` | `29311cb8e952e328eef7c69fb4776a85504ff4af5edf7c55faad53194d60dc7e` | `ed880f236a2b4b5e11e281e58c540534e1cd27f7c752d3990291cf1be55c80d0` |
| manifest `/artifacts/1/sha256` | `a204152ab0f402342e2030c76d4bd77669781ec78b7fe8c5783afb8e72ba4351` | `e859993d1fa8cb627208191e829d3b078a3fa6759b19d241d739e3346ed65bca` |
| raw manifest SHA-256 | `1ff9591b925e926e757bb57ab8f3cd1620b6ff9d41149df92ad5672ff810ab35` | `2ab8286179221e06c2c24843f6a1015f24247c6a1de9d8cb81f20e5fe88aa497` |

No other manifest or lock field differs. JSON includes exact raw-Git hashes and structural differences. The local focused TestCheckedInPackage reproduces the hosted rejection; it is platform-independent and occurs before schema execution.

Earlier evidence did not establish this gate: the e15b2511 closure lists Go client-module tests, not the separate federation verifier module. Python test_vectors compares package bytes against the simultaneously updated generator and locks, so its success does not assert the Go trust anchor. The earlier 9ac925df hosted Go Linux profile stopped at the demo test before reaching module 3. The failure was also already recorded in FEDERATION_PACKAGE_AUTHORITY_BLOCK.md; it was previously detected, not a new regression.

**Decision required:** preserve the original immutable development-v1 package and its original upstream registry snapshot, and introduce the expanded authority as a separately named/versioned package with explicit accepted baseline and reviewed independent-verifier support; or explicitly approve a replacement/compatibility policy that changes what the existing package identity means. The first option preserves historical verification and is recommended. Merely changing the Go digest would implicitly trust new authority semantics under the old identity. No such change is active. Acceptance should verify both supported package identities, reject unapproved hashes and test purposes 15/16 according to each version's rules.

## Windows: proven local boundary, hosted confirmation outstanding

The exact locally reproduced cause is `validateIdempotencyStorePath`'s parent-versus-EvalSymlinks comparison. A Windows 8.3 short name expands to a different string, yielding ErrStoragePathRejected (24) before file creation/locking. The reproduction uses one test-owned directory, captures TEMP/TMP, supplied/resolved paths and owner/DACL in the retained local log, and demonstrates OS create/LockFileEx succeeds through the same short path. Construction succeeds through the canonical spelling without ACL changes. Thus the local failure is fixture construction, not missing Windows storage support or lack of file/lock permissions.

Under test-scoped short TMP/TEMP, the original fixture failed with error 24. The correction resolves only a new t.TempDir root before composing storage paths in the idempotency and runtime tests. It does not rewrite caller paths, change production validation, change host environment permanently or grant permissions. The regression still requires production to reject the short alias. Fixture logging and constructor failure diagnostics retain supplied/resolved path evidence.

Hosted logs contain only generic error 24 and no failing path or Win32 error. This local reproduction therefore does **not** prove the hosted runner used short temp paths, identify its token/DACL, or exclude another hosted path/lock cause. An authorized hosted run must confirm the fixture correction; if failure remains, use its new path diagnostics before any further fix. No claim of a green hosted baseline is made.

## Validation and cleanup

All Go runs used the provisioned cache, offline module policy, two build/test workers, 70-second Go timeout and the existing 95-second supervisor deadline. Exact commands, source hashes and log hashes are in the adjacent JSON.

| Check | Result | Supervisor duration |
| --- | --- | --- |
| Short-path rejection versus OS lock/canonical constructor | PASS | 4.82 s |
| Short TMP/TEMP fixture before correction | expected FAIL, error 24 | 4.82 s |
| Same regression after correction | PASS, including subtest | 5.03 s |
| Full affected authority package | PASS (Go reports 15.527 s) | 17.28 s |
| Federation TestCheckedInPackage | retained FAIL, untrusted manifest digest | 1.61 s |

Independent review by full_delta_review found no blocker and confirmed ownership, cleanup and unchanged negative checks; reviewer ran no tests. No native Linux local run occurred. Initial exploratory sandbox temp cleanup returned Access denied; subsequent exact-path check found the directory absent. All five supervised children were reaped, no containers were started, and unrelated files were preserved. Root guidance and CI documentation record the fixture boundary. No additional expensive checks are warranted before hosted evidence or the authority decision.
