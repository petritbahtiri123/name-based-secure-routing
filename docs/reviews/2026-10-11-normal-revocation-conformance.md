<!-- Publication derivative; original SHA-256 a12af0fa4982cd7ded5893308ed687d6bb398d2f8e813438ced567f0793550dc. Personal attribution replaced by role label. Historical approval and result claims refer to the original local artifact, not a new action. -->

# Normal revocation local conformance amendment

project owner approved proposal revision 2 for local conformance implementation only.
The separate versioned amendment is
`docs/protocol/registries/federation-v0.1-normal-revocation-conformance-v1.json`.
It pins both historical parent registries by SHA-256; neither parent is changed.
Historical 89 literal fixtures remain unchanged. This does not freeze or activate
runtime packaging or change a production source-authority overlay.

`normal-revocation-v1`, version 1, group `normal-revocation` maps signed mode 2,
object 13, FEDERATION_AUTHORITY class 4, REVOCATION purpose 12, 3-of-5,
REVOCATION_PUSH 16407 and effect deny. Existing Option C descriptor digest and
signature contexts are reused. Deny prohibits authority expansion; it does not
replace exact normal typed enforcement with emergency's deny-new/300-second rule.
All five typed modes and terminal termination are exercised.

The package uses explicit five-member eligible IDs checked against the accepted
registry fixture. This is a permitted revision-2 representation. Empty-descriptor
accepted-context lookup is not implemented by the inherited oracle and is not
claimed here. No signer-selected roster, denominator shrink or controller,
emergency or global-trust policy substitution is accepted. Full-roster control
domains must be independent, including unsigned members. These are supplied
trusted-context fixtures, not company-name evidence or authenticated provenance.
No five-separately-incorporated-companies or three-stakeholder-class rule is added.

Context-specific transparency/witness obligations are explicitly simulated input
outcomes. Missing/unknown obligations stay pending. This does not implement those
proof verifiers, introduce universal membership 2/3 witnesses, authorize skipping
a required event round, or establish high-impact governance. Real accepted context
and applicable obligations must be authenticated before any runtime use.

The evaluator parses the actual typed record, binds its digest/scope/lineage to
the envelope, checks record validity against a supplied fixture time, and reuses
the existing cryptographic Option C verifier. Public deterministic signing seeds
are the existing class-4 fixture material; no fresh key generation is used.
Results carry `runtime_authority=false` and `mutation=false`; no semantic authority
token, receipt, event, provider, readiness or active-work mutation is produced.
Replay coverage is request/session/lineage binding, not durable replay history.

Run with the provisioned environment and existing supervisor:

```
python -m scripts.normal_revocation_conformance --check
python -m pytest -q -p no:cacheprovider tests/federation/test_normal_revocation_conformance.py tests/federation/test_threshold_container_supplement.py tests/federation/test_revocation.py
```

CI's python-protocol profile includes the retained-vector check and federation
tests. Local success is not hosted CI evidence. The separate JSON evidence record
retains exact commands, counts, failed attempts, source hashes and cleanup.

Independent review found a missing full-roster independence check: three counted
independent signatures initially admitted two unsigned common-control members.
A deterministic failing regression was retained before the correction. Review
also identified the explicit-ID coverage limit documented above.

Stage 3 remains partial (2/10 complete). Runtime/live flags remain false. Real
membership provenance, currentness, context-specific witness verification,
rollback-resistant restart floors and all-mode runtime composition remain gates.
The final comprehensive security audit before a real pilot is still required.
No installation, network activation, hosted CI, commit or push was performed.
