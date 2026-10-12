# Normal revocation: signed checkpoint and witness composition

This parent-authorized local slice integrates existing verification contracts
instead of adding another status-only mock. `scripts/normal_revocation_witness_conformance.py`
checks an explicitly witness-required context alongside the approved local normal
revocation amendment. It does not introduce a universal witness requirement.

## Contract reused

- `nbsr/federation/cose.py`: exact transparency-log and witness COSE purpose,
  signature, signer identity, active lifecycle and validity checks.
- `nbsr/federation/transparency.py`: authenticated witness quorum with configured
  identities/control domains and replay contexts; checkpoint scope/digest/root
  binding, consistency proof, immediate predecessor and sequence continuity.
- The normal-revocation conformance evaluator: exact signed mode, policy, payload,
  scope, lineage, session/request binding and typed enforcement.

The integration authenticates the log's checkpoint and consistency proof, checks
continuity against a supplied signed previous checkpoint, and authenticates every
witness before quorum validation. The record's transparency reference must match
the checkpoint's log ID, digest and tree size, and its scope must match exactly.
Freshness is checked on every use, including an idempotent checkpoint. All remaining
fixture obligations still have to pass; a status string cannot replace the signed
witness evidence required by this entry point.

Two-of-three and three-of-five witness policies are exercised as explicit test
configuration, not inferred from normal mode or a sender's routine/high-impact
label. Only existing public deterministic test material is used: the log seed
`bytes(range(32))` and witness seeds `bytes([identity])*32` already used by the
transparency/witness tests, plus the existing normal threshold fixture material.
No key generation, new trust service, private provisioning or runtime caller is
introduced. All new executable code lives in `scripts/` and `tests/`.

## Validation and evidence

The missing-API RED result is retained. The initial 31 integration tests passed.
They cover both witness quorum profiles and all five normal enforcement modes,
bad log/witness/consistency signatures, wrong purpose, revoked log, absent prior
checkpoint/proof, insufficient/duplicate/common-control witnesses, replay mismatch,
unconfigured witnesses, invalid threshold type, stale/idempotent checkpoints,
sequence/predecessor rejection, unrelated record reference and pending obligations.
Final neighboring results, exact commands, hashes and omitted checks are in the
adjacent JSON manifest. Independent scoped security review found no blocker and
explicitly confirmed the evidence limits below; the reviewer did not rerun tests.

The python-protocol CI profile already selects the new test through `tests/federation`;
no workflow or command change is needed. Local checks are not hosted CI evidence.
Focused command:

```
python -m pytest -q -p no:cacheprovider tests/federation/test_normal_revocation_witness_integration.py tests/federation/test_normal_revocation_conformance.py tests/federation/test_witness_thresholds.py tests/federation/test_transparency.py tests/federation/test_threshold_container_supplement.py tests/federation/test_revocation.py
```

## Exact remaining gate

`ACCEPT` means this local composition passed under supplied fixture configuration.
It proves witness confirmation of the referenced checkpoint, **not inclusion of
the revocation record**. The test tree deliberately contains a different fixture
entry. The production inclusion verifier accepts a caller-supplied canonical leaf;
this slice neither chooses the governed revocation leaf representation nor claims
an inclusion proof. No field-39 inclusion-proof digest is vouched for here.

Accepted log/witness/control configuration, applicable policy, time and previous
checkpoint are still caller-supplied fixture inputs. Cryptographic validity alone
cannot establish that these are the currently governing inputs. The transient
continuity verifier is not a durable checkpoint floor or a replay journal.
`FederationStateRepository` retains local state/watermark files, but this composition
does not establish an authenticated latest floor after rollback of an entire
installation, nor map that store into connector authority. No filesystem/security
settings were changed to claim otherwise.

Next prerequisite: identify the approved source and exact authenticated binding for
the connector's current governing log/witness/membership configuration and applicable
transparency policy, the actual required record inclusion evidence, and the retained
checkpoint/revocation/replay floor at restart. Reuse the existing proof and state
verifiers once those inputs and their provenance are concrete. Do not invent a new
trust service, silently trust a local status marker, or label this full integration.
If that requires real provisioning or an unresolved semantic choice, obtain that
narrow decision before implementing runtime eligibility.

Controller, normal and emergency obligations remain intact. Runtime/live flags
remain false; Stage 3 is partial, stages 1–2 remain 2/10 complete. The final
comprehensive security audit before a real pilot remains required. No sockets,
installation, hosted CI, deployment, commit or push was performed.
