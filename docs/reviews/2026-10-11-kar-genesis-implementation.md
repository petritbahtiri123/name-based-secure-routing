# Isolated genesis KAR implementation

The authorized isolated slice is implemented and independently reviewed. It is
test-only and replaces no normal-roster assertion. **Successful composed positive
acceptance remains unverified**: existing retained signatures have disjoint root
and KAR validity windows, and this task prohibited new signatures. No historical
bytes or supplied signer metadata were changed to manufacture acceptance.

## Implementation and scope

`crates/nbsr-transport/src/connector_kar.rs` compiles only through the separate
`connector_kar` integration-test target. Its private composed function first runs
the existing exact tagged COSE_Sign1 verifier against the expected payload, key
and kid, then checks the canonical KAR semantics. Only that composed function
constructs its private checked result. The private semantic helper returns no
authenticated result and exists separately for deterministic semantic coverage.

The gate checks object/version, required/allowed fields, exact unsigned integer
and boolean types, canonical encoding, bounds and noncritical extensions. It
requires active unrevoked root and child, exact requested child identity/purpose,
operator and authorizer binding, and inclusive validity for both root and child.
Generation/sequence must be 1/1; predecessor and recovery fields are rejected.
Explicit terminal-key fixture context rejects reuse. Issuer field 3 retains its
existing schema checks without inventing an additional global issuer/root join.

There is no service-scope field or inferred service permission, rotation/recovery
implementation, persistence, timer, network access, owner mutation, Authority
conversion, permit or READY conversion. Supplied roots and terminal IDs remain
test inputs. The five normal-roster authorities are unconnected, and no purpose-12
authorization fixture was created. Stage 3 remains partial, 2/10 overall.

## Evidence and review

The [manifest](2026-10-11-kar-genesis-implementation.json) retains commit/branch,
source and binary hashes, before/after snapshots, patch, exact commands, limits,
logs, cardinality and cleanup. Evidence is under
`evidence/connector-registration-development/2026-10-11-kar-genesis-implementation/`.
The prior [design](2026-10-11-kar-genesis-design.md) and its thirteen pinned sources
remain byte-identical to the design inventory.

Seven focused RED tests used an explicitly recorded primitive-only baseline:
signature/CBOR decoding alone accepted inputs lacking the required KAR checks.
All seven failed at expected assertions; this demonstrates the need for the new
layer, not a defect in the deliberately signature-only primitive. The baseline
and tests are retained. A separate CI regression failed because the new target
was absent. Both failures remain in evidence.

Final scoped results:

| Check | Result |
| --- | --- |
| Native KAR semantic and composed-negative tests | 8 passed |
| Existing native signature and codec neighbors | 7 passed |
| Unsigned Python key-authorization neighbors | 57 passed |
| CI selection contracts | 8 passed, 22 unrelated tests deselected |
| Existing signed fixture byte/signature checker | 14 cases verified |
| Scoped Clippy with `-D warnings`, Ruff and crate format check | Passed |
| Scoped diff whitespace check | Passed; existing CRLF notices retained |

This is 15 unique Rust tests and 65 unique Python tests. Semantic positives use
the existing unsigned registry-signing recipe and the unsigned transport recipe;
purpose 3 and purpose 14 cannot satisfy purpose 12. Exact start/expiry acceptance
and expiry+1 rejection preserve the reviewed inclusive contract. Composed tests
use four unchanged signed cases with their original supplied signer metadata;
valid signatures are demonstrated separately before semantic rejection. Corrupt
signature, wrong expected payload and wrong protected kid fail at the signature
boundary. The existing primitive neighbors cover envelope alternatives and
additional signature mutations. No keys or signatures were generated, including
during Python neighbor execution.

Independent `connector_model_review` examined the gate, tests, final CI selection
and scope documentation. It found no remaining scoped blocker. Its noted direct
purpose-14-to-12 coverage gap was closed with the existing unsigned transport
recipe. The missing successful composed-positive gate remains explicit and
requires separately authorized fixture materialization; semantic passes alone
do not close it. Hosted CI was not run.

## Resources and cleanup

The pre-build check measured 15,189,569,536 free disk bytes and 8,176,476,160 free
RAM bytes. The existing dependency cache was verified after the approved
incremental-cache cleanup. Every build used locked offline dependencies, one
build job and the existing supervisor: at least 8 GiB starting disk, 2 GiB RAM
reserve, stop below 6 GiB disk, stricter 256 MiB per-run disk-growth guard,
95-second work deadline and bounded cleanup. All ten supervised checks completed
without resource abort; every direct child was reaped. Final process inspection
found no cargo, rustc or selected test worker. No sockets or containers were
created. Small incremental outputs were naturally recreated by authorized
builds; the earlier approved cleanup record remains historical and unchanged.

Pre-existing benchmark binary warnings occurred during Cargo tests and are
retained in logs; scoped KAR Clippy passed. A read-only CIM RAM query was denied,
so the existing supervisor's `GlobalMemoryStatusEx` query supplied the guard.
One patch-format attempt was rejected before application; no partial edit was
applied. No downloads, production trust changes, security changes, unrelated
cleanup, commits or pushes occurred. All prior dirty work and evidence remain.
