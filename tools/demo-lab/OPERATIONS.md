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

The coordinator's existing worker join waits up to 120 seconds; this is not a
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

The expiry daemon is signaled to stop but is not joined. There is not yet a shared
whole-shutdown deadline. No automatic kill, forced lock removal, or successful-
cleanup claim follows from listener closure.

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

## Lightweight regression checks

With an already provisioned environment, these checks need no Go/Rust build or
live scenario. Run from the repository root:

```text
python -B -m pytest -q -p no:cacheprovider tools/demo-lab/tests/test_shutdown_uncertainty.py tools/demo-lab/tests/test_web_lifecycle.py tools/demo-lab/tests/test_status.py tools/demo-lab/tests/test_app.py tools/demo-lab/tests/test_windows_setup.py
node tools/demo-lab/tests/test_ui.cjs tools/demo-lab/static/app.js
```

The broader component command is documented in the README. Its HTTP boundary test
uses loopback and a fake coordinator. Component tests do not establish clean-machine
installation, real Mac support, live transport success, capacity or production
readiness. Record the exact tested source, environment, commands and failures.
