# Composed-positive genesis KAR — October 12 checkpoint

Status: scoped composed-positive fixture, Python and native validation COMPLETE
after the separately approved bounded recovery described below. Independent read-only review found no substantive code or
security defect. No runtime behavior, trust registry, owner, permit or READY change.

## Source and authorization

The user approved exactly one deterministic test signature over the unchanged
purpose-3 payload in `2026-10-11-kar-composed-positive-proposal.md`. One invocation
of the existing Sign1 helper reconstructed the existing public test root recipe
in memory. No new key identity, private-key file, credential or additional signature
was generated. No purpose-12/14 positive fixture or normal-roster mapping exists.
The subject public-key literal does not prove possession.

Source commit: `ad77d59754651fee449bb1d9c14a946f9f3b2d15`.
Root tree: `106fb549a4088681b318cc57c3ed00754e4c925e`.
This is a verified sparse materialization, not a completed Git checkout: its Git
index/HEAD were not initialized after fetch stopped. Before edits, all 2,614
materialized file blobs matched the root tree; `evidence/performance/` was excluded.
2,611 files came from the verified predecessor workspace; two CI changes matched
another local workspace. Only `tests/ci/test_ci.py` was retrieved, with exact blob
`249435ebf814e195ceaae944480dc8a80b60b3d0`. Original dirty checkout was untouched.

## New evidence

The retained artifact is `crates/nbsr-transport/tests/fixtures/connector-kar-genesis-positive.json`.
Payload SHA-256: `714ff7bebf0d29c5ba596e486913fcfdba97d61ece00bf114b26d2f4c839afed`.
Wire SHA-256: `e1a0dcf579c9c3fee828366dc0e09dec2794c76985fadfd8377ef97cf402a37c`.

`python -m scripts.check_connector_kar_positive --check` creates no signatures:
it verifies retained bytes against the schema recipe, public test root and existing
Python verifier. Four positive cases pass (1000, 1500, 2000, exact root expiry),
as do 18 rejection cases. The missing-fixture red assertion is retained.

Four Rust tests add full composed positive and negative coverage, including exact
child bindings, terminal subject, wrong root contexts, inclusive boundaries and
mutations rejected at the signature/envelope boundary. They are formatted and
independently reviewed but NOT executed or confirmed compiled in this checkpoint.
Existing gate implementation changed only a comment. Existing connector_kar CI
selection remains; Python protocol CI adds the read-only checker and a clean-
PYTHONPATH invocation regression. No hosted run is claimed.

Fresh Python neighbors: initial 85 passed / 4 setup errors (sandbox default temp).
A fresh writable basetemp retry passed three cases and failed the process cleanup
case with code125 instead of124. That exact case passed on the host: one pass.
Thus 89 unique tests passed across runs, not a single uninterrupted green suite.
All failures remain in evidence. Python 3.14 does not establish the full matrix.
Ruff for all three changed Python files and crate formatting check passed.

## Retained initial resource-stop checkpoint

Original free-disk baseline remains 14,247,788,544 bytes; the 2 GiB cumulative
ceiling was never reset. Two failed source attempts retain both partial packs:
270,802,955 and 300,810,240 bytes. First failure: malformed CRLF alternates path.
Second: filtered fetch returned the commit/tree pack but grew a second temporary
pack before checkout; logs do not establish its nested request's cause.
Approved exact-file materialization completed in 16.79s within its 64 MiB cap.

Native command: `cargo rustc --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --jobs 2 --test connector_kar --message-format=json`.
Cargo also compiled benchmark bins. The supervisor stopped after 24.06s at its
256 MiB per-command disk guard (observed growth 310,951,936 bytes between samples).
No current connector_kar executable artifact was emitted. No native retry occurred.
The owned process tree was terminated; final read-only inventory found no relevant
Git/Cargo/rustc/Python worker. Test child PIDs 4900 and 12868 were absent.
No test/listener sockets, containers, live trust or infrastructure were created.

Remaining: approve or establish a resource-bounded native target build approach
that avoids benchmark binaries, then execute exact native tests and relevant
signature/control neighbors. Existing cached historical binaries are not evidence
for changed source. No stage advancement, commit, push or policy change occurred.

Local detailed logs, source proof, source delta and hashes are retained at
`C:/Users/OPERATOR/AppData/Local/Temp/nbsr-kar-positive-evidence-20261012`.


## Approved native recovery — final result

The user approved one additional attempt capped at 512 MiB across its commands,
inside the unchanged original 2 GiB cumulative ceiling. The supervisor temporarily
set `autobins = false` in the isolated package manifest, verified metadata had no
binary targets, and ran:

```text
cargo test --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --jobs 2 --test connector_kar --test connector_signature --test connector_control
```

The unchanged production library was compiled/linked as the package dependency;
no benchmark binary was selected. Fresh results: **12 KAR + 6 signature + 1 control
= 19 passed, zero failed/ignored**. All four new composed tests passed, proving
acceptance at 1000/1500/2000 and exact root boundaries plus the proposed negative
contexts and cryptographic/envelope mutations. No new signature was generated.

The attempt completed in 3.94 seconds with no abort and 52,592,640 bytes of disk
growth; ending free disk was 13,387,612,160 bytes and available RAM 4,549,459,968.
Manifest restoration ran in `finally` and its before/after SHA-256 matches:
`81103d93ae135c3e7763c5f81ca4960efd581bd881a1de5016a2731054af0d11`.
The direct child was reaped. Detailed target metadata, logs and executable hashes
are retained alongside the earlier failures. No guard budget was reset.

Independent read-only follow-up verified the new evidence and found no remaining
scoped acceptance blocker. This validates selected integration targets using a
temporary manifest setting, not an unmodified full Cargo build or hosted CI.
The earlier INCOMPLETE descriptions above are preserved historical checkpoints,
superseded for this exact composed-positive task only. No runtime authority,
purpose-12/14 positive fixture, normal-roster trust or READY follows.
