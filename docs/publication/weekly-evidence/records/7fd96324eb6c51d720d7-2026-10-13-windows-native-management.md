# Windows-hosted management: offline implementation checkpoint

Approved scope: Windows management implementation with deterministic offline
tests, plus read-only inspection of known artifact metadata/public certificates.
No management container, daemon socket delegation, Docker operation, live traffic,
native process-fault trial, credential generation, private-key inspection, build,
download, settings change or publication occurred.

## Implementation

`scripts/performance/windows_native_management.py` supplies an exact-handle
Windows owner, a shared cell budget, bounded engine adapter, exact-container-ID
config binding, worker entrypoint, and a workload callable for the existing
`local_container_sequence.Sequence`. The host coordinates both endpoint roles;
only Linux endpoint containers are needed. Worker configs replace symbolic
management hosts with independently recorded immutable container IDs. Other
workload/source/TLS fields remain intact. The Windows host output directory is
separate from endpoint outputs; Linux recipe paths are not used as host paths.

`windows_job_backend.py` binds Win32 through ctypes: unnamed kill-on-close Job
Object, no handle inheritance, suspended process creation, assignment before
resume, exact-handle observation, and termination of either the owned job or a
still-unassigned suspended process. No breakaway or permission fallback exists.
The worker opens its own scoped logs. Process exit259 is distinguished from an
active process using the signalled process handle. Reaping requires the leader
exit and zero active job processes; failed close retains the corresponding handle.
This native binding was tested only through fake kernel functions, never against
real Windows jobs. It is not live containment proof.

The existing finite coordinator still runs its Manager, ledger, archive, endpoint,
pair, source/build and post-close validators. Its optional validated-event hook
runs only after ledger acceptance and telemetry forwarding. The worker's deliberate
interruption requires positive completed transport progress in the existing paired
telemetry mode. It cancels management at a safe point and requires the coordinator's
matching INVALID_PARTIAL failure. This is not a hard process crash or proof that
both configured streams had already completed work. Normal and fresh cells still
require the complete existing transport validators.

The existing watchdog accepts an optional original `started_at`; default behavior
is unchanged. `BudgetedEngine` starts the cell clock before creation, and the
Windows workload uses that same epoch. Work stops at95s; cleanup ends at120s.
Engine calls receive remaining time, and their outcomes are checked again after
return. Late absence cannot release ownership. The concrete engine must bound its
own calls and cleanup; a blocked kernel/engine call cannot be made preemptible by
this Python contract.

Deferred catchable cancellation protects acquisition and supervision. Unexpected
exceptional exits attempt immediate exact-owner termination/reap with no new wait
budget, preserve errors and retain handles when confirmation fails. Local worker
completion never proves endpoint disposal. Request-hash-bound replies must match
the exact current invocation; the original two-receipt disposal gate remains the
only route to the next cell. These hashes/object bindings are local misuse guards,
not signatures or hostile-process authentication.

## Validation and retained failures

Final scoped run: **135 passed** (32 new plus103 existing checks),2.83s pytest,
4.22s supervised. Ruff passed. The test child was reaped and no guard aborted.
Final test disk13951213568 bytes; available RAM7082921984 bytes. Python3.14.6
remains a focused permitted-version result, not a full compatibility matrix.

New checks include fake Win32 call ordering/flags, startup and handle-close
failures, exit259, unassigned child retention, whole-job absence, cancellation,
deadline reuse/overrun, exact IDs/replies, real Manager rejection before hook
delivery, and composed normal/interrupted/fresh plus failed-disposal gating.
No fake outcome is counted as real QUIC exchange or actual Windows Job Object proof.

Retained RED runs:13 missing-adapter failures;6 missing-composition failures
with13 passing;2 missing-native-binding failures;6 missing-runner/retained-handle
failures;1 late-disposal failure with2 passing;2 cancellation failures. The latter
cancellation gap was identified by independent review. All raw failures and
successors remain in the dated local-handoff evidence bundle.

Focused verification:

```sh
python -B -m pytest -q -p no:cacheprovider \
  tests/performance/test_windows_native_management.py \
  tests/performance/test_windows_job_backend.py \
  tests/performance/test_local_container_disposal.py \
  tests/performance/test_local_container_sequence.py \
  tests/performance/test_linux_native_finite_run.py \
  tests/performance/test_linux_native_watchdog.py \
  tests/performance/test_linux_native_cleanup_failures.py
```

Windows used a fresh test-owned writable `--basetemp`. Existing fixtures and
historical evidence were preserved. Original dirty repository sources were not
edited; source changes remain in the isolated handoff.

## Public artifact inventory and blockers

Read-only inspection of the known handoff records located only placeholder native
authority/build paths, not an exact retained public certificate set or Linux
release manifest. **No usable existing fixture set is established.** Consequently
no actual public certificate fingerprint, validity dates or matching runnable
binary inventory can be reported.

Source recipe `scripts/performance/authority.py` generates random P-256 private
test credentials and random certificate serials, with SANs source.edge and
destination.edge and one-day validity. It does not establish an actual retained
set's identity or current validity. These test keys are not automatically public
deterministic fixtures. No private-key contents were read, hashed, copied, mounted
or transmitted. Public metadata inventory does not authorize future key use.

Before any local rehearsal: identify a clean reviewed peer source and matching
existing Linux release manifest/hashes for all three required binaries; locate
approved unexpired role-specific TLS fixtures and original compile-time fixture
paths; verify the cached runtime and host/guest resources. Missing/expired inputs
remain blockers without generation, downloads, builds or bypass.

## Remaining implementation/validation gate

The concrete independently observing Docker provisioning backend is still supplied
through the explicit engine interface, not implemented by this Windows slice.
It must provide exact-ID create/inspect/remove and honor each passed remaining
budget. Live engine inspection, resource guards, mounts, network selection and
fixture custody must be wired/reviewed before execution. The native Job Object
binding also needs separately authorized live validation; these offline results
cannot replace it. No live runner command is approved by this document.

Later authority must explicitly cover the exact two-container internal topology,
role-specific private test-key mounts, real two-stream QUIC workload, deliberate
management interruption, bounded native containment checks and exact cleanup.
No daemon access is delegated into a container. A process-only check, if needed
for native containment, remains separate from transport-integration evidence.
SPHERE/bare-host disposal, production authority, durable controller recovery,
transparent resumption and performance capacity remain outside this result.
