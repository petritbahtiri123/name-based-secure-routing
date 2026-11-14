# Retained signed genesis evidence corpus, 2026-11-14

## Deliverable

`crates/nbsr-transport/tests/fixtures/connector-genesis-evidence.json` retains
13 deterministic public-test-only NOR genesis/direct-delegation chains, exact
wire/payload hashes, requested scope, logical time and expected semantic outcome.
The existing oracle is `tests/test_connector_registration_authority_offline.py`;
its source hash is retained. The same openly known `bytes(range(32))` seed is
used, not a real credential, generated secret or provisioned authority.

`python -B -m scripts.extract_connector_genesis_evidence` regenerates in memory
and compares exact bytes. It invokes the existing public test signing oracle,
even in comparison mode. `--write` exports; neither mode accesses the network,
VMs, production keys or runtime configuration. Routine pytest validation only
reads public retained material and verifies signatures, without signing.

`tests/federation/test_connector_genesis_evidence.py` first independently verifies
every COSE signature and exact retained payload, including all rejection cases.
It then calls the existing Python `DelegationVerifier` with supplied test signer
contexts (purposes5/6). Thus negative results test semantics, not broken signatures.

Four positives: exact scope, inclusive lower/upper validity boundaries, and a
requested port narrower than the signed grant. Nine negatives: before/after
validity, widened port/protocol/action, wrong genesis serviceID, forbidden direct
parent digest, delegation outliving ownership, and revoked delegation.

The ordinary LDH `service.example` fixture deliberately does not choose a
normative ACE/IDNA profile. See the separate ACE parity diagnostic. This is a
reusable cross-language evidence input, not a new Python verifier or a superficial
wrapper. The next meaningful stage is native bounded semantic verification of
these retained objects, including signer context and exact binding checks.

## Validation

- RED: focused test failed because retained corpus did not exist.
- GREEN: focused test passed, checking13 chains/26 valid signatures plus expected
  semantics. One pytest function covers the13 explicit corpus cases.
- Deterministic regeneration matched retained bytes.
- Focused test plus existing signed-registration and purpose14 conformance
  neighbors:57 passed in0.76s on the final review-adjusted run.
- Scoped Ruff and `git diff --check` passed; no full suite or hosted CI run.
- No Rust build or VM/benchmark execution for this corpus step.

Independent review verified all13 retained cases without invoking signing, and
recommended pinning corpus ID, exact case IDs/outcomes and two-record cardinality.
Those guards were incorporated before the final57-test run.

## Limits

Not a registration receipt, issuer provisioning proof, currentness/revocation
producer, native name/delegation parser, normal3/5/emergency2/5 governance proof,
READY, real timer, private-origin integration or runtime admission enablement.
The full matrix remains applicable. Fixtures do not authorize live trust, and
both runtime/live flags remain false. Subdelegation, valid extensions, lineage,
transfer/recovery and arbitrary ACE names remain outside this corpus, not globally
invalid. No route behavior, registry, dependency or historical pin was changed.


Follow-on: the bounded native test-only verification step is recorded in
`2026-11-14-native-signed-genesis-evidence.md`. Full semantic/runtime/governance
coverage remains outside that slice.
