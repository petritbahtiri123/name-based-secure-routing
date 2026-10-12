# Stage 1 review checkpoint — bounded mock tests

Base HEAD: c7abbc4423a9ad05cea9cdf6678c231a34cafd59. This increment changes only
`tests/test_connector_federation_model.py` behavior coverage plus documentation
and evidence. Both model source files and the 88-case lifetime regression file
remain byte-identical to the retained 174-pass adapter checkpoint.

## Exact additions and results

13 new parametrized cases:
- Destination signer and shared authority-proof expiry: valid just before 200,
  cancelled/closed at 200 and after; recovery cannot revive expired ownership.
  A mismatched destination proof is rejected rather than silently substituted.
  The valid bilateral proof is shared by digest; no independent unsigned proof
  lifetime is invented for one side.
- Two simultaneously live owners with different proof dependencies: deny-new
  and terminate affect only the dependent owner; the other remains usable and
  is explicitly cleaned up. Cross-owner/context events are rejected.
- Source and destination evidence changed at the same clock instant: revoked
  dependency, policy mismatch or incompatible checkpoint rejects recovery after
  a prior successful verification. Cached decisions cannot restore eligibility.
- Timed semantic fixture: existing TypedRevocationRecord validity and synthetic
  threshold helper reject pre-effective/expired use. At effectiveness, explicitly
  simulated deny preserves finite work, while terminate cancels immediately.
  Record expiry does not erase the instance's enforcement latch.

The timed fixture owns scheduling and explicitly supplies the dependency event;
it does NOT establish a record-target-to-runtime-owner mapping, authenticated
event delivery, threshold transport packaging or a scheduler implementation.
Existing record timestamp validity is inclusive; the adapter's conservative
exclusive work expiry remains unchanged. No new normative semantics are introduced.

`connector-gap-focused`: 13 passed, 21 deselected, zero skips, 0.90s pytest,
2.22s supervised. `connector-gap-final`: 187 passed, zero skips (34 adapter,
88 model, 65 authorization/outage/revocation/state neighbors), 1.71s pytest,
3.02s supervised. Ruff check and format check passed on the changed test file.
No failing check and no implementation bug were observed in this increment;
no model fix was necessary. The original 174-pass logs/manifests/snapshots remain
unchanged historical evidence, not relabelled as the newer test source.

All direct supervised children were reaped, with no abort. Final free disk
12295380992 bytes; RAM 4407529472 bytes. Existing limits: 95s work bound, 8-GiB
disk start/6-GiB floor, stricter 256-MiB growth guard, 2-GiB RAM reserve. No
containers/builds/downloads or persistent credential operations. Cleanup and
independent review outcomes are recorded in the accompanying manifest.

## Remaining five bindings

1. **Identity/registration right:** reuse exact KeyAuthorizationRecord purpose,
   key and lifecycle plus non-widening DelegationRecord scope. Still identify the
   approved registration action and connector-principal binding; operator match
   alone is insufficient (specification/mapping gap).
2. **Live acceptance proof:** reuse authenticated control conventions, but locate
   or approve the exact connector role/transcript linking authority, session,
   attempt and owner generation. RouteGrant PoP cannot be repurposed (spec gap).
3. **Ongoing authority/deadlines:** map applicable signed/profile evidence to
   admission versus continuing work, with existing bounded grace. Do not treat
   all expiries alike or turn fixture timing into connector defaults (mapping gap).
4. **Dependency ownership:** connect existing context/dependency/route digests
   and DependencyIndex to real owner handles; transport compromise versus one
   service must use F93's narrowest affected scope (runtime implementation gap).
5. **Authenticated events:** reuse TypedRevocationRecord authority/target/scope/
   effective-time/lineage/mode checks once an approved delivery boundary exists.
   Simulated events do not fill the unfrozen threshold packaging or authenticated
   event integration gap.

Stage 1 remains partial; 0/10 package milestones complete. Stop here for review.
No new task, commit, push, bypass, runtime integration, wire allocation, credential
issuance or authority expansion. Unrelated paused-peer and user work preserved.
Published c7abbc44's seven-job successful CI remains separate from these local tests.


Independent narrow test review found no blockers. Snapshot comparison confirmed
only the fixture expiry parameter and 13 new cases; timed effects are explicitly
test-scheduled, not evidence of an adapter scheduler. Reviewer did not rerun tests.
Get-Process after testing returned zero visible Python processes. Root guidance
was reviewed; commands and model semantics did not change in this increment,
so no further AGENTS edit was needed.
