# One process-only diagnostic

Helper PID1268 matched GetProcessId on retained process handle584 and the helper's own receipt. Job568 and thread580 were exact retained handles. Work cutoff6.019s; total6.041s. TerminateJobObject returned successfully.

The first raw cleanup sample observed PID1268, ActiveProcesses0, WAIT_TIMEOUT258 and no exit code. Production owner.observe separately rejected the pair; this rejection is retained. The next raw sample observed the same PID, ActiveProcesses0, WAIT_OBJECT_0 and exitcode1. Normal owner.reap then independently rechecked completion and released all three handles. No retained ownership remains. Raw native API start/end times and results are in result.json; exact deltas in summary.json.

This proves a transient unsignalled-helper/empty-Job observation during this specific process-only termination. It does not establish that the earlier Docker helper would have completed within its reserve or explain Docker creation delay. Production rejection logic remains unchanged; historical UNCONFIRMED outcomes remain intact.

Offline4tests passed and Ruff passed. Independent review corrected missing deferred Cancellation before the run and cleared the revised diagnostic. Initial missing-module test failures and E402 lint failure retained. No production file edits, Docker, network, downloads, builds, credentials, commit or push. The only live action was one finite Python helper and exact owned cleanup.
