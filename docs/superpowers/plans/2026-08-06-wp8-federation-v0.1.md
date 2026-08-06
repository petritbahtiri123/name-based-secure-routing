# WP8 Federation v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze and implement a deterministic Federation v0.1 Development Profile over the ratified Core v0.2 candidate, prove it with cross-language vectors, then progressively establish independent control-plane and shared-transport interoperability evidence.

**Architecture:** Federation is a separately versioned control-plane extension. Python defines the reference object/state semantics and vectors, Node independently verifies bytes and proofs, Go implements clean-room federation semantics, and Rust consumes only verified federation authorization at the existing transport boundary. Frozen Core v0.1 objects and approved Core v0.2 artifacts remain byte-identical.

**Tech Stack:** Python 3.12+, deterministic CBOR, COSE Sign1/Ed25519/SHA-256, Node.js 24 built-ins, Go 1.26.x (validated with 1.26.5), Rust/Quinn/rustls, pytest, Ruff.

## Global Constraints

- Work only on the explicitly approved feature branch; never switch, merge, rebase, push, or modify `main` without separate authorization.
- Preserve all frozen Core v0.1 D1-D6 objects, numeric registries, COSE profile, wrappers, state transitions, and vectors byte-for-byte.
- Pin Core v0.2 to repository commit `b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914` and manifest SHA-256 `d4cc06347be4ce7d4f118c004130a1ac7ab9a7d5fda6de3354fbb26bf72a3eeb` before allocating Federation values.
- Federation Extension ID is `1`, extension version is `1`, and required Core version is `2` only after Task 1 ratification tests pass.
- No runtime consumes an unfrozen object, message, field, error, capability, signature input, or authority matrix.
- Every accepted authority change is canonical, signed, scope-bound, monotonic, hash-linked where applicable, bounded, atomic, idempotent, revocation-aware, and privacy-safe.
- Unknown critical behavior, downgrade, ambiguity, rollback, equivocation, split view, invalid recovery, and resource excess fail closed with no unauthorized state mutation.
- Static trust is a separate pre-authorized profile and never an automatic federation fallback.
- Origin Endpoints, subscriber identifiers, private topology, private service inventory, credentials, private keys, payloads, exporter values, and raw grant bytes never enter public federation objects, logs, reports, errors, or fixtures.
- Claims remain tiered: vector agreement, object interoperability, control-plane interoperability, shared-transport interoperability, and independent end-to-end interoperability are never conflated.
- Every behavior change uses RED-GREEN TDD and every confirmed review issue is reproduced with a failing regression before its fix.

### Task 0 approval gate

**WP8-NORMATIVE-SOURCE-01: CLOSED.** The exact detailed historical source is
checked in at
`docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt`, with provenance,
length, and digest locked by
`docs/protocol/registries/wp8-planning-sources.json`. It is a permitted
clean-room input. Task 1 may begin after human approval. Literal allocations
come only from `docs/protocol/registries/federation-v0.1-development.json`;
Task 1 RED tests must copy those approved names and numbers. Replay-state
retention minimum: 86,400 seconds. Terminal tombstones are permanent across
garbage collection, restart, compaction, backup restoration, and fresh-node
synchronization. Continuity-preserving recovery retains the Operator ID at
higher generation; lineage-breaking recovery tombstones it and requires a new
ID.

Core validation uses the following complete sequence. The generic verifier
excludes only the independently inventoried `wp4-exporter/` subtree:

```powershell
python scripts/generate_core_v02_vectors.py --check vectors/core-v0.2
node tools/core-v02-node-verifier/verify.mjs vectors/core-v0.2
node scripts/verify_wp4_exporter_vectors.mjs vectors/core-v0.2/wp4-exporter
```

The corrected order is registry and schema literal vectors; Python codecs and object validation; stateful scenario manifests with literal expected outcomes; Python state-machine implementation; complete generated vectors; Node and Go independent verification. No federation runtime is implemented by Task 0.

---

### Task 1: Ratify Core v0.2 and freeze the Development Profile registries

**Authorization boundary:** After human approval, Task 1 may create only
Development Profile constants, registry enums/tables, baseline immutability
enforcement, and their literal RED/GREEN tests. Task 1 MUST NOT implement object
codecs or validators. `WP8-SCHEMA-REQUIREDNESS-01` remains blocking for Tasks
2-6 and all schema codec work that depends on the unresolved object-by-object
requiredness matrix.

**Files:**
- Create: `docs/protocol/federation-v0.1-development-profile.md`
- Create: `nbsr/federation/__init__.py`
- Create: `nbsr/federation/profile.py`
- Create: `nbsr/federation/registry.py`
- Create: `tests/federation/test_profile.py`
- Create: `tests/federation/test_registry.py`
- Create: `tests/federation/test_baseline_immutability.py`

**Interfaces:**
- Produces `FederationProfile`, `ObjectType`, `MessageType`, `ReasonCode`, `DecisionOutcome`, `EnforcementMode`, `KeyPurpose`, `KeyLifecycle`, and `OperatorLifecycle`.
- Produces `assert_core_baseline(root: Path) -> None` and canonical registry tables consumed by every later task.

- [ ] **Step 1: Write baseline and registry tests before creating federation modules**

```python
def test_core_v02_baseline_is_exact() -> None:
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == (
        "d4cc06347be4ce7d4f118c004130a1ac7ab9a7d5fda6de3354fbb26bf72a3eeb"
    )

def test_extension_registry_is_closed_and_collision_free() -> None:
    assert FederationProfile.extension_id == 1
    assert FederationProfile.extension_version == 1
    assert FederationProfile.required_core_version == 2
    assert [(item.name, item.value) for item in ObjectType] == EXPECTED_OBJECT_TYPES
    assert [(item.name, item.value) for item in MessageType] == EXPECTED_MESSAGE_TYPES
```

`EXPECTED_OBJECT_TYPES` and `EXPECTED_MESSAGE_TYPES` are literal tuples in the
RED test, containing all object and semantically derived message name/value pairs copied from the approved
machine source. The existing Task 0 registry regression contains those exact
literals and is the copying authority. RED tests must not derive a range or
compute expectations from the implementation or JSON loader. Apply the same
literal rule to every other approved registry.

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/federation/test_profile.py tests/federation/test_registry.py tests/federation/test_baseline_immutability.py`

Expected: collection fails because `nbsr.federation` does not exist.

- [ ] **Step 3: Implement exact immutable profile values**

```python
@dataclass(frozen=True, slots=True)
class FederationProfile:
    extension_id: ClassVar[int] = 1
    extension_version: ClassVar[int] = 1
    required_core_version: ClassVar[int] = 2
    name: ClassVar[str] = "nbsr-federation-dev-v1"
    static_profile: ClassVar[str] = "nbsr-static-trust-v1"
    max_object_bytes: ClassVar[int] = 65_536
    max_delegation_depth: ClassVar[int] = 8
    max_chain_objects: ClassVar[int] = 16
    max_graph_nodes: ClassVar[int] = 256
    max_merkle_path: ClassVar[int] = 64
```

Allocate the 18 object values in the exact order in
`docs/protocol/wp8-federation-v0.1-direction.md`; allocate every semantic
message in the exact approved Task 0 order and values without a target count;
allocate the exact approved reason,
purpose, lifecycle, recovery, result, enforcement, authority, extension, and
capability values. “F105 family order” alone is not an allocation. Document
every table in the Development Profile.

- [ ] **Step 4: Verify GREEN and immutable Core artifacts**

Run: `python -m pytest -q tests/federation/test_profile.py tests/federation/test_registry.py tests/federation/test_baseline_immutability.py`

Run: `python scripts/generate_core_v02_vectors.py --check vectors/core-v0.2`

Run: `python scripts/generate_core_v02_baseline_lock.py --check`

Run: `node tools/core-v02-node-verifier/verify.mjs vectors/core-v0.2`

Run: `node scripts/verify_wp4_exporter_vectors.mjs vectors/core-v0.2/wp4-exporter`

- [ ] **Step 5: Commit the ratification tranche**

Stage only the seven Task 1 paths. Inspect `git diff --cached --name-only`,
`git diff --cached --stat`, and `git diff --cached --check`, then commit:

`docs(wp8): freeze federation development profile`

### Task 2: Operator identity and purpose-bound key authorization

**Vector-first gate for Tasks 2-5:** Before each Python codec/object validator
is written, its closed schema and hand-authored registry/schema literal vectors
(canonical valid form, each requiredness boundary, unknown critical field,
wrong type, over-limit form, and signature-purpose case) must be reviewed and
checked in. Python tests consume those literals; Python does not generate their
expected bytes or outcomes. Task 7 later assembles these literals and generated
coverage into the complete package.

`WP8-SCHEMA-REQUIREDNESS-01` is a named blocking decision and blocks Tasks 2-6: they cannot
begin until the object-by-object genesis/update requiredness matrix and literal
schema vectors are approved. It does not block Task 1's profile, registry, and
baseline-only surface, but it forbids object codecs and validators.

**Files:**
- Create: `nbsr/federation/fields.py`
- Create: `nbsr/federation/identity.py`
- Create: `nbsr/federation/cose.py`
- Create: `tests/federation/test_operator_id.py`
- Create: `tests/federation/test_key_authorization.py`
- Create: `tests/federation/test_cose_authority.py`

**Interfaces:**
- Produces `OperatorId.from_genesis_key(raw_key: bytes)`, `.from_text(text: str)`, `.binary`, and `.text`.
- Produces frozen `OperatorRegistryRecord` and `KeyAuthorizationRecord` with `canonical_bytes()`, `digest`, `require_valid_at(now)`, and `require_newer_than(current)`.
- Produces `verify_federation_sign1(message, authority, expected_object_type, now)` that enforces Ed25519, protected `kid`, exact key purpose, object class, operator, validity, lifecycle, generation, sequence, and revocation.

- [ ] **Step 1: Write Operator ID RED tests**

Use the fixed genesis public key `bytes(range(32))`. Assert one hand-recorded
32-byte digest and one hand-recorded 63-character lowercase Bech32m string,
round-trip equality, mixed-case rejection, checksum rejection, wrong-HRP
rejection, wrong algorithm discriminator rejection, and stability across
operational-key rotation.

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/federation/test_operator_id.py`

Expected: imports fail because `identity.py` is absent.

- [ ] **Step 3: Implement exact derivation and parser**

```python
OPERATOR_ID_DOMAIN = b"NBSR-FEDERATION-OPERATOR-ID-v1\x00"
ED25519_GENESIS_KEY = b"\x01"

digest = sha256(OPERATOR_ID_DOMAIN + ED25519_GENESIS_KEY + raw_key).digest()
```

Implement Bech32m locally with HRP `nbsr`, no dependency, strict lowercase,
exact 32-byte payload, and checksum verification before exposing an identity.

- [ ] **Step 4: Add Key Authorization RED tests**

Test genesis/update requiredness, root signature, exact operator binding,
single purpose, validity, predecessor continuity, generation/sequence,
next/active/retiring/retired/revoked transitions, cross-purpose signature,
compromised signer, recovery generation, terminal key-ID non-reuse, and
unknown critical extensions.

- [ ] **Step 5: Implement closed objects and authority verification**

Reuse `nbsr.protocol.cbor` and cryptographic primitives, but use new federation
schemas and registries. Do not change `nbsr.protocol.models`, `registry`, or
`cose`.

- [ ] **Step 6: Verify and commit**

Run all three Task 2 files, Core protocol tests, Ruff, and `git diff --check`.
Commit: `feat(wp8): bind operator identity and key authority`.

### Task 3: Name ownership and bounded delegation chains

**Files:**
- Create: `nbsr/federation/ownership.py`
- Create: `nbsr/federation/delegation.py`
- Create: `tests/federation/test_ownership.py`
- Create: `tests/federation/test_delegation.py`
- Create: `tests/federation/test_delegation_graph.py`

**Interfaces:**
- Produces `NameOwnershipRecord`, `DelegationScope`, `DelegationRecord`, `AuthorityClass`, and `DelegationVerifier.verify(chain, request, now)`.
- `DelegationScope.intersect(child)` returns only equal or narrower name/service/tenant/region/protocol/port/action authority.

- [ ] **Step 1: Write chain RED tests**

Test one ownership root, direct delegation, depth-eight valid chain, depth-nine
rejection, sibling isolation, partial port/protocol/service scope, prohibited
sub-delegation, missing scope, loop, repeated node, broken parent digest,
wrong authority class, stale/equal-conflicting/higher versions, expiry,
revocation, transfer, and recovery generation.

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/federation/test_ownership.py tests/federation/test_delegation.py tests/federation/test_delegation_graph.py`

- [ ] **Step 3: Implement immutable scope algebra and bounded graph walk**

Use iterative traversal with explicit `max_chain_objects=16`,
`max_delegation_depth=8`, `max_graph_nodes=256`, a visited digest set, and
fail-closed class/scope checks before any accepted-state mutation.

- [ ] **Step 4: Verify and commit**

Run Task 2-3 tests plus existing name registry/name node tests. Commit:
`feat(wp8): verify ownership and delegation chains`.

### Task 4: Trust bundles, transparency proofs, and witnesses

**Files:**
- Create: `nbsr/federation/trust.py`
- Create: `nbsr/federation/transparency.py`
- Create: `tests/federation/test_trust_bundle.py`
- Create: `tests/federation/test_merkle.py`
- Create: `tests/federation/test_transparency.py`
- Create: `tests/federation/test_witness_thresholds.py`

**Interfaces:**
- Produces `FederationTrustBundle`, `TrustBundleStore`,
  `TransparencyCheckpoint`, `InclusionProof`, `ConsistencyProof`,
  `WitnessStatement`, and `TransparencyVerifier`.
- Merkle leaf hash is `SHA-256(0x00 || canonical_leaf)`; node hash is
  `SHA-256(0x01 || left || right)`. Empty-tree behavior and genesis checkpoint
  are explicitly encoded in the Development Profile before GREEN.

- [ ] **Step 1: Write RED vectors as literal fixtures**

Cover known leaf/root pairs, inclusion, consistency, wrong order, excessive
path, same-size different-root split view, stale checkpoint, bad witness,
same-organization witness diversity failure, 2-of-3 ordinary threshold,
3-of-5 high-risk threshold, bundle genesis/update, previous digest, restrictive
composition, lifecycle rotation, early activation, retirement, revocation,
rollback, equivocation, freshness, and maximum staleness.

- [ ] **Step 2: Run RED, implement minimal deterministic tree/proof logic, and rerun GREEN**

Run the four Task 4 test files. Keep proof verification iterative and bounded;
retain conflicting evidence instead of choosing first-seen state.

- [ ] **Step 3: Commit**

Commit: `feat(wp8): verify trust bundles and transparency`.

### Task 5: Discovery, bilateral authorization, revocation, and lifecycle

**Files:**
- Create: `nbsr/federation/discovery.py`
- Create: `nbsr/federation/authorization.py`
- Create: `nbsr/federation/revocation.py`
- Create: `nbsr/federation/lifecycle.py`
- Create: `tests/federation/test_discovery.py`
- Create: `tests/federation/test_authorization.py`
- Create: `tests/federation/test_revocation.py`
- Create: `tests/federation/test_lifecycle.py`

**Interfaces:**
- Produces `OperatorEndpointRecord`, `FederationAuthorityProof`,
  `FederationAuthorizationContext`, `TypedRevocationRecord`,
  `ConflictEvidence`, `OperatorLifecycleRecord`, `RecoveryTransitionRecord`,
  `ConflictResolutionRecord`, and `AppealDecisionRecord`.
- Produces source and destination authorization methods that independently
  return `FederationResult` and never return an Origin Endpoint.

- [ ] **Step 1: Write discovery/admission RED tests**

Test candidate-only DNS/HTTPS/static discovery, exact operator/transport-key
binding, anti-enumeration exact-match lookup, no Origin Endpoint output,
source-before-destination validation, exact service/operator/proof/bundle/
checkpoint/policy binding, incompatible checkpoint synchronization, missing
proof pending timeout, no automatic static downgrade, and direct-origin
fallback rejection.

- [ ] **Step 2: Write revocation/lifecycle RED tests**

Cover every object target class, dependency-selective invalidation, terminal
tombstones, known compromise during outage, APPLIED through TERMINALLY_REVOKED
states, RECOVERY-stage requiredness, quarantine, staged re-entry, recovery
thresholds, conflict resolution, appeal non-reactivation, and idempotent retry.

- [ ] **Step 3: Implement and verify**

Run Task 5 tests plus WP7 admission/privacy tests. Commit:
`feat(wp8): enforce federation authorization lifecycle`.

### Task 6: Immutable state machine, durable watermarks, and outage policy

**State-vector gate:** Before `FederationState.apply` is implemented, check in
the approved stateful scenario manifests with literal expected outcomes,
reasons, enforcement modes, mutation flags, dependency effects, and state
digests. Task 6 implements against those manifests. Task 7 packages them and
may add reference-generated coverage, clearly labelled as generated rather
than specification-authored.

**Files:**
- Create: `nbsr/federation/state.py`
- Create: `nbsr/federation/store.py`
- Create: `tests/federation/test_state_machine.py`
- Create: `tests/federation/test_store.py`
- Create: `tests/federation/test_outage.py`
- Create: `tests/federation/test_error_precedence.py`

**Interfaces:**
- Produces `FederationState.apply(event, now) -> (FederationState, FederationResult)`.
- Produces a bounded canonical snapshot and `FederationStateRepository` using
  descriptor-bound bounded reads and existing private atomic-write helpers.

- [ ] **Step 1: Write RED tests for all outcome classes and exact precedence**

Assert literal outcome/reason/enforcement/state-digest tuples for malformed,
over-limit, noncanonical, bad signature, wrong purpose, schema mismatch, scope,
rollback, equivocation, revocation, proof, staleness, and policy failures.

- [ ] **Step 2: Write persistence/outage RED tests**

Cover `limit+1` reads, regular-file/no-symlink checks, corruption, partial
write, rollback after restart, terminal non-resurrection, fresh-node current
state proof, primary outage/alternate success, LKG freshness, restricted mode,
maximum staleness, known compromise, static-recovery activation and hard
expiry, and reconciliation.

- [ ] **Step 3: Implement immutable transitions and bounded repository**

Rejected input returns the identical prior state object. Equal version/equal
digest returns `state_changed=false`; equal version/different digest preserves
both branches in quarantine evidence; higher state commits only after complete
preflight.

- [ ] **Step 4: Verify and commit**

Commit: `feat(wp8): persist deterministic federation state`.

### Task 7: Deterministic Federation v0.1 vector package

Task 7 is package completion, not the first appearance of vectors. It combines
the pre-codec registry/schema literals, the pre-state-machine literal scenario
manifests, and explicitly labelled reference-generated expansion cases. The
manifest records provenance for each artifact as `specification-authored` or
`reference-generated`.

**Files:**
- Create: `scripts/generate_federation_v01_vectors.py`
- Create: `scripts/federation_v01_vectors/`
- Create: `vectors/federation-v0.1/README.md`
- Create: `vectors/federation-v0.1/manifest.json`
- Create: `tests/federation/test_vectors.py`

**Interfaces:**
- Generator supports `--check vectors/federation-v0.1` and never rewrites on
  mismatch in check mode.
- Manifest records exact artifact paths, lengths, SHA-256, dependencies,
  applicability classes, fixed time, resource bounds, outcome, reason,
  enforcement, state digest, mutation flag, and emitted artifacts.

- [ ] **Step 1: Write generator contract RED tests**

Test closed manifest, sorted unique IDs, safe relative paths, complete artifact
inventory, no unlisted files, deterministic rerun, fixed test-only keys, and
valid/invalid/rollback/equivocation/rotation/split-view/revocation/outage/
resource cases for every applicable object.

- [ ] **Step 2: Run RED and implement deterministic generation**

Use only fixed inputs. Generate into a temporary directory, compare complete
inventories and bytes, then check in the package once stable.

- [ ] **Step 3: Verify and commit**

Run generator twice, `--check`, all federation tests, and Core vector
immutability checks. Commit: `test(wp8): publish federation conformance vectors`.

### Task 8: Independent Node and clean-room Go object/control-plane verification

**Files:**
- Create: `tools/federation-v01-node-verifier/`
- Create: `implementations/go-federation/README.md`
- Create: `implementations/go-federation/go.mod`
- Create: `implementations/go-federation/internal/`
- Create: `implementations/go-federation/cmd/nbsr-federation/`
- Create: `implementations/go-federation/testdata/`
- Create: `evidence/wp8-independent-go/implementation-manifest.json`

**Interfaces:**
- Node verifies manifest, canonical bytes, COSE, Operator ID, Merkle proofs,
  artifact outcomes, and never reads private seeds or writes vectors.
- Go parses, emits, signs, verifies, and applies the same objects/stateful flows
  without importing or executing reference-runtime code.

- [ ] **Step 1: Create and approve a clean-room sub-plan**

The implementer receives only normative WP8 docs, including the permitted
clean-room input
`docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt`, external
standards, registries, vectors, public test keys, and expected outcomes. Record
permitted inputs and prohibited source paths in the evidence manifest before
coding. No unavailable local file, conversation, or absent external document is
a prerequisite.

- [ ] **Step 2: TDD the Node verifier**

Start with a failing package-boundary test, then independently implement
bounded CBOR/COSE/Bech32m/Merkle/object checks with Node built-ins. Verify every
static vector and exact symbolic outcome.

- [ ] **Step 3: TDD Go from public artifacts only**

Pin Go `1.26` in `go.mod` and record the validated `go1.26.5 windows/amd64`
toolchain in evidence. Implement bounded canonical encoding, cryptography,
objects, state machine, and CLI;
reverse artifact generation so Python/Node consume original Go bytes.

- [ ] **Step 4: Verify isolation and commit in separate tranches**

Audit imports, subprocess/network calls, generated-code provenance, dependency
graph, vector writes, and reference-source access. Commit Node and Go work
separately after their independent reviews.

### Task 9: Federation capability agreement and Rust transport binding

**Files:**
- Create: `crates/nbsr-transport/src/federation.rs`
- Create: `crates/nbsr-transport/tests/federation.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Modify: `crates/nbsr-transport/src/admission.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/core_v02.rs`

**Interfaces:**
- Consumes a verified `FederationAuthorizationContext` canonical digest and
  exact capability agreement bound to Core version 2 and the authenticated
  Transport Session.
- Does not parse registry, governance, or Origin Endpoint data inside stream or
  datagram gates.

- [ ] **Step 1: Freeze the exact transcript/extension-container binding in a reviewed decision**

The decision specifies byte layout, domain label, session/route IDs,
source/destination Operator IDs, context digest, nonces, extension ID/version,
critical capability set, replay scope, and failure behavior without modifying
the frozen RouteGrant.

- [ ] **Step 2: Write Rust RED tests**

Cover capability absence/version mismatch/stripping, wrong operators/context,
replay, stale/revoked/quarantined dependencies, static downgrade, valid
role-reversed source/destination admission, existing WP4 exporter binding,
drain, and selective invalidation.

- [ ] **Step 3: Implement minimal binding and verify**

Run Rustfmt, Clippy `--all-targets -- -D warnings`, all Rust tests, Python/Node/
Go vectors, and shared-transport live scenarios. Commit:
`feat(wp8): bind federation authority to transport`.

### Task 10: Review closure, evidence, protocol draft, and authoritative status

**Files:**
- Create: `docs/protocol/federation-v0.1-wire.md`
- Create: `docs/protocol/wp8-federation-v0.1-decision.md`
- Create: `docs/internet-drafts/draft-nbsr-federation-00.md`
- Create: `tests/federation/test_runtime_documentation.py`
- Modify: `docs/protocol/status.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

**Interfaces:**
- Documents exact implemented schemas/registries/flows, validation counts,
  cross-language evidence, unsupported surfaces, and claim tier.
- Draft is an implementation-derived working draft, not claimed IETF consensus.

- [ ] **Step 1: Dispatch independent correctness, security, privacy, and clean-room reviews**

Review the complete WP8 diff and evidence. Reproduce every candidate locally;
fix confirmed issues only through failing regression tests and scoped commits.

- [ ] **Step 2: Run the complete validation matrix**

Run full Python tests/Ruff/format/pip, Core v0.1/v0.2 and WP4/WP6/WP7 checks,
Federation vector generation/checks, Node verifiers, Go tests/vet/build,
Rustfmt/Clippy/tests, Compose/OPA when available, live bounded federation
scenarios, privacy/secret/artifact scans, and `git diff --check`.

- [ ] **Step 3: Write documentation RED tests, update evidence, and rerun validation**

Tests require every authoritative document independently, exact counts,
baseline digests, review disposition, claim tier, and all non-claims. Commit:
`docs(wp8): record federation evidence`.

- [ ] **Step 4: Verify final Git invariants**

Confirm exact repository, branch, HEAD, clean tree/index, upstream divergence,
unchanged main refs, explicit staged paths, ignored secrets/temp artifacts, and
that no merge, rebase, switch, or push occurred.

## Execution handoff

Start with Task 1 only. Do not parallelize tasks that allocate or consume the
same registries. Tasks 2-6 are sequential because each consumes the prior
authority model. Task 7 follows schema/state freeze. Node and Go implementation
may run as separately reviewed subplans only after Task 7 vectors are stable.
Rust integration starts only after Python/Node/Go byte and state agreement.

Recommended execution mode: subagent-driven development, one fresh implementer
and one independent reviewer per task, with security and correctness reviews
after Tasks 4, 7, 8, and 9.
