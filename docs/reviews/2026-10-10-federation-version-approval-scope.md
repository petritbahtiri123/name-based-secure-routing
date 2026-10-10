# Proposed approval scope: separately versioned federation package

Status: proposal only. No package, authority, pin, verifier or Windows fixture was changed in this step. No publication is requested by this scope.

## Decision recommended

Authorize a local implementation and review of `federation-v0.1-development-v2`, explicitly opt the deterministic Go/Node/Python verification jobs into testing it, and retain independent verification of immutable `federation-v0.1-development-v1`. Keep protocol family `federation-v0.1` and manifest format 1. Do not reinterpret the old identity or replace its trusted digest.

Old v1 is the exact nine-file package from commit `7af982239dc8fbc67ae142037f192458c797f4d4`, with manifest SHA-256 `1ff9591b925e926e757bb57ab8f3cd1620b6ff9d41149df92ad5672ff810ab35` and accepted baseline `0849b986d065105441e116dce15294250a323926`.

Proposed v2 uses the already approved registry bytes present at `af15649678540d57770fd08ad09934a43c1f9241` (SHA-256 `ed880f236a2b4b5e11e281e58c540534e1cd27f7c752d3990291cf1be55c80d0`, 78,881 bytes). Its accepted authority baseline should identify that commit, rather than falsely retaining 0849b986. Preserve the seven other upstream authority pins exactly. New manifest digest is not yet computed or approved: generate deterministically, review the complete artifact diff, then record the version/digest binding explicitly. Do not bless the current mismatched `2ab828...` v1 manifest as v2.

## Existing semantic authority versus newly accepted trust

`a6ac60c21c6a7aeca659e0cfa9ba0aa986c641b7` froze the ACP authority profile. `docs/protocol/tranche2b-acp-wire-semantics.md` section 14 defines purpose 15, ACP_RESULT_SIGNING, exclusively for the outer ACP Result Envelope in the operator/federation trust domain. It is not a client identity.Purpose alias or permission to sign inner grants and credentials.

`af15649678540d57770fd08ad09934a43c1f9241` froze enrollment. `docs/protocol/tranche2b-enrollment-wire-semantics.md` section C defines purpose 16, ENROLLMENT_RESULT_SIGNING, for EnrollmentResultPayload COSE Sign1. Verification resolves protected nonempty kid through the operator trust registry and requires this exact purpose. Purpose 15 cannot substitute; device requests, transport proofs, local integrity, route grants, freshness, checkpoints, revocation and federation evidence remain distinct. Initial enrollment does not imply reenrollment, rotation or recovery support.

Thus this packages an already approved semantic change. However, adding v2 to the independent verifier's trusted versions **does expand its accepted authority**, including recognizing previously reserved purpose values 15/16 in the selected registry. It needs explicit approval; it is not a CI hash refresh. No new signer/key, network endpoint, runtime enrollment policy, or live federation authority is authorized.

## Exact proposed file boundary

Data changes:

- Restore only `vectors/federation-v0.1/manifest.json` and `vectors/federation-v0.1/authority-locks.json` to exact 7af98223 bytes. Verify the other seven existing package files already match that commit; do not regenerate v1. Preserve the overwritten e15b2511/current bytes and provenance in the evidence record/Git history.
- Add `docs/protocol/registries/archive/federation-v0.1-development-v1.json`, exact original 78,624-byte registry with SHA-256 `29311cb8e952e328eef7c69fb4776a85504ff4af5edf7c55faad53194d60dc7e`. Current live registry is unchanged.
- Add exactly nine files under `vectors/federation-v0.1-development-v2/`: `README.md`, `manifest.json`, `authority-locks.json`, `capability-vectors.json`, `error-precedence.json`, `signed-vectors.json`, `stateful-scenarios.json`, `static-vectors.json`, `threshold-vectors.json`. Preserve the six semantic vector JSON files byte-for-byte unless a separately reviewed necessity is found; purpose-version cases belong in verifier regressions, not silently rewritten historical vectors.

Implementation and tests:

- `scripts/federation_v01_vectors/package.py`; `scripts/generate_federation_v01_vectors.py`; `tests/federation/test_vectors.py`.
- `verifiers/federation-go/internal/packageverify/package.go`; `verifiers/federation-go/internal/packageverify/package_test.go`; `verifiers/federation-go/internal/verifier/verifier.go`; `verifiers/federation-go/internal/verifier/verifier_test.go`; `verifiers/federation-go/internal/schema/schema_test.go`; `verifiers/federation-go/cmd/verify/main.go`.
- `verifiers/federation-node/src/manifest.js`; `verifiers/federation-node/src/registry.js`; `verifiers/federation-node/src/verifier.js`; `verifiers/federation-node/test/manifest.test.js`; `verifiers/federation-node/test/full.test.js`.
- `scripts/ci/check.py`; `tests/ci/test_ci.py`; `verifiers/federation-go/README.md`; `verifiers/federation-node/README.md`; `docs/CI.md`; `AGENTS.md`; this approval record and its implementation evidence companion `docs/reviews/2026-10-10-federation-version-implementation.json`.

Use a closed version-to-manifest-digest/authority-source binding, with v1 still the default. Explicit CLI/API selection of v2 is required; package-provided version strings cannot alone opt a caller into new authority. Resolve the archived registry only for the exact pinned v1 identity, with no missing-file fallback. Hash-check and consume the same selected authority bytes throughout verification. Other locked authorities remain at their existing paths/pins. Generator check mode remains nonmutating. If implementation needs additional production files or changes the immutable-data boundary, stop and amend this scope before proceeding.

## Opt-in consumers and deterministic acceptance

Opt-in is limited to the Python conformance generator/checker, independent Go verifier, independent Node verifier and bounded CI commands explicitly selecting v2. Existing default commands select v1. Tests run both versions. The Go client runtime, gateways, transport, ACK code, current registry, deployed operators and historical evidence consumers receive no authority change.

Positive tests: v1 exact raw-byte identity and unchanged original pin; v1 verification against archived registry; v2 reproducible byte-identical generation twice and nonmutating check mode; all existing vector families through Go and Node for both versions; version-selected registry/schema recognition of 15/16 only under v2. Registry acceptance alone must not be reported as end-to-end ACP/enrollment conformance.

Negative tests: v1 rejects 15/16 as reserved; v2 still rejects 17 and unsupported values; default/v1-only caller rejects v2; unknown version/hash rejected; v1 label with v2 bytes and inverse rejected; altered registry, substituted locks, mixed-version artifacts, missing archive, symlink/alias and unlisted files rejected. Existing signed-object wrong-purpose tests must remain passing; purposes 15/16 must not substitute for existing federation signer purposes. Existing ACP/enrollment exact-purpose tests remain the authority for outer-result purpose separation; no new runtime implementation is implied.

Validation must retain the current failing Go package result and prove both-version verification under cached, bounded local checks plus independent review. No skipped gates or expected-failure conversion. A later hosted run and any commit/push/bypass require their own authorization. The reviewed Windows fixture correction remains separate, local and uncommitted.


## Approval and execution record

The user subsequently approved this exact scope for local implementation/testing
and a verified scoped local commit. No publication/bypass was authorized. Execution
preserves all nine v1 files and the six semantic v2 vector files byte-for-byte;
independent review confirmed both version pins and the archive. The one review
finding (Node caller-supplied unverified lock maps) was removed and regression-tested.
See `2026-10-10-federation-version-implementation.json` for exact runs and hashes.
