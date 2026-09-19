# Resistant capture-child cleanup

At 4d3bbb45 a fault-injected owned child ignoring SIGINT and SIGTERM survives
the capture context's 10-second then 5-second shutdown waits. The live RED
retains matching PID/start identity before and after the raised TimeoutExpired;
the experiment then kills/reaps only that fixture child. This is a surviving
owned child after failed cleanup, not evidence of a real dumpcap hang in a
benchmark. A second unit RED proves the stderr handle is left open on failure.

72b7295b adds final kill/reap after failed graceful/terminate waits and closes
stderr in finally, including final reap failure. Existing stop waits and all
benchmark/protocol deadlines are unchanged. Forced cleanup always leaves
capture validity false; it never accepts a partial trace as valid.

38 focused packet/readiness/cleanup tests PASS. Ruff has zero findings before
and after; diff check PASS. Three Linux fault-injection GREEN repetitions kill
and reap the resistant child, leave no owned PID, preserve invalid capture status,
and return to the original controller FD count. No production implementation,
security semantics, performance number or packet-accounting result changes.
