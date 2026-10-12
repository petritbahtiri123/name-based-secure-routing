<!-- Publication derivative; original SHA-256 a50a8dab69ab4cad0dc3f92234a90afb0024293768584ec0a43e091bbd79f8a6. Personal identifiers removed. Historical hashes, results and commands refer to original local inputs; placeholder commands were not executed. Originals retained locally. -->

# Connected authority owner: reviewed local implementation

The four checkpoint blockers are resolved in the approved test-only slice.
Independent source review found no remaining scoped blocker, including the
additional retained-anchor parity correction. Work remains uncommitted on
`codex/nbsr-v3-wp0-wp1` at base `c7abbc4423a9ad05cea9cdf6678c231a34cafd59`.
The adjacent JSON manifest identifies exact source snapshots, binary hash,
commands, retained failures and cleanup. The earlier incomplete checkpoint and
RAM-guard abort remain unchanged historical evidence.

## Behavior and scope

Native Rust verifies the actual signed normal-v2 record, Option-C signature
context, full-record inclusion, consistency and configured witnesses under
explicit `SuppliedTestTrust`. It applies only DENY_NEW_USE or
TERMINATE_ACTIVE_USE to an explicitly fixture-created owner. The producer has no
positive registration authorization path and always reports registration-ready
false. Termination retains the existing cleanup ticket and quota until exact
successful confirmation; failure requires explicit retry.

The four reproduced defects and fixes are:

1. **Dependency applicability:** the canonical supplied inventory must hash to
   the exact owner dependency digest and contain the signed target. An unrelated
   digest or absent target rejects. This inventory is a local fixture input,
   not authenticated registration evidence or a new wire allocation.
2. **Configuration consistency:** pinned input still must agree internally.
   Bundle log/witness references, thresholds, profile and staleness match the
   supplied policy/keys. Closed policy fields retain normal class/message/effect,
   class minima and independence requirements. Full eligible-roster key reuse
   rejects. Root/controller references retain their expected class/operator shape;
   this does not authenticate genesis or an identity-root key-authorization chain.
3. **Record validation:** native checks match unchanged reason-code, validity,
   generation/sequence and terminal-expiry requirements. Five correctly signed,
   logged and witnessed malformed records reproduced acceptance before the fix;
   all now reject. The valid terminal record still passes.
4. **Fresh-event idempotence:** identical R under fresh E retains E-to-R and
   advances the provider revision without reapplying denial/cleanup or changing
   the accepted floor. Rebinding that E to another signed R rejects, and the
   original cleanup ticket still confirms ownership release.

The final event also retains every selected key/witness/record/authorization
deadline from the earlier freshness fix. Final owner, request, session,
dependency, provider-instance and revision checks precede mutation.

Independent review corrected one over-rejection: the retained prior anchor A is
authenticated and identity-bound, while freshness applies to containing C at
verification and final application. The old-A/fresh-C fixture matched Python
ACCEPT, reproduced Rust rejection, and now passes. The fixture builder gained an
optional anchor timestamp; its default output and all six historical packages
remain byte-identical under `--check`.

## Verification

| Check | Result |
| --- | --- |
| Rust `connector_authority` | 13 passed |
| Rust codec / registration / signature neighbors, sequential | 1 / 24 / 6 passed |
| Total unique Rust tests | 44 passed, no ignored tests |
| Python connected vectors / inclusion / persistence / CI contracts | 159 unique passes across initial run and focused retries |
| Connected retained vector check | 18 cases and 2 replay pairs passed |
| Historical inclusion package check | 6 packages passed |
| Crate formatting, scoped Ruff, scoped Clippy `-D warnings` | Passed |
| Diff whitespace check | Passed; existing line-ending warnings retained |

Python first passed 155 tests with four default-temp setup errors. A fresh
task-owned `--basetemp` resolved those setup errors: three passed and the existing
owned-child timeout test reported cleanup exit 125 in the sandbox. That single
test passed unchanged in the host context with a second fresh test root.
Both recorded child PIDs (11864 and 7356) were subsequently confirmed absent.
This is 159 unique tests, not a single uninterrupted all-green run.

Other negative attempts remain recorded: four original RED reproductions,
old-anchor RED, missing-CI-selection RED, two initially overstrict configuration
length checks corrected to existing contracts, and two Clippy findings corrected
without suppressing them. Clippy corrections use `is_multiple_of` and a boxed
cleanup-result variant; the full authority target passed again afterward.
Pre-existing benchmark-bin warnings remain in test output; no whole-repository
Clippy or hosted CI success is claimed.

Rust CI now explicitly selects the test target. Python-protocol selects the
federation test plus `python -m scripts.check_connected_authority_vectors --check`.
CI contract regression confirms selection without live/ignored execution.
AGENTS, CI guidance, protocol status and the full-model matrix retain the scope
restrictions. No production source overlay or frozen registry changed.

## Resources, cleanup and remaining limits

Every Rust run used the existing offline Windows cache and one build job.
The unchanged supervisor checked disk/RAM before each run and retained its
95-second deadline, cleanup-inclusive bound, 2 GiB RAM reserve and stricter
256 MiB per-run disk-growth guard. All 29 continuation runs completed without
a resource abort; every supervised direct child was reaped. No visible task
compiler/connector worker remained at final inspection. No sockets, containers,
new keys, downloads, ACL/security-setting changes, commits or pushes were made.

This is local normal negative enforcement with synthetic ownership and supplied
trust. Controller/emergency acceptance, authenticated bootstrap/key-governance
provenance, positive register/renew authorization, durable native floors and real
timer/delivery integration remain unimplemented. The local proof horizon remains
0-to-1 or 1-to-2 leaves. READY and runtime/live flags remain false; Stage 3 stays
partial and overall completion remains 2/10.

The requested disk assessment (local-only evidence omitted; see publication manifest) is read-only.
Docker had zero running containers and is not needed for this native task, so
quitting Docker Desktop is safe for the active work. No cleanup deletion occurred;
historical containers/evidence, volumes and active dependency caches are preserved.
