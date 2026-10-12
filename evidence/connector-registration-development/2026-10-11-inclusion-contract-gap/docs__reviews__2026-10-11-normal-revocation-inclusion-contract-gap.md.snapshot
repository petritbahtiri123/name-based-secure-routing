# Record inclusion: exact leaf contract required

Status: inspected and blocked before implementation. No runtime/verifier code,
wire format, historical pin or conformance vector was changed. The prior signed
checkpoint/witness composition remains valid within its stated scope; it does not
establish inclusion of the revocation record.

## Existing contract and concrete gap

The development profile's cryptographic freeze gate defines
`SHA-256(0x00 || canonical_leaf)`, node hashing and the empty-tree root. The schema
defines InclusionProof log/scope/checkpoint/tree/leaf/path/hash-profile/object-class
fields. `InclusionProof.verify` in `nbsr/federation/transparency.py` checks exact
checkpoint binding, freshness, supplied leaf digest and Merkle membership.

However, that API receives `canonical_leaf` from its caller. The existing direct
test uses `b"a"` and rejects `b"b"`; it does not define a TypedRevocationRecord
leaf representation. `_Record.canonical_bytes` encodes the entire payload, and its
digest hashes those bytes. TypedRevocationRecord requires field 39, whose closed
TransparencyReference contains log ID, checkpoint digest, tree size and nullable
inclusion-proof digest.

If field 39 identifies the checkpoint containing that same final record, using
the full final record as its leaf creates this dependency:

```
record bytes -> leaf/root -> checkpoint digest -> record field 39 -> record bytes
```

A non-null proof digest may introduce another dependency through the proof's
checkpoint and leaf fields. This is a construction/semantic gap, not a demonstrated
weakness in the Merkle verifier. No inspected source specifies excluding field 39,
zeroing/nulling a digest, a separate leaf projection, external detached evidence,
or prior-checkpoint semantics as the approved solution. None is introduced here.

Inspected anchors:

- `docs/protocol/federation-v0.1-development-profile.md`, cryptographic freeze gate.
- `docs/protocol/registries/federation-v0.1-schema-proposal.json`,
  TransparencyReference, InclusionProof and TypedRevocationRecord definitions.
- `docs/protocol/wp8-federation-v0.1-schema-allocation.md` and schema-requiredness.
- `nbsr/federation/fields.py`, `revocation.py`, `transparency.py` and direct
  transparency tests; related renderer definitions and archived registry search.

The independent reviewer also inspected the profile/schema, historical requirements,
implementation and transparency tests and found no accepted cycle-free mapping.
This is a scoped source finding, not a claim that no external decision can exist.

## Bounded diagnostic and checks

The pure public-data diagnostic reads the retained valid normal-record literal.
It constructs a one-leaf checkpoint and proof without generating keys/signatures:

1. Existing inclusion verification accepts the original full bytes in that tree.
2. The original record's field 39 does not reference the constructed checkpoint.
3. Rebinding field 39 changes the canonical leaf and original signature payload.
4. The existing verifier rejects the rebound bytes against the old proof/root.
5. Rebuilding the root for those rebound bytes changes the checkpoint digest again.

All five assertions passed. This demonstrates the ordinary construction dependency;
it is not a proof of mathematical fixed-point impossibility or accepted signed
inclusion evidence. The existing exact inclusion regression passed: **1 pytest
test**, no skips/deselections. Its wrong-leaf/checkpoint/path assertions remain
unchanged. No RED/GREEN implementation claim is made because no new contract was
selected. Diagnostic source, outputs, commands, hashes and cleanup are retained in
the adjacent JSON manifest and evidence directory.

Broader tests, prior 123-test witness composition, Rust/Go/live tests and hosted CI
were not rerun: executable repository sources are unchanged. No new CI selection
is required for this documentation-only checkpoint. Independent contract review
confirmed the stop boundary; it did not rerun tests.

## Precise prerequisite and recommendation

Provide an existing approved source, or approve a separate versioned semantic
mapping that defines all of:

1. Exact canonical revocation leaf bytes and their cryptographic binding to the
   immutable signed TypedRevocationRecord.
2. Whether field 39 references prior transparency evidence or the checkpoint
   containing this record.
3. Placement and binding of checkpoint and inclusion-proof references without
   self-reference, preserving record signatures, scope, object class and lineage.

An external proof bound to an immutable record is a possible design direction,
not an approved mapping or a selected implementation. Do not silently omit signed
fields, invent placeholders or reinterpret field 39 to make a fixture pass. Once
the exact mapping is approved, reuse the existing inclusion verifier and integrate
wrong leaf/digest/checkpoint/object-class/reference/replay and no-mutation cases
with the completed signed checkpoint/witness checks.

Current governing configuration/provenance and durable restart floors remain
separate later gates; neither resolves this leaf-definition gap. All three authority
modes remain required. Runtime/live flags remain false; Stage 3 partial, 2/10
complete; final comprehensive security audit still required. No keys, sockets,
installation, hosted CI, deployment, commit, push or security-setting changes.
