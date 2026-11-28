# Composed trust admission: approved local offline slice

On 2026-11-26 the project owner explicitly approved the chat contract for this
fixture and minimal adapter, with focused local tests only. This is not general
Option C runtime approval. The historical proposal registry remains unchanged.

Base source: `840fef10d601f28336afde92f730b539eaf9154f`. The separate retained
`vectors/trust-admission-offline-v1/fixture.json` pins source and artifact hashes;
the base SHA alone does not identify these uncommitted additions.

## Contract and implementation

The explicit selector is `trust-admission-offline-v1`. The current bundle is
supplied fixture trust. Candidate canonical bytes are parsed without repair.
Envelope field 4 is SHA-256 of those exact bytes; field 6 is SHA-256 of
deterministic CBOR of the candidate scope; field 7 is candidate generation,
sequence and previous digest. The receiver requires `global-trust-v1`, existing
TRUST_BUNDLE_UPDATE and effect `replace`, with the pinned complete descriptor.
Existing verification checks governance 3/5, three organizations, purpose,
signatures, operation, capability and session context. All five roster keys must
also be ACTIVE in the separately supplied lifecycle snapshot.

The positive is generation 1, sequence 1 to 2. Scope and trust configuration
remain unchanged. Generation transitions, bootstrap and configuration/root
changes are excluded. Freshness and bundle-key lifecycle checks precede admission.
The supplied registry never comes from candidate-controlled data. Existing
`TrustBundleStore` handles continuity, idempotence and authenticated conflicts.
The adapter builds a new store and leaves the input store untouched, including
on exceptions; quarantine retains evidence without replacing the current bundle.
This is synchronous test composition, not a concurrent or durable store API.

Provenance, witness and transparency are three REQUIRED, explicitly simulated
obligations, each `satisfied-fixture`. Missing/unsatisfied obligations return
PENDING. These markers do not prove KAR provenance, inclusion, witness receipt,
or session authentication. Cryptographic decision and semantic decision are
reported separately, with before/after digests and fixture-state mutation.
Runtime authority and live flags remain false.

The builder reuses the existing public deterministic signing helper and verifier.
It signs the actual new candidate context; historical signatures cannot be reused
for different bytes. No keys or signatures are created for live use. The original
89 threshold literals and production guards are unchanged.

## Local verification

Working directory:
`C:/Users/bajra/Documents/Codex/2026-11-25/nbsr-connector-docker/publish-currentness`.
Use the existing Python environment; no downloads required.

- `python -m scripts.trust_admission_offline`: compare retained artifacts/source
  hashes with deterministic reconstruction and exercise the positive adapter.
- `python -m pytest -q -p no:cacheprovider tests/federation/test_trust_admission_offline.py`
- Neighbors: `tests/federation/test_trust_bundle.py` and
  `tests/federation/test_threshold_container_supplement.py`.

Initial RED: test collection failed because the new adapter module did not exist.
Initial GREEN: 14 focused cases passed before the final boundary additions.
The focused review found a missing-obligation-snapshot classification mismatch:
REJECT instead of the approved PENDING. A regression reproduced it and the
adapter now returns PENDING. The oversized-proof test initially caused pytest
setup errors with its automatic long parameter ID; explicit short IDs corrected
the test harness. No production parser limit was relaxed.

Final local Python 3.14 result: 56 passed across the adapter (26), trust-bundle
and threshold-container suites, in 1.48 seconds. The retained-artifact command,
scoped Ruff checks and diff whitespace check also passed. This does not establish
a Python version matrix or hosted CI pass. Focused review covered candidate
binding, independent supplied roster, all-member lifecycle checks, obligations,
copy-on-accept, idempotence and authenticated quarantine. Historical source and
threshold artifacts have no changes. No CI wiring, runtime, VM, Run2201, commit
or push is part of this change.
