# Opt-in local trial watchdog

This is a local containment aid, not remote cleanup proof. It adds one outer owner
around the unchanged finite or lifecycle coordinator and its existing admission,
retained-evidence and cleanup validators. It never converts an invalid worker result
to PASS. The supervisor's strongest status is LOCAL_WORKER_COMPLETED, with both
local_cleanup and remote_cleanup still UNCONFIRMED. A nested worker result alone
must not override a watchdog INVALID_PARTIAL or missing final result.

On an explicitly authorized Linux host, from the source checkout:

```text
python -B -m scripts.performance.linux_native_watchdog --mode finite --config /approved/config.json --output /approved/new-evidence --original-disk-free-bytes ORIGINAL_BASELINE
```

Replace ORIGINAL_BASELINE with the previously retained original free-byte count;
never reset a cumulative budget to retry. This is documentation, not authorization
to execute the command. Mode lifecycle is also supported. The synthetic October12
configuration is not a live target. Long diagnostic durations and other modes are
rejected; existing raw CLIs remain available and are not covered implicitly.

The fixed monotonic schedule is INT at100, TERM at105, KILL at110, stop waiting at120
seconds from just before worker startup. Early cancellation, worker failure, resource
pressure or partial startup begins this cleanup schedule immediately. A returned
startup call or delayed scheduler beyond120 still triggers an immediate owned KILL
attempt and returns uncertainty without new waits. Repeated cancellation never
restarts grace. Observe uses waitid(WNOWAIT); the leader stays unreaped until the
last group snapshot, preserving its PID/PGID against reuse while signalling. Existing
worker threads and relay subprocesses normally inherit that session. No remote PIDs
are signalled. No arbitrary command/module selection is exposed.

stdout/stderr go to files, not parent pipes. Startup uncertainty is written before
creation; final status and bounded stage/type errors are written separately. Existing
worker evidence remains under worker/. Signals target only the owned process group;
resource failure is retained. Group-snapshot observation includes zombies and retains
uncertainty on access errors; leader reap is separate from the snapshot result.

Limits: process creation, filesystem/proc operations, uninterruptible kernel waits
and scheduler starvation can exceed userspace deadlines. Final evidence writes also
can stall: no unconditional 120-second wall-clock guarantee is claimed. /proc scans
are non-atomic and mount visibility can hide members; escaped sessions and parent
death are not contained. Retaining the leader prevents a PGID-reuse race during
escalation, but does not authenticate remote ownership. At the offline implementation checkpoint, tests used injected
handles and clocks only; no Linux child/session/signal test had yet run. Separately retained October 13 evidence records six accelerated-clock real Linux
process cases; that evidence is outside this narrow source snapshot. Those cases do not close
the general containment, remote cleanup or unconditional real-time gates above.

Next gates: review the gaps remaining after the six accelerated process cases;
separately authorize any justified additional or full-duration validation. Review
stronger containment/parent-death requirements if needed; specify fresh,
run-bound remote cleanup evidence and separately authorize actual host/SSH/TLS/build
provenance before any live network trial. No trust, signature or deployment change
is included. Exact commands and results are retained in that external evidence.
