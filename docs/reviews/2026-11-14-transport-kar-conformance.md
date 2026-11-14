# Retained transport KAR conformance, 2026-11-14

## Scope

The latest provider proposal preserves controller, normal 3/5 and emergency 2/5
requirements. Controller-only is superseded. No positive registration provider,
Authority implementation, READY path or runtime/live flag changes are made here.
Generic native `verify_genesis` already supports exact transport purpose 14;
this change adds cross-language evidence, not another verifier.

The fixture exports default `key_authorization` from
`tests/test_connector_registration_authority_offline.py::fixture()`.
Execution of that existing known public deterministic test-seed oracle was
explicitly authorized. No new secret or operational credential is introduced.
These public fixture bytes must never be installed as real trust or credentials.

The JSON records the oracle source SHA-256 and exact retained wire/payload hashes:

- Wire: `6f769236943bcb4c6ded7f0f374966aa48ab4d9a14ed386bf7f4573e1c088008`
- Payload: `335f1b59b11997e0355bcd357cfae0f3a8c9c0b0db8db88e8f1ba0d3d5789b69`

Export used `runpy.run_path`, the oracle's default `fixture()`, and verification
of its complete offline registration input before retaining only the signed KAR
message, expected payload and public metadata. Normal conformance tests read
the retained bytes and perform no signing.

## Checks

- Initial RED: 7 Python cases failed specifically for the missing fixture.
- Python conformance: 13 passed; scoped Ruff passed.
- Conformance plus offline registration authority and key-authorization neighbors:
  113 passed.
- Independent source review found no scoped blocker. Its suggestion to pin exact
  payload/public-key identity independently in Rust was incorporated.
- Native `connector_kar`: 15 passed, including 3 new cases. Locked/offline Cargo,
  existing cache, two jobs, 40.20s compile and 0.19s test execution; exit 0 before
  the 95-second work deadline. No downloads or VM access.
- Rust formatting and scoped whitespace check passed.

Coverage includes signed purpose14 acceptance, inclusive validity, root/KAR
intersection, wrong-purpose/root/child rejection, expiry and payload/signature
tampering. Purpose14 cannot substitute for purpose12 revocation authorization.
Existing python-protocol CI includes tests/federation and Rust CI selects
connector_kar. Hosted CI and the full repository suite were not run.

## Limits and reconciliation

This is test-only supplied trust, not real provenance, registration readiness or
stage 3 closure. Delegation/governance/currentness, all-mode event delivery, real
clock policy and rollback-resistant restart remain separate prerequisites.

The old full-model review's composed-positive-incomplete statement is historical:
current source already has a signed purpose3 positive and five purpose12 KAR
chains under supplied test trust. This change closes only the retained signed
purpose14 cross-language evidence gap.
