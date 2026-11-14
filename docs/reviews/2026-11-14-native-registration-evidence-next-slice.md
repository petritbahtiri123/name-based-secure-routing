# Next native registration evidence slice: historical design

This is the pre-implementation design snapshot, not the current completion
status. The bounded test-only checker and request/evidence binding were
subsequently implemented; see `2026-11-14-native-signed-genesis-evidence.md`
and `2026-11-14-native-request-evidence-binding.md`. Neither closes the runtime
registration or governance gates described below.

## Evidence and purpose at design time

Native `connector_kar::verify_genesis` and its retained public-purpose14 corpus
already establish bounded transport-key evidence under supplied test trust.
There is no native counterpart to Python's signed `DelegationVerifier.verify`
for ownership/delegation. The existing route-admission attestation verifier is
not a substitute. The missing work is semantic composition, not another wrapper
around signature success or a larger test count.

References:

- `nbsr/federation/ownership.py`: canonical name and service-ID derivation,
  owner/issuer identity, lifecycle and transfer/continuity semantics.
- `nbsr/federation/delegation.py`: exact scope, graph/ancestry checks,
  validity containment, narrowing, actor/digest repetition and signer purposes.
- `nbsr/connector_registration_authority_offline.py`: exact registration action,
  request/dependency inventory, instance-local fixture receipts and limitations.
- `docs/reviews/2026-10-11-registration-provider-contract-proposal.md` and
  `2026-10-11-registration-full-model-acceptance.md`: full governance requirements.

## Approaches

1. Connect fixture signature results directly to the registration owner: rejected.
   This would disguise missing governance/currentness as positive authority.
2. Port the complete production registration provider now: too broad for a
   prerequisite slice. Provisioning, complete mode enforcement, time/restart and
   activation are unresolved separate boundaries.
3. Retain an oracle-checked signed corpus, then implement one explicit test-only
   direct-genesis semantic composition: recommended. Reuse existing native strict
   CBOR/signature code, Python's specified semantics and the exact public test seed.

## First deliverable: immutable semantic corpus

Export the existing oracle's ownership root and direct delegation along with
the requested registration scope. Preserve source hashes, individual wire/payload
hashes and explicit signer-purpose/identity/validity test inputs. Reuse the same
known public fixture seed only; introduce no real credential or trust store.
Test consumers never generate signatures. Independently pin corpus identity.

Include signed semantic negatives produced by the existing oracle, not only
unsigned byte tampering. Run every case through the existing Python verifier and
retain the expected reason/category. This is necessary to catch a native parser
that verifies signatures but fails to enforce ancestry or scope.

Required cases:

- Valid exact genesis ownership plus one direct delegation; inclusive record and
  signer boundaries; their intersected validity window.
- Wrong purpose 5/6, kid, operator, class or root identity; revoked/inactive signer.
- Canonical service identity/name mismatch, malformed name, mismatched ownership
  issuer/owner; malformed deterministic CBOR and unknown critical extension.
- Delegator not the ownership owner; delegatee/actor loop; wrong service/name;
  delegation extending outside ownership validity; signed revoked ownership/grant.
- Requested scope widening in each constrained dimension, ports, protocol/action,
  depth or subdelegation. Registration action 24576 is not application admission.
- Valid narrower requested port/protocol/action scopes must succeed; equality is
  not a replacement for the existing intersection/subset rules.
- Missing, extra, reordered or duplicated chain records; altered payload/signature.
- Unsupported updates, ownership transfer/recovery and child delegations must be
  explicitly classified outside this slice, never silently accepted as genesis.

## Second deliverable: bounded native evidence checker

Only after the corpus is checked, implement an internal test-target checker for
exactly two genesis objects. It must compose existing signature verification with
the corpus-defined ownership/direct-delegation semantics. The result may expose
verified evidence identities and intersected validity for tests, but cannot
implement `Authority`, construct registration `Decision`, change an owner, claim
current governance, emit an authenticated runtime event or enable READY.

The subset is an explicit test API boundary, not a change to frozen wire rules.
Valid protocol inputs outside it must report unsupported scope, not be described
as globally invalid. Do not invent an A-label subset or skip ACE normalization;
choose an existing compatible canonical-name implementation or settle the exact
compatibility contract before claiming support for arbitrary names. A fixed-name
fixture acceptance alone is not a general ownership verifier.

## Material progress and stop conditions

Corpus-only work closes interoperability evidence debt but not implementation.
The native checker is material progress only if correctly signed semantic-negative
cases fail for semantic reasons and both language implementations agree on the
supported boundary. A signature-only test or constant allowlist is not completion.

Before implementation, review the corpus categories and canonical-name parity.
If achieving parity requires a new dependency, altered wire semantics or a new
trust/policy decision, report that choice rather than widening the task silently.

## Independent review and discovered compatibility boundary

Independent source review agreed with corpus-first sequencing and required a
separate unsupported-versus-invalid taxonomy. It also identified valid scope
narrowing and noncritical extensions as cases a naive exact-match port would
incorrectly reject. These are included above.

The existing native `federation.rs::valid_canonical_name` checks ASCII label shape
but not ACE round-trip validity. Python ownership/scope validation explicitly
checks ACE decoding/re-encoding. For example, Python rejects `xn--a.example`;
source inspection shows it meets the native helper's current shape predicates.
That native helper therefore cannot be copied as a complete parity solution.
This observation is not a new native runtime reproduction or a claim of exploit.
No change to that existing route-admission code was made by this design task.

Keep controller, normal 3/5 and emergency 2/5 requirements unchanged. Neither
deliverable authenticates real governance/currentness, completes runtime
registration, changes stage counts or proves production readiness. Real timers,
rollback-resistant restart, event delivery and cleanup remain independent gates.


Follow-on: the bounded native test-only verification step is recorded in
`2026-11-14-native-signed-genesis-evidence.md`. Full semantic/runtime/governance
coverage remains outside that slice.
