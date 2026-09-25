# Native bundle runtime-worker diagnostic control

Cause motivating the experiment: retained split2048 failures show destination
roughly0.9-0.95effectiveguestcore in last5s, namespace receive-buffer errors in
some failures, and source-only allocation to two cores does not fix the workload.
Native affinity selection does not set the existing Rust benchmark runtime knob;
its omitted --p2a-runtime-workers defaults1. Do not infer all failures share a cause.

Expose an optional destination-only runtime_workers integer1/2/4, <=allocatedcores, for
bundle mode only. Omission preserves oldargv/evidence. Bind configuration through
CLI, controller, environment, exact peerargv replay and post-run requested/actual
checks. Reject explicit null/bool/invalid/oversubscribed values and sequential
cycles before launch. Use existing benchmark flag, noRust/security/wire/timerchange.

Literal RED command/config/replay tests, cycle rejection RED, affectedPython/Ruff,
one focused review. Preserve current failed cohorts. Commit and release build;
run fixed3trials withsourceCPU0+4/twoshards unchanged and destinationCPU2+6,
explicit2destination runtimeworkers. Keep2048,100offered/s,1skeepalive,memoryOFF.
All failures retained. Allocation+worker experiment is not physical scaling proof,
observer qualification or stable capacity. Recheck actual oldrelease replay.

Review ruling: source lifecycle branch ignores the outer worker flag and uses its existing fixed shard runtimes. Reject source explicit runtime_workers in config/workload/replay; destination only. Literal review regression RED before fix.
