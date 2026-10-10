# Connector active-work mock extension — 2026-10-10

User approved one simulated request with mode-specific enforcement. No network,
credential, real authority, wire registry, pinned source, deployment, commit or
push changes. Base fb587d76fe2cf691a9caa9c278f4db4da46298b4 on
codex/nbsr-v3-wp0-wp1. Unrelated dirty work preserved.

## Result

One in-memory ActiveWork is admitted only through a ready owner and existing
permission. Deny-new blocks registration/confirmation/renewal/new work and
reconnect while retaining the already authorized fixture until completion or
its unchanged deadline. Terminate cancels it; failed cleanup retains visible
ownership until a successful close. Repeated/stale events cannot downgrade
termination or remove a successor. Exact federation enum types are required.

Admission requires an explicit lease_bounds_active fixture boolean; tests cover
both lease-capped and separately bounded work. Permission always caps lifetime,
and renewal never extends the active fixture. This does not settle the real
lease-versus-active-work policy. Legacy verifier None still means immediate
cancellation, not typed deny-new or outage-preservation. Events are already-
verified fakes; no real event parsing, authentication, scheduling or persistence.

## Tests and retained failures

Command: `python -m pytest -q -p no:cacheprovider tests/test_connector_control_model.py tests/protocol/test_states.py tests/federation/test_revocation.py`

Final: **109 passed, zero skipped** (72 model, 13 frozen state, 24 federation
revocation). Pytest 0.98 seconds; supervised elapsed 2.21 seconds. Provisioned
Python 3.14.6/pytest 8.4.2; not a full version-matrix or repository-suite claim.
Ruff check and final format check pass; initial format check required two files
to be reformatted. Diff check passes with existing CRLF conversion warnings.

| Retained run | Outcome |
| --- | --- |
| connector-active-red | 15 failures / 50 deselected: active-work/enforcement APIs absent. |
| connector-active-finish-red | 1 failure / 64 deselected: absent active-work API for early completion. |
| connector-active-green | 102 pass, before independent-review boundary additions. |
| connector-active-boundaries-red | 7 failures / 65 deselected: matching revoke lost at cleanup boundary (six variants), and late renewal wrongly cancelled independently bounded work. |
| connector-active-final | 109 pass after both fixes. |

Independent reviewer `/root/connector_model_review` reproduced both defects.
Enforcement now matches/latches before polling can remove the owner; late
renewal shares normal registration-expiry/draining behavior. Final inspection
confirmed both fixes with no remaining blocking findings in the narrow scope.
Reviewer did not rerun final tests; execution evidence belongs to this worker.

## Evidence and limits

Five bounded runs retained under `evidence/connector-control-model/2026-10-10/`;
adjacent JSON records exact commands, source/log hashes and results. Every direct
child was reaped, no guard aborted. Final test disk stayed 12,348,686,336 bytes;
RAM at completion 5,052,891,136 bytes. Supervisor uses 95-second work cutoff,
8 GiB start/6 GiB disk floor, stricter 256 MiB growth guard and 2 GiB RAM reserve.
Get-Process found zero visible Python processes after checks; no containers were
created. No downloads or global changes. Historical manifests/logs preserved.

Tests prove serialized model behavior only. No concurrent stream cancellation,
real cleanup, revocation-signature validation, future-effective delivery, durable
tombstones, restart-proof revocation or product readiness is established. The
profile now records exact partial B-case coverage; stage 1 and 0/10 package
milestone completion status remain unchanged. No broader tests were justified
for this isolated mock slice.
