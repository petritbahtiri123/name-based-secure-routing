# Native request-body/evidence binding, 2026-11-14

## Bounded design

Reuse `nbsr/connector_registration_authority_offline.py` policy/scope/inventory
checks and existing native codec, KAR and genesis verification. This is test-only
composition, not a new provider. No session, operation counter, receipt provenance,
authenticated currentness, governance closure, admission expiry or READY claim.

The configured policy and actual request body use the existing strict REQUEST
validator. Pin fields2,3,4,5,6,7,8,12. Configured scope must bind service/operator/
destination and registration-only action, no subdelegation/depth. Actual peer key
must match the request digest and purpose14 KAR subject. Derive delegatee through
the authenticated chain path. Match all three signed payload digests to both the
request and explicit configured fixture inventory. Three means complete only for
this KAR/NOR/direct-delegation fixture, not the complete runtime governing closure.

Return only request digest and an inclusive evidence-expiry upper bound, never the
exclusive offline admission ceiling (which additionally depends on freshness).
Preserve Invalid/Unsupported from the native chain and its128byte decoder limit.

Alternatives: enabling a runtime provider is blocked by the separately documented
currentness artifact contract; duplicating signature/parsers is unnecessary.
The reviewed approach reuses the existing test-only primitives and retained public
signed vectors. Unsigned REQUEST construction follows the existing fixture recipe;
no new signatures, keys, registry entries or production source changes.

## Execution plan

1. Add failing composition tests with a non-accepting stub.
2. Implement exact joins and expose only verified delegatee from the chain checker.
3. Exercise peer/key/policy/scope/dependency/inventory mismatches, including swapping
   valid evidence and request together while configured inventory remains pinned.
4. Bounded offline native tests, independent review, no commit before coordination.

## Observed verification

RED:20existing tests passed and4new composition tests failed against the explicit
non-accepting stub. GREEN:24passed,0failed,0ignored after the narrow implementation;
compile2.37seconds, tests0.39seconds. The native controller granted a quiet window,
and it was released after both bounded offline runs. No VM or hosted-CI action.
Independent source review found no blocker within this declared fixture scope.
No full-suite claim.

Negative coverage includes policy fields, actual peer, configured inventory,
request KAR/dependency digests, missing/extra refs, configured-scope mismatch and
wrong key ID even when policy is changed too. A different already-signed valid
narrow-port delegation plus matching request is rejected while the configured
inventory stays pinned, then accepted only when that explicit fixture inventory
is also changed. That tests the three-way join, not authenticity of provisioning.

The helper trusts supplied signer contexts; unlike the Python offline verifier it
does not independently pin their membership against a configured signer_inventory.
It therefore does not claim complete offline-verifier parity or provisioning.
The helper has no session/counter/time-of-request check, revocation delivery or
runtime import. Supplied KAR terminal IDs are explicitly empty test context;
normal/emergency/controller governance remain outside the scope. The returned
expiry1800 is inclusive evidence, not freshness-limited admission1700. Existing
signed fixtures and source registry are unchanged.

## Publication revalidation on Windows

Fresh verification used the official Cargo CLI, a new isolated target directory,
`--locked --offline --features benchmark-harness --jobs 2`, a 95-second
owned-process deadline per invocation and free-disk/growth guards (6 GiB minimum,
2 GiB maximum growth). The cold build reached the deadline and its owned process
tree was stopped. A bounded incremental retry reused only that new target:
24 genesis tests passed (12.79 seconds compilation, 0.31 seconds execution).
The neighboring `connector_kar` target passed 15 tests; these overlap the reused
KAR cases above and must not be summed as independent coverage. Clippy for both
targets with `-D warnings` passed. The focused Python corpus and CI contract
checks passed 57 tests. No dependency downloads, VM operations or benchmark
workloads were performed. These are local results, not hosted CI or runtime
registration acceptance.
