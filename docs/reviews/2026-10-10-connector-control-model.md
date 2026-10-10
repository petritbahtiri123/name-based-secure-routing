# Connector control model — 2026-10-10

Approved scope: deterministic mock-only one connector/service/gateway; no real
network, keys, credentials, persistent access, wire IDs, frozen authority edits,
deployment, commit, push or bypass. Identity check: laptop PETRIT, workspace
`C:/Users/bajra/OneDrive/Documents/NBSR`, branch `codex/nbsr-v3-wp0-wp1`, base
`fb587d76fe2cf691a9caa9c278f4db4da46298b4`. Existing unrelated dirty work preserved.

## Implementation and result

`nbsr/connector_control_model.py` is isolated from runtime entrypoints. It models
exact binding verification, owner/session-bound acceptance, one live slot,
permission-capped lease and renewal, expiry/revocation, fresh reconnect,
bounded retry count/delay, and conditional old-owner cleanup. It uses injected
fakes, serialized method calls and explicit poll; it neither edits nor drives
the frozen ConnectorState map. Close failure withdraws eligibility but retains
visible ownership and halts retry, rather than claiming zero cleanup.

Final supervised command:

`python -m pytest -q -p no:cacheprovider tests/test_connector_control_model.py tests/protocol/test_states.py`

**62 passed: 49 model + 13 existing frozen-state tests; zero skips.** Pytest
reported 0.72 seconds; supervisor elapsed 2.01 seconds. Python 3.14.6 / pytest
8.4.2 are already provisioned. This permitted Python version is not evidence of
the entire documented version matrix. Focused Ruff check and format check pass.
No full repository suite, Rust build, live network or hosted CI ran for this slice.
Scoped checks follow AGENTS.md rather than the generic skill's broad-suite advice.

## Retained attempts and independent review

| Run label | Outcome |
| --- | --- |
| connector-model-red | 1 setup error: missing-module assertion was in a fixture; no implementation yet. |
| connector-model-red-corrected | 1 expected failure: missing model assertion moved into a test. |
| connector-model-green | 42 tests pass; initial format check then reported two files needing formatting. |
| connector-model-boundaries-red | 3 fail / 1 pass / 42 deselected: renewal returned bool instead of fresh ticket, duplicate same transport closed owner, stop used stale backoff timestamp. |
| connector-model-cleanup-red | 2 fail / 46 deselected: throwing/no-op close lost ownership accounting. |
| connector-model-boundaries-green | 61 pass including 13 frozen-state neighbors after corrections and formatting. |
| connector-model-renewal-red | 1 fail / 48 deselected: clock samples 17 then 18 renewed a ticket expiring at 18. |
| connector-model-final | 62 pass after renewal commit rechecks expiry. |

Independent reviewer `/root/connector_model_review` reproduced the stale backoff,
duplicate transport and failed-close ownership bugs. The reviewer then found the
two-clock-sample renewal boundary; each received a focused regression and fix.
Final disposition: all four findings resolved by inspection, no remaining blocker
within mock scope. Reviewer did not rerun the final suite; execution evidence is
the implementing worker's retained logs. Failed attempts were not discarded.

## Limits and evidence

All C01–C16 topics are mapped in the profile's follow-up, but none is presented as
full wire/runtime acceptance. No cryptographic proof, real control exchanges,
async cancellation, frame/credit bounds, concurrent threads, persisted authority
floors, production revocation delivery, package preflight or application relay
was established. Test numbers are explicit fixture inputs, not protocol defaults.
Public model objects are not an adversarial Python object boundary. Dependencies
are non-reentrant fakes. Model renewal is an atomic event, not an ACK protocol.

The supervisor used a 95-second work deadline, >=8 GiB disk start, 6 GiB floor,
stricter 256 MiB disk-growth guard and 2 GiB RAM reserve. Every run reaped its
direct child and none hit a guard. Final test disk stayed 12,379,664,384 bytes;
available RAM at end was 4,603,019,264 bytes. No model subprocesses or containers
are created. Command-line process inventory via CIM was denied by this environment;
its apparent zero count was therefore not accepted as evidence. A subsequent
Get-Process enumeration found zero visible Python processes. Direct-child reaping
is separately confirmed by every supervisor record; no Docker operation occurred.

Logs and supervisor JSON are retained under
`evidence/connector-control-model/2026-10-10/`; their hashes and exact changed-source
hashes are in the adjacent report JSON. Baseline SHA alone does not identify these
uncommitted files. Stage 1 is partial: mock slice complete, identity/wire/state
integration and numeric policy decisions still review-pending. No package
milestone or production-readiness claim is made.
