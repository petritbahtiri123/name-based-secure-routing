# Federation v0.1 Development Profile

**Task 1 status:** Ratified Development Profile implementation authority on
2026-08-07. These allocations and constants are frozen for
`nbsr-federation-dev-v1`; this is not a final Federation v0.1 wire freeze or a
production-profile allocation.

**Task 0 approval:** Approved at
`06c912cd307467623d7d4ab69bfb3305de253f4b`.
The Task 0 draft was proposed for human approval and is now accepted as the
authority for this bounded Task 1 ratification.
**WP8-NORMATIVE-SOURCE-01: CLOSED.** The exact 318,890-byte historical source
is repository-accessible at
`docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt` and matches the
previously recorded SHA-256. Human approval authorized Task 1's bounded
profile, registry, and baseline implementation. This profile is not a
permanently frozen Federation wire allocation; production-profile values remain
deferred.

The historical source is the detailed F1-F119/V1-V6 decision authority. The
condensed decision index is a cross-reference aid. This approved profile,
the machine registry, generated allocation tables, and later expressly approved
requiredness/vector decisions take precedence only for the exact values or
ambiguities they explicitly freeze or correct; summaries never silently
override the historical source.

## Base and identity

Required Core version is 2, baseline commit is `b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914`, extension ID/version is 1/1, profile is `nbsr-federation-dev-v1`, and static compatibility is `nbsr-static-trust-v1`. The cryptographic profile is tagged COSE Sign1, protected `alg=-8`, protected non-empty `kid`, empty external AAD, Ed25519 only, and SHA-256 only. The registry and baseline authorities are `registries/federation-v0.1-development.json` and `registries/core-v0.2-baseline-lock.json`.

The 110-artifact baseline lock is itself pinned by SHA-256
`21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef`.

The lock proves every non-amended artifact byte-identical to the baseline
commit. Its three named Task 0 exceptions are only the generic verifier README,
inventory implementation, and regression test required to separate WP4
exporter ownership; their post-amendment bytes are independently locked.

Operator ID binary/text mapping is `SHA-256("NBSR-FEDERATION-OPERATOR-ID-v1" || 0x00 || 0x01 || raw_32_byte_Ed25519_genesis_key)` and lowercase Bech32m HRP `nbsr` over those 32 bytes. Uppercase, mixed case, wrong HRP/checksum/length, and wrong discriminator fail.

Continuity-preserving recovery retains the Operator ID with a strictly higher identity generation. Lineage-breaking recovery terminally tombstones the old Operator ID and requires a new genesis commitment and new Operator ID.

## Retention, bounds, and timing

Direction-document bounds and thresholds remain proposed. Replay-state retention minimum: 86,400 seconds. Terminal tombstones are permanent, non-expiring, and recoverable after garbage collection, restart, compaction, backup restoration, and fresh-node synchronization.

Timing values are skew 300 seconds; key lifetime 30 days; overlap 1 hour through 24 hours; checkpoint interval 60 seconds and emergency deadline 30 seconds; trust freshness 300 seconds and degraded staleness 900 seconds; cache ceiling 300 seconds; missing evidence 30 seconds; quarantine reevaluation 300 seconds; drain 30 seconds; static warning 15 minutes and hard expiry 60 minutes without automatic reset.

## Operator lifecycle and recovery stage

Top-level lifecycle values are exactly `APPLIED`, `VERIFICATION_PENDING`,
`VERIFIED`, `PROVISIONAL`, `ACTIVE`, `SUSPENDED`, `QUARANTINED`, `RECOVERY`,
`RETIRED`, `TERMINALLY_REVOKED`, and `REJECTED`, in that numeric allocation
order. The numbers are identifiers, not a lifecycle rank. Monotonicity applies
to identity generation and record sequence, with valid continuity; same-state
updates require a higher sequence.
`RESTRICTED` is only a decision/outage behavior. `REJECTED` creates no
Federation authority. `PROVISIONAL` creates only explicit bounded pilot
authority. Invalid, skipped, rollback, or unknown transitions reject
fail-closed without mutation.

The exact transition graph is: `APPLIED -> {VERIFICATION_PENDING, REJECTED}`;
`VERIFICATION_PENDING -> {VERIFIED, REJECTED}`; `VERIFIED -> {PROVISIONAL,
ACTIVE, REJECTED}`; `PROVISIONAL -> {ACTIVE, SUSPENDED, QUARANTINED, RECOVERY,
RETIRED, TERMINALLY_REVOKED}`; `ACTIVE -> {SUSPENDED, QUARANTINED, RECOVERY,
RETIRED, TERMINALLY_REVOKED}`; `SUSPENDED -> {ACTIVE, QUARANTINED, RECOVERY,
RETIRED, TERMINALLY_REVOKED}`; `QUARANTINED -> {RECOVERY, RETIRED,
TERMINALLY_REVOKED}`; and `RECOVERY -> {ACTIVE, RETIRED,
TERMINALLY_REVOKED}`. `RETIRED`, `TERMINALLY_REVOKED`, and `REJECTED` have no
outgoing transitions.

`recovery_stage` is required exactly for lifecycle `RECOVERY` and forbidden in
every other lifecycle. Its only wire values are `RECOVERY_PENDING`,
`RECOVERY_VERIFIED`, and `REENTRY_RESTRICTED`. Normal `ACTIVE` follows
`REENTRY_RESTRICTED` only after peer synchronization, compatible checkpoints,
current revocations, monitoring completion, and readiness approval. The seven
workflow labels retained in the machine source are explicitly local and never
wire or signed-object values.
Recovery stages advance exactly `RECOVERY_PENDING -> RECOVERY_VERIFIED ->
REENTRY_RESTRICTED -> ACTIVE`; skipping or rollback rejects
`ERR_CONTINUITY` without mutation.

## Federation semantic messages

The 58-message count is derived from the complete semantic registry, not a
target. Capability agreement occurs after exact Core v2 selection and peer
authentication and never negotiates Core version lists. Discovery, authority
retrieval, bundle synchronization, transparency, bilateral authorization,
push/pull revocation, conflict evidence, lifecycle/recovery notices, explicit
object publication/update acknowledgements, conflict resolution, and appeal
remain distinct. Sender/receiver roles, class, replay context, mutation,
idempotency, allowed protocol state, object association, authority effect, and
purpose are normative in the machine registry and generated allocation table.
ACK and notice delivery never creates authority unless the named signed-object
validation and state transition independently succeeds.

## Ratified registry tables

The exact ordered names and numeric values are the generated tables in
`wp8-federation-v0.1-registry-allocation.md`, derived from
`registries/federation-v0.1-development.json`. The Python `IntEnum` tables in
`nbsr/federation/registry.py` reproduce those literals without loading or
deriving them at runtime.

| Registry | Ratified entries | Allocated values |
|---|---:|---|
| Extension IDs | 1 | 1 |
| Capability IDs | 5 | 1..5 |
| Object types | 18 | 1..18 |
| Message types | 58 | 16384..16441 |
| Reason codes | 32 | 0..31 |
| Key purposes | 14 | 1..14 |
| Key lifecycles | 5 | 1..5 |
| Operator lifecycles | 11 | 1..11 |
| Recovery stages | 3 | 1..3 |
| Result types | 8 | 1..8 |
| Decision outcomes | 5 | 1..5 |
| Enforcement modes | 5 | 0..4 |
| Authority classes | 14 | 1..14 |

All remaining ranges shown in the generated allocation document remain
reserved. Unknown and reserved values fail closed. These are approved
Development Profile allocations, not permanent Federation wire allocations.

## Cryptographic freeze gate

- Merkle leaf domain separator: `0x00`.
- Merkle node domain separator: `0x01`.
- Empty-tree root: `SHA-256("")`.
- Leaf/node hashes: `SHA-256(0x00 || canonical_leaf)` and `SHA-256(0x01 || left || right)`.
- Genesis checkpoint: signed `TransparencyCheckpoint`, tree size 0, empty-tree root, generation 1, sequence 1, absent predecessor, configured log ID, and timestamp 0 only in deterministic vectors.
- Privacy commitment: HMAC-SHA-256 using a uniformly generated single-use 32-byte opening key over `"NBSR-FEDERATION-PRIVACY-COMMITMENT-v1" || 0x00 || canonical_value`.
- Salt/keyed-commitment and opening rules: no separate public salt; authorized opening reveals the exact key and canonical value for recomputation. Keys are never logged or reused, and opening is audited.

Task 4 cannot invent or replace these values before GREEN. A change requires a named blocking profile amendment, literal vectors, and approval.

## Genesis/update requiredness

The generic rule is: genesis is generation 1/sequence 1 with absent
predecessor; same-generation update increments sequence and requires the
immediately accepted canonical predecessor digest; new generation begins at
sequence 1 and requires the prior terminal/transition digest plus recovery or
transfer evidence. Object-specific requiredness is explicitly deferred by the
named blocking decision `WP8-SCHEMA-REQUIREDNESS-01`. It blocks Tasks 2-6 until
an object-by-object matrix and literal schema vectors are approved. Task 1
registry modules may proceed; no object codec or validator may proceed.

## Signer-authority matrix and COSE kid binding

| Object family | Signer authority / key purpose |
|---|---|
| Operator registry | development registrar / registry signing plus witnesses |
| Key authorization | identity root / identity root, or approved recovery / recovery |
| Ownership and delegation | name owner / name ownership, then scoped owner or delegate / delegation |
| Trust bundle | scoped federation authority / trust bundle |
| Checkpoint and proofs | transparency log / transparency log |
| Witness statement | independent witness / witness |
| Endpoint | operator endpoint or scoped delegate / endpoint discovery |
| Authority proof and context | exact source and destination / federation authorization |
| Revocation | target controller 1-of-1, normal authority 3-of-5, or deny-only emergency authority 2-of-5 / revocation |
| Lifecycle and recovery | registry plus operator recovery / recovery |
| Conflict and appeal | conflict-resolution or appeal authority / governance |

The exact signer-authority matrix is machine-readable in the registry source;
its signer sets, purposes, thresholds, and combination rules override prose
abbreviations in this table. Every COSE `kid` is 1..64 opaque bytes and resolves
to exactly one accepted operator, public key, key purpose, authority class,
validity interval, lifecycle, generation, and sequence. Ambiguous or
cross-purpose resolution fails. Root replacement requires 2-of-3 recovery
approvals, 1-of-1 development registry approval, and 2-of-3 witnesses. A
compromised/terminal root cannot replace itself; absent continuity proof forces
lineage-breaking recovery.

Every registry is closed. Unknown, unallocated, or reserved values return
`REJECT/ERR_UNSUPPORTED_CRITICAL` with `state_changed=false` before mutation.
Privacy opening requires 4-of-5 conflict-resolution authorities using the
governance purpose plus 3-of-5 witnesses. The signed single-use opening request
binds commitment, object digest, request ID, recipient Operator ID, and expiry;
authority or binding failure is `REJECT/ERR_AUTHORITY`, and every attempt is
audited.

`TypedRevocationRecord` carries a signed `revocation_authority_mode` selecting
exactly one of `target-controller`, `normal-threshold`, or
`emergency-deny-only`; validators evaluate only the selected alternative.
Unknown modes fail `REJECT/ERR_UNSUPPORTED_CRITICAL`. Signature counts from an
unselected alternative cannot make a record valid or ambiguous.

## State and error rules

Idempotency: equal version/equal digest is `ACCEPT` without mutation. Lower version is `REJECT/ERR_ROLLBACK`. Equivocation: equal version/different digest retains both branches and is `QUARANTINE/ERR_EQUIVOCATION`. Higher versions mutate only after complete validation.

Error precedence is the numeric order in the machine registry: resource, parse, canonical/critical, cryptography/signature, identity/purpose/lifecycle, schema/version, authority/scope/expansion, rollback/replay/equivocation/continuity, revocation/terminal, transparency/checkpoint/split-view/witness, freshness/evidence/outage, downgrade, local policy, recovery, internal.

## Staged vector-first execution

1. Registry and schema literal vectors.
2. Python codecs and object validation.
3. Approved stateful scenario manifests with literal expected outcomes.
4. Python state-machine implementation against those manifests.
5. Complete generated vector package.
6. Node and Go independent verification.

Specification-authored literals are not derived from Python. Python may generate the complete byte package only after literals and outcomes are frozen.

## Claims and non-claims

Shared-transport evidence is not independent-runtime evidence. Object/vector, control-plane, shared-transport, independent-runtime, and independent end-to-end claims remain separate.

No federation runtime is implemented by Task 0. There is no live federation, public/global authority, production registry/log/witness/governance/HSM custody, Go runtime, independent control-plane or end-to-end interoperability, production readiness, origin anonymity, DDoS elimination, or complete partition tolerance.
