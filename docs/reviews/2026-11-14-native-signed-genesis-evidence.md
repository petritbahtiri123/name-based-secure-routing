# Bounded native signed genesis evidence, 2026-11-14

## Scope

The new `connector_genesis` Rust integration-test target verifies the retained
NOR/direct-delegation corpus using the existing strict CBOR codec, exact COSE
signature primitive and supplied test-signer container. The helper lives under
`tests/support/connector_genesis.rs`, not the production library. No route,
registry, dependency, trust policy, transport source or runtime behavior changed.

This advances the corpus-only prerequisite documented in the signed-genesis
review. It does not close full registration or Stage3 readiness.

## Checks

- Exactly two bounded signed objects; both signatures verified before semantics.
- Exact object types, closed fields, types, lineage and signer purposes5/6;
  supplied signer operator/kid, lifecycle, validity and revoked-state checks.
- Ownership serviceID derivation, owner/delegator/delegatee binding and actor loops.
- Direct-delegation ancestry, inclusive record windows, signer-window intersection,
  ownership containment and revoked-record rejection.
- Every scope dimension checked: exact first six dimensions, narrowed ports,
  protocol/action subsets, no restored subdelegation or increased depth.
- Successful evidence contains only chain window and leaf digest. It is not an
  authority, registration receipt, owner handle, revocation event or READY token.

`Invalid` means a checked structural/contextual requirement failed. `Unsupported`
means recognized out-of-slice input was not fully evaluated, NOT that it is valid.
ACE names, updates, noncritical extensions and child-delegation contexts remain
outside this ordinary-LDH direct-genesis slice. The reused connector decoder
also bounds all text values to128bytes; the semantic name validator's255byte
ceiling does not expand that parser bound. It does not settle normative IDNA,
validate missing parent ancestry, update/recovery provenance or full governance.
Malformed fields and signature failures are not converted to Unsupported.

## Validation and review

- RED: target failed because helper was absent.
- During implementation, a lifetime compile error, mistaken actor enum values,
  a test delimiter error and a Clippy style warning were caught and corrected.
- Independent review identified nullable issuer kid and genesis-only parent-digest
  classification issues. Both corrected with focused regressions.
- Native target:19 tests passed, comprising15 reused KAR neighbors and4 new test
  functions. The signed-corpus function verifies13 cases (4positive/9negative)
  against pinned case/outcome sets, exact success windows and leaf digest.
- Separate signed-input checks cover signer purpose/operator/key/kid/lifecycle,
  revoked state, validity/intersection and signature corruption.
- Explicitly unsigned semantic probes cover malformed/unknown fields and supported
  versus unsupported classification. They are NOT signed conformance evidence.
- Chain-only expiry1900 is not the separate transport-KAR expiry1800.
- Target Clippy with `-D warnings` passed;43 CI contract tests passed.
- `connector_genesis` is selected in the existing Rust connector CI command;
  no ignored/live test activation or hosted run was performed.

Commands, with existing cache/supervisor and offline bounds:

```text
cargo test --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --jobs 2 --test connector_genesis
cargo clippy --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --jobs 2 --test connector_genesis -- -D warnings
python -B -m pytest -q -p no:cacheprovider tests/ci/test_ci.py
```

Local commands reused the verified target cache, used at most2 build jobs and a
95-second owned-process deadline, with8GiB/6GiB disk guards and2GiB growth ceiling.
No dependency download, new key, VM action or measured benchmark occurred.

## Remaining integration gates

No complete signer provisioning, name lifecycle/ownership transfer/recovery,
normal3/5/emergency2/5 governance, all-applicable controller authority, authenticated
currentness/revocation producer, durable restart floor, real timer, native
registration provider or READY integration is established. Those remain separate
work, not an excuse to enable a partial runtime adapter.

## Follow-up parser boundary finding

Independent review found that `connector_control.rs::Decoder::node` caps text
at128bytes before the genesis semantic name check can run. This is an observed
implementation limit, not a proposed federation name rule. Ordinary LDH names
of129..255bytes can satisfy Python federation name validation but are outside
this native evidence parser subset. They currently return a decode failure
(classified Invalid by this test helper), not Unsupported or a normative finding
that the name itself is invalid. Do not interpret such rejection as cross-language
semantic agreement. No production parser bound was widened.

The added128/129/255 regression uses unsigned CBOR text probes with valid LDH label
lengths. It checks the real reused decoder:128round-trips;129and255reject. It is
parser-boundary evidence, not signed-object conformance or runtime authorization.
A separately reviewed federation decoding boundary is required before claiming
full long-name coverage. The prior19-test result above predates this follow-up.

Follow-up execution: after the active benchmark controller confirmed no timed
window, the same bounded/offline target completed:20passed,0failed,0ignored;
compile1.49seconds and tests0.29seconds. This includes the new boundary probe.
Python's actual ownership `_canonical_name` separately accepted the same three
names. No full-suite or hosted-CI rerun is claimed for this documentation/test-only
follow-up. Independent review found the boundary diagnostic and scoped claims
sound; its pending-execution caveat was resolved by this recorded run.
