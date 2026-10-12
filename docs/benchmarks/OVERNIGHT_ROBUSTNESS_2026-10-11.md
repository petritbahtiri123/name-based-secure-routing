<!-- Publication derivative; original SHA-256 933ec87bb4839d0a3586f58c44fee9a6ac079f8b13d3b08243d82ee95effc806. Personal identifiers removed. Historical hashes, results and commands refer to original local inputs; placeholder commands were not executed. Originals retained locally. -->

# Overnight robustness — 2026-10-11

New overnight authorization received2026-10-10 20:47UTC; cutoff07:00UTC October11.
Small evidence-led local improvements; no new trust/lifetime/registry decisions,
persistent credentials, external traffic, push/deploy or security changes. Prior
October10 work remains dirty and preserved; no local commits have been made.

## Checkpoint1: challenge authority revision

Python/Rust mismatch reproduced for registration and renewal. Python now rejects
a proof whose current authority revision differs from its challenge snapshot;
old owner/lease survives and next-counter recovery works. Two red regressions;
434 final scoped passes, no exclusions. Python vector check and Node independent
artifact/replay checks pass, lint/format/diff checks and independent review clear.
See `docs/reviews/2026-10-11-connector-challenge-revision.md` and JSON.
All children reaped; no task sockets/containers or visible relevant workers.
Stage3 remains partial; no publication or runtime trust claim.

## Checkpoint2: Go observed-expiry latch

Three expiry-observation paths reproduced rollback resurrection and now latch
ineligibility while preserving ownership. Go21+3 top-level passes (71+10 events),
one parent-only loopback skip; vet/format/diff and independent review clear.
See `docs/reviews/2026-10-11-connector-go-expiry.md` and JSON. All children reaped,
no sockets/containers or live rerun. README updated; uncommitted/unpublished.
Parent checkpoint notification tool returned thread-not-found; no retries.

## Checkpoint3: Go observed-time floor

Three rollback paths reproduced and fixed: pending ACCEPT recovery, authority
callback and owner view before expiry. Go25+3 top-level passes (77+10 events),
one parent-only worker skip; vet/format/diff and independent review clear.
See `docs/reviews/2026-10-11-connector-go-clock.md` and JSON. No new real clock,
lifetime policy, sockets/keys or live rerun; cleanup complete, uncommitted.

## Checkpoint4: Rust observed-time floor

Four clock failures reproduced and fixed at attach/handle/poll; retains owner
and cleanup-ticket identity. Rust23passes/1live-ignore, Clippy/format/diff and
review clear. See `docs/reviews/2026-10-11-connector-rust-clock.md` and JSON.
No new live execution, sockets/keys or runtime trust. All children reaped.

## Final reviewed handoff

Five bounded fixes are complete: Python challenge revision binding, Go observed
expiry retention, Go observed-time floor, Rust observed-time floor, and exact
integer typing of Python current-revision snapshots. The last fix rejects bool
and float values that otherwise compare equal to integer revisions.

Latest focused results: Python **436 passed**, zero exclusions; Go **28 top-level
passes** (87 pass events), one default worker skip; Rust **23 passed**, one default
live ignore. The separately authorized fresh loopback passed **19/19 cases**.
All five deltas received independent review. The earlier unchanged-vector checks
passed 20 files/24 specifications and Node checked 19 hashes/34 transitions; these
checks were not repeated at finalization. Across 29 supervised runs, six expected
red runs retain 14 failing cases/subcases. No resource abort occurred.

See [revision type evidence](../reviews/2026-10-11-connector-revision-type.md) and
[fresh loopback evidence](../reviews/2026-10-11-connector-loopback.md).
All supervised children were reaped; no live-test PID or UDP endpoint remained.
The new Go worker was removed after hashing. Existing caches and older worker
were preserved. No task containers, downloads, commits or publication occurred.

Stopping at this coherent reviewed checkpoint before the cutoff, without claiming
continuous work until morning. Stage 3 remains partial; stages 1-2 remain 2/10.
Real authority/revocation-provider composition and real timer delivery remain open.
A future integration should review request-ID binding at the verifier interface;
this is a design seam, not a demonstrated vulnerability. Pure fixture assembly
does not itself require new authorization. The parent notification tool returned
thread-not-found; this final handoff is available through task completion.

## Follow-up: connector CI selection

The parent-authorized CI audit found and corrected explicit selection gaps.
Final CI regressions: 23 passes; newly selected Python/config: 297 passes;
tagged Go test/vet and Node verifier pass; exact new manual loopback profile
passes 19 cases. Nine supervised runs, two retained failed attempts, no resource
abort. Independent review clear after removal of a nested-supervisor flaw.
See [CI selection evidence](../reviews/2026-10-11-connector-ci-selection.md).
Hosted schema/execution remains unrun; no publication, dependency or security
setting changes. No remaining evidenced local selection gap; next validation
is an authorized hosted run. Earlier checkpoint hashes remain historical.

## Approved local normal-revocation conformance amendment

Revision 2's named policy/group mapping now has a separate pinned amendment and
33 deterministic literal cases. Final scoped Python/CI result: 103 passed,
3 unaffected process-supervision tests deselected. Vector check and Ruff pass;
independent review clear after a reproduced full-roster common-control gap was
fixed. Explicit eligible IDs are covered; accepted-context empty-descriptor lookup
is not. See `../reviews/2026-10-11-normal-revocation-conformance.md` and `.json`.
Historical parent policies/vectors remain unchanged. All provenance and witness
outcomes remain fixtures; runtime/live flags false, Stage 3 partial, 2/10 complete,
final comprehensive audit gate retained. No sockets, new keys, downloads, hosted
CI, commit or push. All supervised children reaped; no resource abort.

## Signed witness/checkpoint integration follow-up

The local normal-revocation check now has a separate explicit witness-required
entry point composing existing COSE, consistency, checkpoint-continuity and
authenticated-witness verifiers with the record's exact checkpoint reference.
Final scope: 123 tests passed, no skips/deselections; 31 new integration tests.
Ruff and independent review clear. The missing-API RED result is retained.
See `../reviews/2026-10-11-normal-revocation-witness-integration.md` and `.json`.
This verifies checkpoint confirmation under public fixture configuration, not
revocation-record inclusion, real governing provenance or durable restart floors.
Those inputs are the next gate; runtime/live flags false, Stage3 partial, 2/10,
final audit retained. No sockets, keys generated, installation, hosted CI or push.

## Exact record inclusion: contract boundary

Read-only source review and five bounded diagnostic assertions expose an unresolved
leaf/reference mapping: including the whole final record in the checkpoint named
inside its required field 39 creates a construction dependency cycle. The existing
inclusion regression passes (1 test); no verifier or vector was changed. Independent
review confirms that no accepted cycle-free mapping was found in inspected sources.
See `../reviews/2026-10-11-normal-revocation-inclusion-contract-gap.md` and `.json`.
Next prerequisite is the approved exact leaf bytes, signed-record binding and
field-39/checkpoint/proof placement semantics. No fixture equivalence or runtime
activation is claimed; previous 123-test results remain historical, not rerun.

## Approved version-2 full-record inclusion

After explicit approval of the reviewed mapping, separate v2 local conformance
now verifies full signed record inclusion with prior anchor, detached signed
checkpoint/proofs/witnesses, retained floor and replay bindings. Final 200 tests
pass (76 inclusion, 123 neighbors, one CI selection), no skips/deselections.
Six v2 packages and 89 historical threshold literals checked separately. Review
clear after retained RED/GREEN floor and event-replay fixes. See
`../reviews/2026-10-11-revocation-inclusion-v2.md` and `.json` for exact evidence.
Historical policies/vectors remain unchanged; runtime/live false, Stage3 partial,
2/10 complete. Real provenance, durable restart and all-mode live composition,
broader proof chains and final audit remain gates. No sockets, keys generated,
installation, hosted CI, commit or push; supervised cleanup retained.

## Inclusion restart: persistence decision boundary

Read-only investigation and independent review found no existing lossless
inclusion-state projection in federation schema 1. Three pure store tests pass;
no filesystem restart or private-write tests ran. A separate versioned bounded
persistence contract and approved independent floor/provenance are required
before claiming restart security. Windows write/repair paths harden ACLs and
were not invoked under current constraints. See
`../reviews/2026-10-11-revocation-restart-boundary.md` and `.json`.
No implementation change; runtime/live remain false and Stage 3 remains partial.

## Proposed inclusion persistence/recovery contract

Prepared approval-ready INCLUSION-PERSISTENCE-01 in
`../reviews/2026-10-11-inclusion-persistence-design.md` and adjacent JSON.
Separate bounded schema, watermark-first recovery, injected exact restart
expectation, and action-time Windows ACL scope are explicit. Independent review
corrected attribution of ancestor-reparse/alias checks; remaining design had no
blocking contradiction. Design only: zero tests, behavioral or ACL changes.
Power-loss durability and production rollback-resistant provenance remain open.

## Approved inclusion persistence: memory implementation

Implemented the approved separate codec and storage-neutral coordinator with
exact expected-digest recovery and retained replay/denial state. Final 255 tests
pass, including 51 persistence tests; lint/format/diff checks pass. Independent
review clear after retained RED/GREEN ownership-release and reentrancy fixes.
See `../reviews/2026-10-11-inclusion-persistence-implementation.md` and `.json`.
Nine supervised runs retained, including failures; all children reaped without
resource abort. No filesystem adapter, ACL changes, keys, sockets, hosted CI,
commit or push. Filesystem/private-write and real restart trust remain gates;
runtime/live false and Stage 3 completion counts unchanged.

## Approved filesystem trial: stopped in preflight

One authorized supervised attempt stopped when child Windows PowerShell could
not load Microsoft.PowerShell.Security for Get-Acl. No root creation, ACL changes
or filesystem tests ran; exact root absence verified, child reaped, no resource
abort. See `../reviews/2026-10-11-inclusion-filesystem-approved-attempt.md` and
`.json`. Prior 255-test memory results remain historical; filesystem gate open.

## Same-root approved filesystem retry passed

Corrected only the 5.1 child Security-module selection through $PSHOME. Three
assertion groups passed: observed exact private ACL, real write/read/reopen and
idempotence, and injected post-watermark replacement repair. Supervised 5.43s,
no resource abort, child reaped. Exact root removed and absence independently
verified. See `../reviews/2026-10-11-inclusion-filesystem-matching-module.md`
and `.json`. Earlier failure preserved. No process-crash/power-loss or production
trust claim; runtime/live remain false and Stage 3 partial.

## Connected authority-to-owner proposal

Prepared `../reviews/2026-10-11-connected-authority-owner-proposal.md` and JSON:
native normal-v2 verified deny-new/termination into existing fixture-created
owner, with exact retained-ticket cleanup; no positive provider admission/READY.
Independent review corrected unsupported typed effects and synchronous-release
hazard. Reconciled filesystem trial PASS narrowly in acceptance matrix.
Design only; no tests or activation. Stage 3 partial, 2/10 unchanged.


### Connected authority owner — incomplete checkpoint

Native test-only bridge: 6 tests passed; independent Python oracle/inclusion tests: 77 passed; 11 vector cases checked. Final-apply expiry regression reproduced and fixed. Rust neighbor build stopped by RAM guard; no retry. Four independent-review blockers remain. No runtime authority, positive registration or READY; Stage 3 partial, 2/10. See [2026-10-11-connected-authority-owner-checkpoint](../reviews/2026-10-11-connected-authority-owner-checkpoint.md).


### Connected authority owner — reviewed continuation

Four review blockers and the retained-anchor parity issue were reproduced and fixed. Rust 44 passes; Python/CI 159 unique passes across focused run and targeted environment retries; all failures retained. Eighteen vector cases and two replay pairs, six historical packages, Ruff, crate format and scoped Clippy passed. Independent review found no remaining scoped blocker. Supplied test trust and synthetic owner only; no registration provider/READY/runtime authority. Stage 3 remains partial, 2/10. See [implementation report](../reviews/2026-10-11-connected-authority-owner-implementation.md). Docker has no running containers and is not needed by this active native work; read-only disk assessment (local-only evidence omitted; see publication manifest) records candidates without deletion.


### Approved incremental cache cleanup

Only the assessed inactive Rust incremental directory was removed after explicit user approval. Logical bytes removed: 3,908,720,279; free C: increased from 11,693,117,440 to 15,179,739,136 bytes. Exact path/reparse/inactivity checks and unchanged retained binary hash are recorded in cleanup evidence (local-only evidence omitted; see publication manifest). No builds or broader deletion followed. Stage 3 remains partial; the next proposed gate is root-signed KAR purpose authentication under a separately bounded fixture design.


## KAR genesis design checkpoint

Inventory and independently reviewed design: [proposal](../reviews/2026-10-11-kar-genesis-design.md), [source-pinned inventory](../reviews/2026-10-11-kar-genesis-design.json). No matching retained purpose-12 chain was found for the five normal roster keys in the reviewed material. Recommend an isolated supplied-root genesis semantic prerequisite; new purpose-12 fixture mappings require a separate decision. Review corrected draft expiry semantics to the existing inclusive boundary. No implementation, signing, keys, builds or tests. Approved incremental cache remains absent; prior cleanup and evidence preserved.

## Isolated genesis KAR implementation

[Report](../reviews/2026-10-11-kar-genesis-implementation.md) and [manifest](../reviews/2026-10-11-kar-genesis-implementation.json): reviewed test-only gate, 15 Rust and 65 Python passes, 14 existing signature cases verified. Seven semantic baseline failures and one CI-selection failure retained. Inclusive expiry and exact purpose preserved; no new signatures or keys. Successful composed positive acceptance remains incomplete; no normal-roster authority connected, READY false, Stage 3 partial 2/10. Ten bounded runs had no resource abort and all direct children reaped. Authorized builds recreated small incremental outputs; prior cleanup record unchanged.

## Composed-positive fixture proposal

[Proposal](../reviews/2026-10-11-kar-composed-positive-proposal.md) independently reviewed: exactly one deterministic signature over the unchanged purpose-3 genesis payload with the existing public test root. Purposes 12 and 14 reject; normal-roster mapping remains deferred. No signing, key generation, implementation or builds. Separate local publication assessment is not a publication authorization.
