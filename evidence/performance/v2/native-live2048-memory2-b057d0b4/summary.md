# Native2048 two-worker memory cohort: partial observer failure

Two PASS_FUNCTIONAL trials and one FAIL_RETAINED/INVALID_PARTIAL trial at
releaseb057d0b4. Same2048livebundles/100offered/s/twosource shards CPU0+4,
destinationCPU2+6/twoworkers/1skeepalive, optional private-memory observer ON.
Two accepted pairs complete4096 roundtrips, both final eleven ownership counters
zero, owned PIDs absent. All6ownedPIDs absent across attempted cohort.

Third trial fails in destination resource observation: PermissionError reading
/proc/96/fd. Its raw server report has2048/2048samples, and source role independently
passes raw replay, but pair telemetry acceptance fails. This is an observer
failure, not proof of NBSR connection/admission failure or a security defect.
Do not replace failed validation with the server PASS field. Observer cleanup
race/permission cause needs focused diagnosis; no speculative fix this stage.

Only two valid complete pairs: minimum3repeat gate NOT_MET. Retained private/PSS
samples and driver phase medians remain diagnostic raw data; no qualified2048
memory scale/CV/isolated resource cost/allocator/soak claim. Separate observer-OFF
cohort remains3/3functionalPASS, not evidence of observer neutrality. Never discard
this unfavorable observation or blend it into a successful cohort.

Replay: `python -B evidence/performance/v2/native-live2048-memory2-b057d0b4/analyze.py C:/NBSR-build/native-live2048-memory2-b057d0b4`.
Replay binds exact mode/runtime/allocation/SHA/binary, successful raw peer outcomes,
failed role details and owned cleanup; no timeout/buffer/productionchange.
Next focused work: diagnose and RED/GREEN the /proc FD permission/exit observation
path, then fresh memory cohort. Fullcampaign still needs qualifiedobserver/soak,
isolated-resource attribution, externalhardware and finalclaimsfreeze.
