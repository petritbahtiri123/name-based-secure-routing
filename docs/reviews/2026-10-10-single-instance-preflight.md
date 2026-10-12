# Single-instance Stage 1 closure and Stage 2 offline preflight

## Outcome and authority

**Stages 1 and 2 meet their scoped contract/offline acceptance gates: 2/10.**
The user explicitly approved Rust destination registration/cleanup ownership,
Go origin attempts/renewal ownership, and Python as the offline reference oracle,
then authorized Stage 2. The profile's exact future file/interface inventory is
reconciled. The proposed separate Python gateway coordinator is superseded by
`nbsr/connector_registration_offline.py`; no duplicate implementation was added.

Stage 1's success and negative cases map to the current draft-2 vector manifest:
24 executable scenario mappings, 19 artifact hashes and four counter traces
(34 independent transitions, verified in the previous unchanged checkpoint).
This turn reran its 103 CRP tests and 187 model/federation plus 68 CBOR neighbors.
Wrong peer/service, expired/revoked authority, stale revision/generation and
conflicting ownership have explicit fixture outcomes. Fixture verifier decisions
are not real registration-chain proof. Independent review confirmed the ownership
approval and synchronized inventory resolve the remaining contract decision.

The frozen contract, D1–D3, replay counters, typed revocation and independent
active-work lifetime policies remain unchanged. Wire message/action/profile/ALPN
allocations and any pinned transport overlay require separate reviewed pre-wire
authority before Stage 3 activation. Real producers, clocks, asynchronous cleanup,
transport conformance and deployment remain their later implementation gates.

## Stage 2 deliverables

`deploy/single-instance/` contains the strict validator, generated structural JSON
schema, public illustrative example, 62 focused tests and usage/limitations README.
It reuses provisioned Pydantic and the existing canonical-name helper. It avoids
service Settings environment/default/key-loading behavior and adds no dependency.
One service entry is keyed by service/gateway identity; client data has no origin.
Registration limits preserve the approved finite profile; GET / and 4096-byte
request/response limits remain explicit. Unknown/pilot modes reject.

The parser rejects duplicate/unknown/missing fields, malformed/oversized/deep JSON,
nonfinite numbers, coercible numeric types, mismatched scopes, invalid endpoints,
unsupported versions, missing/path-like/inline references and widened limits.
Diagnostics identify known fields without printing supplied values or unknown keys.
Success is `CONFIG_VALID_OFFLINE`, with `ready=false`, `references_verified=false`.
References are logical names: existence, contents, ACLs, authority/provenance and
provider binding are not checked. No real credential is created or configured.

The CLI reads only an explicit local materialized regular input file, up to 64 KiB.
Windows fixed-drive and root-to-leaf lstat checks reject UNC/device/ADS inputs,
links/reparse points and offline/recall files before descending. This assumes stable
operator-controlled directories, not a concurrent filesystem attacker. Other
platform callers must ensure the filesystem is local. A fresh-process audit test
covers import and check for no sockets, subprocesses, writes or directory creation.
The path regression uses synthetic reparse metadata; no real network share was
activated. Origin hostnames are checked syntactically only; private destination
resolution/authorization remains Stage 5. Schema-only validation is insufficient;
the Python semantic checks must also run.

## Measured checks and failures retained

Final scoped suite: **420 passed, zero failed/skipped** = 62 preflight + 103 CRP +
187 model/federation + 68 CBOR. Python 3.14.6/Pydantic 2.13.4 on this Windows host;
this is not a full Python/platform matrix or hosted CI result. Ruff check/format
and the example CLI passed. Schema/example equality is checked by the tests.

Ten supervised runs and stdout/stderr logs are retained in the accompanying
manifest. Expected reds: missing implementation (1 failed); missing backoff const
in structural schema (1 failed, 6 passed); review findings (2 failed). First full
attempt: 50 passed, 4 setup/teardown errors from oversized pytest parameter IDs
and an unwritable default Windows temp location. Short parameter IDs and a fresh
task-owned writable `--basetemp` resolved those harness issues. Subsequent focused
runs passed 53 and 62 tests; final neighbors passed 420. No failed run was omitted.
One PowerShell quoting attempt and one documentation UTF-8 read attempt failed;
corrected before completion. Those authoring outputs were not saved as standalone
logs. Intermediate failed source versions are not retained; final snapshots and
exact run metadata are retained.

Independent review reproduced a 5,000-digit JSON integer escaping redaction and
identified links reaching remote files through local-looking paths. Both now have
regressions and fixes. Rereview found no remaining blockers for the authorized
offline Stage 2 criteria or Stage 1 contract closure. Reviewer inspected the fixes
but did not independently rerun the reported suite.

## Local artifact and cleanup status

All changes remain uncommitted; index is empty. No push, live network/trust,
credential creation, registry allocation, dependency download, deployment or OS
setting change occurred. Prior counter/model source and artifacts match their
historical hashes. Mixed existing work and old manifests were preserved; new
source snapshots, exact hashes, full current tracked patch and status inventory
identify this dirty checkout without claiming the base commit alone identifies it.

All ten supervised children reaped without resource abort. The audit subprocess
was awaited. No task-created container or background worker was started; test
fixtures/logs are retained intentionally. Final suite: 5.42s including supervision,
12,184,662,016 bytes free disk at start, 12,184,641,536 at end; 4,855,562,240 bytes
available RAM at end. No builds occurred. Remaining work starts with Stage 3's
separately approved pre-wire allocation/authority gate and authenticated runtime
registration; Stage 2 validity must never be used as its readiness signal.
