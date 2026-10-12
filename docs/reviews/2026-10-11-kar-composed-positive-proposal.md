# One composed-positive KAR fixture

**Decision requested:** approve one deterministic test signature over the unchanged
purpose-3 genesis payload, using the existing openly published test root, and its
bounded composed acceptance/rejection verification. No keys, signatures or code
were generated in preparing this proposal. The [manifest](2026-10-11-kar-composed-positive-proposal.json)
pins the exact source and identity values.

## Exact proposed record

Create exactly one new retained COSE_Sign1 record, fixture ID
`test-only-kar-genesis-purpose3-positive-v1`, in the new test artifact
`crates/nbsr-transport/tests/fixtures/connector-kar-genesis-positive.json`.
Its payload is byte-for-byte schema fixture `valid-root-authorized-genesis` from
`vectors/federation-v0.1-schema-proposal/literal-fixtures.json`, SHA-256
`714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed`.
No payload fields change. Historical signed packages remain untouched.

| Binding | Exact supplied test value |
| --- | --- |
| Root operator | ASCII `O` repeated 32 bytes; synthetic fixture identity |
| Root key ID / public key | `root-kid` / `03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8` |
| Root signing material | Existing public `bytes(range(32))` recipe in `tests/federation/test_cose_authority.py`; no random key generation |
| Root purpose/state/lineage | IDENTITY_ROOT 1; ACTIVE 2; unrevoked; generation 1, sequence 1 |
| Root validity | Inclusive 900 through 2100 |
| Subject operator / key ID / public key | Same `O` repeated 32 bytes / `operational-kid` / ASCII `K` repeated 32 bytes |
| Subject purpose/state/lineage | REGISTRY_SIGNING 3; ACTIVE 2; unrevoked; generation 1, sequence 1 |
| Subject validity | Inclusive 1000 through 2000 |
| Issuer and authorizer | Both exact class-1 references to that root operator and `root-kid` |
| Previous/recovery/revocation references | Predecessor and recovery-transition fields absent; revocation reference null |

The subject public-key literal is existing schema material; this test neither
creates a subject private key nor proves possession or operational signing by the
subject. The signature verifies the root's authorization of the exact recorded
bytes relative to supplied test trust. It does not establish genesis provenance.

Use the existing tagged COSE_Sign1 encoding: tag 18, protected EdDSA algorithm -8
and exact `root-kid`, empty unprotected map, attached exact payload and empty
external AAD. Reconstruct the already public root signing key only in memory;
persist no private-key file, credential, certificate, trust-store entry or access
configuration. Retain only public fixture metadata, payload, signature and hashes.

## Purpose and scope separation

The only positive mapping is **that root to that purpose-3 subject**. Required
purpose **12 (REVOCATION)** and purpose **14 (FEDERATION_TRANSPORT)** both reject
this signed record. No positive purpose-12 mapping is proposed. Adding one would
be a new fixture authorization decision and is unnecessary to close the specific
composed-positive gap in the implemented verifier.

KAR has no service-scope field. Do not add or infer service, tenant, action,
normal-roster membership, organization, quorum or control-domain authority.
The five normal roster IDs and keys are not subjects of this record; their
identity-root mappings and accepted governance remain separate open decisions.
No child key alias, numeric-purpose cast or purpose fallback can bridge them.

## Required verification after approval

The existing Python verifier and native composed gate must both accept the exact
record under the exact supplied context at 1000, 1500 and 2000. Native acceptance
must pass the real signature verifier and semantic gate, with no bypass or
semantic-only substitute. This closes only successful composed acceptance for
the isolated genesis gate under supplied test trust.

Using the same signed bytes, reject times 999 and 2001, wrong expected purposes
12 and 14, wrong expected operator/child kid/public key/payload, wrong root
kid/key/operator/purpose, inactive or revoked root, and terminal subject ID.
Separate supplied root contexts whose validity starts after the test time or
ends before it must reject. Root and record exact expiry remain inclusive.
Byte-mutated signature, altered signed payload, trailing/noncanonical envelope
and detached-payload cases must fail at the cryptographic/envelope boundary.
These cases create **no additional signatures**.

Existing unsigned tests retain detailed genesis/rotation/recovery, child-state
and extension coverage. Unchanged retained signed rotation/recovery records
remain rejection evidence with their original metadata; they do not establish
successful lineage verification. No newly signed malformed, rotation, recovery,
purpose-12 or purpose-14 records are included in this request.

## Isolation and review

Keep the artifact consumed only by the existing `cfg(test)` integration target
and a bounded fixture checker. Do not add it to development or production trust
registries, packaged credentials, runtime configuration, normal-roster inputs or
source-authority overlays. The checked result stays private, with no Authority,
owner, permit or READY conversion. Existing public fixture keys confer no secret
or persistent access; no real trust configuration is changed.

The signature is ordinary cryptographic data: it cannot intrinsically prevent
someone from deliberately trusting the public test root elsewhere. Isolation is
enforced by test-only consumers and absence from runtime trust, not a claim that
the bytes are cryptographically unusable. The historical logical-time interval
also remains unchanged; it is not current production authorization.

Independent `connector_model_review` recommended this single unchanged purpose-3
record as the smallest decision, with composed rejection for purposes 12 and 14.
It found no need to introduce a new purpose-12 identity mapping for this gap.
No build, test, signature or key generation occurred during this design task.
Approval would permit the one signing/materialization action and bounded tests;
runtime activation, normal-roster integration and stage advancement remain outside
scope.
