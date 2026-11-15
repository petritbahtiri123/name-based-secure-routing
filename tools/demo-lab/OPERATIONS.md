# Local Demo Lab operational checklist

This checklist is for the development preview, not a production installer or
service deployment. Windows has local demo evidence, not clean-machine acceptance.
**Mac is prepared but untested; compatibility is unknown.** Its proposed runtime
is Mac host / Linux container, not a native Mac NBSR backend.

## Dependencies and setup gates

Use the exact reviewed commit in a full checkout of `codex/nbsr-v3-wp0-wp1`.
Record `git rev-parse HEAD` and `git status --short`; retain dirty-source hashes
when applicable. A moving branch or historical successful receipt is insufficient.
See [setup details](README.md#prerequisites-and-transparent-setup) for tool versions
and [Mac image preparation](container/README.md) for that separate workflow.

| Gate | Windows command from repository root | What success establishes |
| --- | --- | --- |
| Inspect | `python tools/demo-lab/demo.py check` | Preliminary source/tool inventory only; staging access is not probed |
| Review dependencies | `python tools/demo-lab/demo.py prepare` | A dependency plan; no downloads or compiled outputs |
| Fetch, only when authorized | `python tools/demo-lab/demo.py prepare --allow-downloads` | Locked dependency download attempt; no OS toolchain installation or warm compiler cache |
| Build, separately authorized | `python tools/demo-lab/demo.py build` | Offline bounded compilation and retained build manifest/logs; no live acceptance |
| Open dashboard | `python tools/demo-lab/demo.py serve` | Authenticated loopback UI; no scenario success implied |
| Verify completed run | `python tools/demo-lab/demo.py verify --run-id demo-<32-hex>` | Local receipt/artifact consistency, PASS and CLEAN when exit code is zero; not third-party attestation |

Use the exact run ID printed by the dashboard, replacing the placeholder. Check
exit codes after every stage and stop on failure. `check` returns 2 when preliminary
build admission fails. On Mac it deliberately keeps `ready_for_build` false;
image selection/assembly and real host acceptance remain separate gates. Use
`python3` on Mac and follow the container guide rather than host `prepare`/`build`.

The Python dashboard uses the standard library. Existing pytest is needed only
for component checks; existing Node.js runs the dependency-free UI regression.
Do not confuse installing the repository's Python package with preparing the
Go/Rust demo binaries. Do not silently install tools, fetch dependencies, change
execution policy, or extend a failed build's resource/time limits.

## Start, observe, stop

1. Confirm no benchmark, collector, historical demo, or other Demo Lab run will
   overlap. Reconcile any prior run by exact process/receipt identity before start.
2. Keep the launch terminal open. Keep the bootstrap URL/token private. The UI
   listens on loopback only; do not expose or proxy it as a public service.
3. Start one fixed scenario. Treat allowed Service A as a live attempt; the named
   negative/isolation scenarios are fixture regressions. A responding dashboard,
   HTTP CONNECT 200, or completed build is not application readiness.
4. Accept a scenario only with its required assertion, PASS, CLEAN and successful
   independent verification. Service A requires the exact application payload,
   destination PASS and backend request count 1 described in the README.
5. Use **Cancel** to request cancellation of owned work, and **Stop Demo Lab** to
   stop the dashboard. A cancellation request is not proof of completed cleanup.
   Closing a browser tab does not cancel a run. Preserve failed/cancelled receipts.
6. If disconnected, timed out, or cleanup is UNCONFIRMED, reconcile the UI PID,
   owned run identities and receipts before restarting. Do not replay a POST or
   remove a stale lock to force progress. There is no general CLI stop command;
   do not replace owned cleanup with a process-name kill.

If opening the browser or starting the dashboard expiry thread raises an error,
the launcher closes its HTTP socket before attempting coordinator shutdown, so a
slow coordinator does not retain the listener. Coordinator cleanup is still
attempted if socket closure raises. Errors still propagate;
this is not proof that a scenario's child processes were cleaned up. Preserve
unresolved-run markers and use the reconciliation procedure below before restart.

The coordinator's worker join waits up to the remaining cleanup budget (capped at
120 seconds); this is not a
whole-process exit guarantee. A surviving non-daemon worker can keep the process
alive. If the worker is still alive after that wait, shutdown raises a cleanup-
uncertain error and the launcher reports failure (code 2), retaining `ui.lock`.
That return code does not force interpreter exit while a non-daemon worker survives.
The coordinator does not erase `active.json` on timeout; a later worker result can
still record its actual cleanup outcome through the existing receipt path. The
retained UI lock still requires owner reconciliation before restart.

An exception or Ctrl+C during the worker join or subsequent liveness inspection
also reports cleanup uncertainty and retains the UI lock. The original exception
is chained for diagnosis, but its raw text is not included in the normal CLI error.
This does not handle every possible interruption point or force a worker to stop.
Reconcile ownership even if the worker finishes after the failed observation.

On entry to the dashboard cleanup block, a single monotonic deadline is set
120 seconds ahead. After signaling expiry stop and closing the listener, the
coordinator receives that deadline. The expiry thread is then joined for at most
one second, capped by the remaining budget, even when coordinator cleanup raises.
A surviving expiry thread or failed/interrupted join/inspection reports cleanup
uncertainty and retains UI ownership. An attempted thread start that cannot be
confirmed stopped is also uncertain; do not remove its lock to retry.

This bounds requested join waits, not total process lifetime or all blocking code.
It starts at cleanup entry, not the shutdown button or initial cancellation. Socket
closure and arbitrary coordinator code are not forcibly preempted. Every HTTP
shutdown helper is retained before its start attempt and joined after expiry
cleanup, even when that cleanup fails. Each helper gets at most one second within
the same remaining budget. All helper waits/inspections are attempted; survivors,
unstarted helpers, or failed/interrupted observations retain UI ownership and
report cleanup uncertainty. Multiple helper failures remain chained together for
diagnosis. The first authenticated shutdown request still receives 202 when helper
start succeeds. Once a helper reference is retained, further shutdown requests
receive 409 and create no new helper, including after a failed start. The one
reference is never discarded to permit retries; reconcile ownership before a new
session. Authentication and exact Host/Origin checks happen before this admission.
No automatic kill, forced lock removal, or successful workload-cleanup claim follows
from listener closure.

## Read-only recovery triage

Run `python tools/demo-lab/demo.py status` (Mac: `python3`) before investigating
an interrupted session. It reports only the presence of the dashboard lock,
unresolved-run marker and historical-demo lock. It never reads their contents,
contacts the dashboard, probes processes, starts work, or removes state.

Exit 0 means all three markers were absent at inspection time. Exit 2 means at
least one is PRESENT or UNKNOWN (including unsafe paths or inspection errors).
Neither result proves liveness, cleanup, ownership, build readiness or absence of
other workloads; the snapshot can race concurrent changes. Reconcile exact owner
identities and retained receipts before restart. Do not delete locks based on this
report. This command does not turn Mac's untested adapter into accepted support.

## When Stop fails or cleanup remains unconfirmed (Windows)

A `202` response accepts a shutdown request; it does not confirm process exit.
A first helper-start failure can return `409` after scenario cancellation was
requested. The listener may still be running. Once the helper reference is
retained, another Stop request returns `409` without another start attempt.
Neither response proves that owned work stopped. Do not repeatedly press Stop,
replay its POST, launch another dashboard, or start another scenario to test it.

1. Keep the launch terminal and the original error available. Record the exact
   checkout/HEAD, time, displayed scenario/run ID and whether the UI is connected.
   Distinguish the HTTP response from the terminal's later shutdown/cleanup error.
   A terminal message saying `Demo Lab stopped` with cleanup uncertainty is not
   evidence of process exit; the shell may not have returned yet. Do not wait an
   arbitrary 120 seconds and infer success. Keep the private bootstrap URL/token
   and raw runtime credentials out of notes intended for sharing.
2. From a separate terminal in the same checkout, run the existing read-only
   commands below. Capture `$LASTEXITCODE` immediately after Python, before another
   native command can replace it; preserve both outputs.

   ```powershell
   python tools/demo-lab/demo.py status
   $LASTEXITCODE
   ```

   PRESENT means a marker exists, not that its owner is alive; UNKNOWN is not
   absence. If paths are inaccessible or unsafe, stop that inspection rather than
   changing permissions or following alternate paths to force a result.
3. Inspect only the relevant local records below when accessible. They supply
   identifiers for reconciliation, not authority to remove a lock. Preserve the
   files and their original contents, including failures.

   | Record (repository-relative) | What it can establish |
   | --- | --- |
   | `tools/demo-lab/.state/ui.lock` | Recorded UI `pid` and `purpose`; no process creation time or proof that the PID still identifies the same process |
   | `tools/demo-lab/.state/active.json` | Recorded run ID and scenario when the unresolved-run marker exists |
   | `tools/demo-lab/.state/runs/<recorded-run-id>/receipt.json` and selected `process/` logs | Retained scenario evidence, when written; an early failure may leave no receipt |
   | `client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/active.lock` | A separate historical-demo marker requiring its own owner reconciliation |

4. For the recorded UI PID only, an existing Windows observation is
   `Get-Process -Id <recorded-ui-pid> | Select-Object Id, ProcessName, StartTime, Path`.
   Replace the placeholder with the PID actually recorded in `ui.lock`. Compare
   available observations with the original launch terminal and known launch
   identity. PID reuse, missing properties, access errors, or no matching process
   leave gaps; a generic process-name scan does not fill them. The UI PID does not
   identify every scenario child process or prove their cleanup. If the original
   identity cannot be established, keep ownership unresolved.
5. If the exact run ID is known, replace the placeholder with that recorded ID
   and capture the verifier output and exit code immediately:

   ```powershell
   python tools/demo-lab/demo.py verify --run-id <recorded-run-id>
   $LASTEXITCODE
   ```

   Do not select an unrelated latest or historical PASS. A
   missing/incomplete receipt is not CLEAN. A later verified PASS/CLEAN concerns
   that scenario's recorded evidence; it does not certify the UI helper's exit or
   authorize removing `ui.lock`. A failed/cancelled scenario can also require
   separate inspection of its recorded cleanup outcome.
6. Hand off the observations to the run owner/maintainer using the
   [verified handoff template](../../docs/agents/HANDOFF.md): source identity,
   recorded owner/run IDs, original failure, marker observations, verifier result,
   and unresolved identity/cleanup gaps. Include selected redacted observations,
   not a dump of private runtime directories. If the UI PID is gone but its lock
   remains, preserve that fact rather than interpreting it as permission to reset.

There is no implemented CLI `stop`, `unlock`, or `reconcile` command. This checklist
collects evidence; it does not supply an automatic recovery or lock-removal step.
Keep failed receipts and ownership markers until the owner has resolved the exact
resources and authorized a separate recovery action. Do not delete locks, kill by
process name, change network/security settings, or regenerate fixtures as a retry.
Windows observations here do not establish clean-machine acceptance. Mac remains
prepared but untested; these Windows commands are not a Mac recovery procedure.

## Lightweight regression checks

With an already provisioned environment, these checks need no Go/Rust build or
live scenario. Run from the repository root:

```text
python -B -m pytest -q -p no:cacheprovider tools/demo-lab/tests/test_http_shutdown_helpers.py tools/demo-lab/tests/test_expiry_cleanup.py tools/demo-lab/tests/test_shutdown_uncertainty.py tools/demo-lab/tests/test_web_lifecycle.py tools/demo-lab/tests/test_status.py tools/demo-lab/tests/test_app.py tools/demo-lab/tests/test_windows_setup.py
node tools/demo-lab/tests/test_ui.cjs tools/demo-lab/static/app.js
```

The broader component command is documented in the README. Its HTTP boundary test
uses loopback and a fake coordinator. Component tests do not establish clean-machine
installation, real Mac support, live transport success, capacity or production
readiness. Record the exact tested source, environment, commands and failures.
