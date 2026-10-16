# Preserved task-2 benchmark fixes

These are sanitized reusable reference implementations, not a deployment bundle or authorization. All 29 Python candidates are retained (including the two previously published accounting files). Synthetic addresses use documentation ranges; aliases end in `.invalid`; the example account is `benchmark-user`. The old absolute checkout import now resolves the repository containing these copies. `make_commands.commands(prior_commands=...)` accepts explicitly supplied reviewed staging argv; its default staging entries are deliberately non-operational fixtures. The alias preflight has no import-time activity and its CLI is disabled.

Runtime functions still describe consequential actions and must not be called as a demo. External approval manifests, source inventories, dependency locks, payloads, baseline accounting records and SSH configuration are intentionally absent. Historical source pins are provenance, not proof that this publication checkout matches a sealed runtime. Existing limits and validation gates remain in the source. TLS generation/signing code is preserved for review; no credentials or certificate bytes are included, and these paths were not exercised.

## Fix and regression map

All paths below are under `scripts/performance/sphere_support/`.

| Fix | Implementation | Offline regressions |
| --- | --- | --- |
| Fresh single-pass file-size accounting; no cross-check cache; fail closed on errors | accounting.py, resource_boundary.py, bounded.py | test_accounting.py, test_cadence.py |
| Refresh Job accounting after observed leader exit; bounded exact-Job PID diagnostics | coherent_backend.py, diagnostic_backend.py | test_draining.py uses fake backend; real Win32 refresh is untested here |
| Two-second descendant drain capped by original deadline; observed empty proof, cancellation and termination failures retained | draining_owner.py, bounded.py | test_draining.py, test_proposed_grace.py, test_cadence.py |
| Login sudo invocation and nonroot system service boundaries, exact system cleanup | plan.py, remote_ops.py, make_commands.py, alias-preflight.py | test_system_revision.py, test_execution_gates.py; alias route requires separate runtime validation |
| Mountpoint creation intent, identity checks, no adoption or broad deletion | mountpoints.py, remote_ops.py | test_mountpoints.py |
| System-owned bounded TLS lifetime; original activation age, runtime-directory identity, public digest gates; fallback retained on failure | tls_lifetime.py, tls_roles.py, public_tls_sign.py, peer_guard.py, remote_ops.py | test_tls_lifetime.py, test_tls_contract.py, test_execution_gates.py, test_system_revision.py |
| Exclusive output parent preparation before endpoint parents=False creation | remote_ops.py | test_output_parent.py |
| Both capability gates, sealed input hashes, exact command allowlist and independent cleanup receipts | execute_step.py, plan.py, coordinator.py | test_execution_gates.py, test_system_revision.py |
| Bounded exact-commit source presentation, packaging and in-unit resource safeguards | sparse_source.py, package_review.py, peer_guard.py | Preserved source; no staging, packaging or live resource execution in this review |

## Verification

From the repository root: `python -B scripts/performance/sphere_support/run_offline_tests.py`.

59 tests passed on Python 3.14 on Windows. The runner rejects unmocked subprocess creation and socket access. Tests use fake clocks/backends, mocked subprocess calls and temporary filesystem fixtures; no SSH, VM, Docker, systemd, TLS key generation or signing was run. This is not validation of actual Windows kernel accounting, Linux namespace/systemd behavior, cryptographic issuance or network transport.

## Historical failures and exclusions

Earlier local drain failures remain failures: faster accounting improved observation cadence without proving that every child exited before the original half-second deadline. The later two-second tolerance remained capped by the original work deadline and did not make failed prior runs pass.

The earlier TLS attempt failed before native QUIC because a public certificate disappeared after session teardown; the exact unlink actor was not audited. The system-managed runtime directory avoids reliance on the user manager lifetime while retaining bounded expiry. A later command timeout happened before TLS setup and is not a TLS failure. Another trial proved TLS logout survival but failed before connection/measurement because the output parent was absent; exclusive parent preparation corrected that prerequisite. The final historical run was debug correctness only, not a capacity baseline. Independent absence receipts and generic supervision uncertainty are distinct evidence; missing cleanup must never be converted to success.

All 18 non-Python candidates are represented by safe labels and original digests in provenance.json and summarized here. Raw approvals, workflow instructions, infrastructure preflight, outcome/reconciliation records and historical reviews are not copied verbatim: they contain private deployment data or historical authority that must not become current authority. Originals remain unchanged privately. No raw auth/TLS material, inventories, patches, machine records, binaries, archives or caches are included. Publication of source does not authorize running operational helpers.
