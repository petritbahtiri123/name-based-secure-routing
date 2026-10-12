<!-- Publication derivative; original SHA-256 3aab30af76fdcd7d38129eccab9af36ebef868cf1574bf443f3174b72261a1fd. Personal attribution replaced by role label. Historical approval and result claims refer to the original local artifact, not a new action. -->

# Approved v2 record inclusion: bounded local conformance

project owner approved REVOCATION-INCLUSION-01 for a separate local conformance amendment.
`scripts/revocation_inclusion_v2.py` implements that mapping. New registry metadata
is `docs/protocol/registries/revocation-inclusion-local-v2.json`; six retained public
packages are in `vectors/revocation-inclusion-local-v2/packages.json`. Runtime/live
flags remain false. Historical profile/registry/vector files are unchanged.

## Exact evidence chain

The original canonical version-2 TypedRevocationRecord bytes are signed through
Option C, hashed as the record identity, and logged unchanged as the Merkle leaf
using the existing 0x00 domain. Field 39 binds the previously accepted checkpoint
A and contains a null proof reference. The detached closed nine-field package
carries later signed checkpoint C, signed inclusion/consistency proofs, signed
witness statements and A. Every reference, scope, class, profile, version and
signature is checked. The inclusion index must follow A's tree, object class must
be exactly 13, and C must be A's immediate successor with valid consistency.

The historical typed-record parser still rejects version 2. The local parser
explicitly selects v2 and reuses unchanged field validation through a temporary
v1-discriminator syntax view. That view is never signed, hashed, logged or used for
identity/lineage; all such operations use original v2 bytes. The shared offline
threshold verifier adds an explicit expected-profile keyword for this amendment.
Its historical default remains unchanged and rejects the new profile. This is
not a change to a production authority source overlay or runtime parser.

Required normal authority is still class 4, purpose 12, 3/5 with independent
five-member control context and exact typed enforcement. Witnesses use existing
2/3 or 3/5 policies only in independently configured applicable test contexts.
No controller/emergency substitute, universal witness rule, roster shrink, field
omission or trust expansion is introduced. Controller/emergency runtime obligations
remain intact; this selector's implementation is normal-mode local conformance only.

## Transaction and replay boundary

The immutable FixtureState is a serialized test oracle, not a store or authority
provider. Rejection/pending returns its exact input identity without changing a
checkpoint floor, record, retained revocation marker or event binding. Successful
forward validation returns a new state only after every proof and signature check.

F=A permits forward verification; F=C permits fresh evidence reuse. Other floors
reject without replacing F with package A. An already-applied identical record
additionally requires F=C; a rolled-back F=A cannot claim idempotent success.
Freshness is checked even for reused evidence. Expired/stale evidence cannot remove
an already retained terminal denial marker.

Same-record/same-event reuse returns the same state. Same record under a newly
authenticated event ID atomically retains that event-to-record binding without
reapplying the revocation or moving the checkpoint floor. A later distinct record
cannot reuse that event ID. Ordinary same-generation record updates are tested with
one proper immediate checkpoint successor; recovery/new-generation authority and
broader historical proof chains are outside this slice and reject.

Fixture requests and retained markers are in-memory explicit test state; their
retention does not prove crash consistency, bounded service-lifetime storage or
rollback-resistant restart. No real work is cancelled or registration admitted.

## Validation

Final focused run: **200 passed**, no skips/deselections: 76 new inclusion tests,
123 normal-conformance/witness/transparency/threshold/revocation neighbors, and
one new CI-selection regression. Six retained packages cover 3/4/5 normal signers
and both witness policies, with forward and idempotent checks. Historical 89
threshold literals are separately checked under the unchanged default profile.

RED evidence includes the initial missing API, the rolled-back floor case, and
the independent-review three-step replay reproduction: R/E1 accepted, R/E2 reused,
then an otherwise valid successor R2/E2 incorrectly accepted. Both behavior failures
are fixed and retained as regressions. Initial lint reported two unused test imports;
those were removed. Final lint/format/diff checks and scoped independent review
are clear. The reviewer did not independently rerun tests. Exact commands, results,
resource readings, hashes and source snapshots are in the adjacent JSON manifest.

Focused commands (use provisioned runtimes and existing resource supervisor):

```
python -m pytest -q -p no:cacheprovider tests/federation/test_revocation_inclusion_v2.py
python -m scripts.revocation_inclusion_v2 --check
python scripts/verify_federation_threshold_container_fixtures.py --check
```

The python-protocol CI profile selects the new federation tests and retained-v2
package check. This was checked locally, not run on hosted CI. Broad repository,
disk/ACL persistence, Rust/Go/live and deployment tests were not run because those
paths and capabilities are outside this change. No new keys were generated: signing
reuses existing explicitly public deterministic threshold/log/witness test material.

## Remaining Stage 3 gates

This now proves exact full-record inclusion and signed checkpoint/witness consistency
under explicit fixture configuration. It does not authenticate that configuration's
real provenance/currentness, establish durable restart floors, implement all-mode
live authority, support broader proof-chain renewal or demonstrate deployed cleanup.
Later floors can make this bounded package unusable; that never undoes a retained
denial. Stage 3 remains partial, stages 1–2 remain 2/10 complete. The comprehensive
security audit before a real pilot remains required. No sockets, installation,
hosted CI, runtime activation, commit or push occurred; all work is uncommitted.
