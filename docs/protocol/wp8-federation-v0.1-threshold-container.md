# WP8 Federation v0.1 Threshold Signature Container Decision Supplement

> **PROPOSED DEVELOPMENT PROFILE DECISION — REQUIRES HUMAN APPROVAL**

Decision `WP8-THRESHOLD-CONTAINER-01` is based on accepted Task 6 commit
`aa6375b1d3d00fdb92913e750bb27b290314fe7e`. It freezes a proposed wire
representation only. It does not authorize Task 7 vector-package generation,
Task 8/9 runtime work, or replacement of Task 2–6 semantic evidence before
human approval.

## Decision

Select **Option C: a versioned NBSR threshold evidence envelope containing
independent tagged COSE_Sign1 values**. Every signer signs the same exact
deterministic-CBOR `ThresholdSignatureContext`, except for the required
`group_id` that prevents reuse across semantically distinct threshold groups.
The envelope is referenced evidence and is not a signed Federation authority
object. No nineteenth object type, Core object, Core message, Federation
message, or new authority class is allocated.

Option A, COSE_Sign, provides a standard shared-payload multi-signature shape,
but its per-signature protected/unprotected header assembly and partial
collection representation create more collector-dependent canonicalization
surface. It also fits multi-set authorization poorly without an additional
policy envelope.

Option B, a bare canonical array of independent COSE_Sign1 objects, provides
excellent independent and offline signing but does not itself bind a policy,
authority scope, lineage, operation, validity, organizational diversity, or
multiple named groups. Those facts would remain external and substitutable.

Option C retains Option B's independent Sign1 verification while making the
missing policy and context binding explicit. It gives one deterministic outer
encoding, preserves partial Sign1 collection, permits offline signing, and
keeps Ed25519-to-successor-algorithm migration versioned at the evidence
container rather than coupled to a Federation authority-object allocation.
The cost is one NBSR-specific schema, which is bounded and independently
verifiable.

## Canonical envelope

The container ID is `nbsr-federation-threshold-evidence-v1`, version is `1`,
profile is `nbsr-federation-dev-v1`, and required capability is the already
allocated `FEDERATION_OBJECTS`. Unsupported container or signature-context
versions reject `ERR_VERSION` without mutation. The exact integer-key schema,
wire types, and generated tables are normative in
`registries/federation-v0.1-threshold-container-proposal.json` and
`wp8-federation-v0.1-threshold-container-allocation.md` if this supplement is
approved.

The top-level map binds:

| Key | Meaning |
|---:|---|
| 1 | container version `1` |
| 2 | profile ID `nbsr-federation-dev-v1` |
| 3 | exact registered target object class |
| 4 | SHA-256 of the exact canonical target payload |
| 5 | complete `ThresholdPolicy` including its self-derived policy ID |
| 6 | SHA-256 authority-scope digest |
| 7 | nullable generation, sequence, and affected-lineage digest |
| 8 | message/action, request/event/transition ID, validity window, context digest, and extension version |
| 9 | threshold groups in policy requirement order |
| 10 | optional approved `ExtensionEntry` array |

`policy_id` is SHA-256 over deterministic CBOR of the complete policy with key
2 set to CBOR null. The container carries the completed policy with key 2 set
to that digest. This prevents a textual policy name from silently selecting a
different threshold.

`authority_scope_digest` is calculated by the target object's already-approved
scope rules. It binds only the canonical scope, not private descriptive
metadata. The authorization context's key 5 is SHA-256 over deterministic CBOR
of its keys 1–4, 6, and 7. The message type is an existing Federation message value
and serves as the intended operation/action; this supplement allocates no new
action registry.

## Threshold policy and groups

`ThresholdPolicy` contains the allowed object classes, message types, authority
effects, deny-only bit, and one to four ordered `GroupRequirement` values. A
policy name is not self-authorizing: the verifier matches the complete
descriptor to the approved machine-readable named-policy definition. A
signer-selected descriptor and self-digest cannot alter the approved object,
message, effect, M/N, group, class, purpose, or diversity mapping. Each
requirement binds the group ID, M and eligible N, eligible classes, mandatory
per-class counts, eligible authority identities or a context-registry lookup,
minimum distinct organizations, allowed purposes, deny-only restriction, and
scope digest.

The envelope contains all named groups in policy order. Operator recovery is
one envelope with independent `recovery`, `registry`, and `witness` groups.
It is never flattened into one count. A signer identity may occur in only one
group. Activation requires every group to validate.

The proposed named Development Profile policies cover registrar 1-of-1,
ordinary witnesses 2-of-3, high-risk witnesses 3-of-5, global trust 3-of-5,
high-risk global/root transition 4-of-5, recovery 2-of-3 plus registry 1-of-1
plus witnesses 2-of-3, deny-only emergency 2-of-5, and separate conflict and
appeal decision plus witness groups. Emergency evidence is valid only for an
already-approved deny/restrict/revoke action and cannot add, restore, or
broaden authority.

The authorization context carries an `authority_effect` of exactly `deny`,
`grant`, `replace`, `recover`, or `decide`. Each named policy permits only its
listed effect. `deny-only` additionally requires exact effect `deny`.

Threshold evaluation counts distinct validated authority identities, never
array entries or keys. Organizational diversity counts distinct trusted
organization identities obtained from the accepted authority registry. An
outer organization value must equal that trusted value. Multiple keys or
authority IDs controlled by one organization do not satisfy independent
organization requirements.

## Signer entries and ordering

Each signer entry binds authority class, authority identity, key purpose,
protected `kid`, optional required organization identity/commitment, signed
payload digest, and exact tagged COSE_Sign1 bytes. Unknown non-critical
extensions are preserved byte-for-byte under existing extension rules;
unsupported critical extensions reject.

Within a group, signer entries sort lexicographically by the exact tuple
`(authority_class uint, authority_id bstr, key_purpose uint, kid bstr)` using
the natural integer and byte-string values. Groups appear in the same order as
the policy requirements. A duplicate tuple, a repeated authority identity in
a group, or reuse of an authority identity across groups rejects
`ERR_AUTHORITY`. Collector input order is not signed; collectors sort entries
before encoding, so different arrival order produces identical canonical
envelope bytes.

## COSE signature input

Every entry is an attached-payload, tagged COSE_Sign1. Protected headers are
exactly `{1: -8, 4: kid}`, the unprotected map is empty, external AAD is the
empty byte string, and Ed25519 is the only accepted algorithm. The attached
payload is deterministic CBOR of:

```text
{
  1: "NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1",
  2: 1,
  3: "nbsr-federation-dev-v1",
  4: target_object_class,
  5: payload_digest,
  6: policy_id,
  7: group_id,
  8: authority_scope_digest,
  9: lineage_context,
  10: authorization_context
}
```

COSE computes the ordinary Sign1 `Sig_structure` over those exact attached
payload bytes. An entry's `signed_payload_digest` must equal key 5, every Sign1
payload must equal the context reconstructed from the envelope, and protected
`kid` must equal the signer entry and accepted key record. Consequently a
signature for another payload, object class, policy, group, scope, generation,
sequence, lineage, action, request/event/transition, validity window, profile,
or extension version cannot count.

One-key-one-purpose is enforced from accepted `KeyAuthorizationRecord` state.
The accepted authority registry must resolve each `kid` and public key to
exactly one authority identity; ambiguous reuse rejects `ERR_IDENTITY`.
The signer entry cannot relabel a key. Revoked, non-active, not-yet-valid,
expired, wrong-class, wrong-purpose, unknown-`kid`, or cryptographically invalid
entries reject the whole container even if other entries meet M.

## Collection, decisions, and precedence

Zero signatures or any group below M is pending evidence only:
`PENDING/ERR_EVIDENCE_MISSING` for zero entries and
`PENDING/ERR_WITNESS_THRESHOLD` for a partial group. It creates no authority
and never mutates authority state. Exact-threshold and over-threshold packages
accept only when every supplied entry and every required group validates.

Malformed, unauthorized, duplicate, revoked, expired, wrong-purpose, mixed
digest, or invalid-signature packages reject as a whole. Unknown authority
classes reject `ERR_AUTHORITY`. Resource checks occur before cryptographic
work and return `ERR_RESOURCE_LIMIT`; unsupported critical extensions precede
cryptographic work and return `ERR_UNSUPPORTED_CRITICAL`. All rejection and
pending outcomes have mutation flag false. Authority mutation remains the
responsibility of the already-approved Task 2–6 semantic transition after
container validation.

## Replay and substitution resistance

The signature context binds the exact canonical object digest, registered
object class, policy digest, named group, authority-scope digest, affected
lineage, generation and sequence where applicable, existing Federation message
type, request/event/transition ID, validity interval, profile, and extension
version. A receiver also compares those values with the operation it is
processing. Same context and digest may be idempotent under existing semantic
rules; altered context is replay/substitution and cannot authorize another
operator, object, service, generation, recovery, conflict, appeal, governance,
or root action.

## Development Profile resource limits

Limits are four groups, five signatures per group, sixteen total signer
entries, 65,536 encoded bytes, 64 bytes each for authority identity,
organization identity, and `kid`, nested depth eight, and sixteen Ed25519
verification attempts. Exceeding any bound deterministically rejects
`ERR_RESOURCE_LIMIT` before authority mutation. Parsers must bound the raw
container before decoding and may stop after the first deterministic error in
the approved validation precedence.

Verification requires the already allocated `FEDERATION_OBJECTS` capability
in the authenticated negotiated-capability context. Missing capability rejects
`ERR_UNSUPPORTED_CRITICAL` without signature work.

## Privacy

The container may expose only scoped public authority IDs or approved private
commitments, protected `kid`, authority class, key purpose, and the minimum
organization identity/commitment needed for diversity. It must not contain a
subscriber identity, recovery share, private key, Origin Endpoint, unrelated
organization metadata, or unnecessary topology. Private profiles may use an
already-approved scoped authority commitment; this supplement does not invent
a new commitment scheme.

## Literal vectors and implementation boundary

The specification-authored package contains 78 literal valid, pending, and invalid
containers. Each records canonical CBOR hex, SHA-256, decision, reason, and a
false mutation flag. The independent verifier recomputes canonical encoding,
policy and context digests, COSE protected headers and Ed25519 signatures,
approved named-policy selection, capability agreement,
authority/purpose/organization eligibility, threshold results, replay binding,
validity, extension shape, and resource decisions. The renderer is confined to this proposal package;
Task 7 must consume these frozen bytes and must not regenerate them through
Task 7 runtime/vector code.

After approval, Task 2–6 paths that need raw multi-authority proof may replace
their opaque authenticated evidence inputs with validated containers. Their
authority rules, threshold meaning, state transitions, and mutation behavior
must not change. Until approval, no runtime integration is authorized.

## Remaining ambiguity

There is no unresolved Development Profile wire choice in this proposal.
Production-profile algorithm agility, production governance membership,
institutional organization identifiers, and private commitment schemes remain
outside Federation v0.1 Development Profile scope.
