# Owned native memory observation during exit

Raw b057d0b4 memory2r3 destination traceback proves phase before_smaps invoked
strict sample_process while initial/rechecked same-epoch flags4194572 include
PF_EXITING. FD access disappears before stateZ. Normal owned monitor already
handles this transition; private-memory observer did not. All2048 destination
samples existed; this is observer invalidity, not a production throughput limit.

Add optional memory allow_exiting defaultFalse. Only owned CycleMemoryObserver
opts in; same PID epoch/affinity checks remain mandatory. Verified exiting or
zombie memory is unavailable/allNone, never zero or measured. Stop memory at the
exit gap; continue owned resource monitor until actualZ/exit0. Replay requires
PF_EXITING for gap, rejects any later memory record and still requires measured
live data and final owned lifetime/CPU bounds. No timeout/workload/securitychange.

2literalRED,2reviewRED; focused/affectedtests,Ruff,scopedreview. Commit/release,
then fresh2048memory2sameconfig3validrepeats/5ifresourceCV>5%;retainfailures.
Do not relabel previous invalidtrial asPASS. All memory remains diagnostic until
observer qualification; no isolated-resource or stable-capacity claim.
