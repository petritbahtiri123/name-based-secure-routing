# Windows durable-run descendant containment

2026-09-25; bounded benchmark-only reliability repair.

Measured defect: full performance-suite failure retained a Windows child PID
while the durable manifest reported cleanup_verified=true and listed only the
parent. A focused real Windows regression additionally proves that a successful
parent can leave a live descendant while authoritative_pass_eligible=true.
Do not infer the precise scheduling cause from the old snapshot alone.

Design: create an unnamed kill-on-close Job Object; create the owned benchmark
parent suspended, assign it to that job before resuming its sole initial thread.
Keep the job handle non-inheritable. Descendants inherit job membership; no
breakaway permission is enabled. Terminate and query the owned job for zero
active members rather than claiming cleanup from one PID ancestry snapshot.
Normal parent exit with leftover descendants is a failed run, even if forced
cleanup succeeds. All error paths fail closed and close owned handles. Existing
workload deadlines, record reconciliation, Linux process-group behavior, protocol
and transport/security implementation remain unchanged.

Validate literal RED -> live Windows GREEN, startup/assignment/resume failures,
timeout descendants, normal completion, bounded teardown, test readiness outside
the unchanged 0.4s timeout, Ruff and one focused independent review. Preserve the
original failed suite and focused RED. No global job/security policy changes.

Microsoft reference: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
This is containment for ordinary benchmark descendants using CreateProcess,
not a sandbox for malicious WMI/service-launched processes. The suspended-start
approach has a narrow controller-crash-before-assignment window; controlled
exception paths terminate the suspended child. No crash-proof launch claim.

Verified: three focused containment/error-path RED captures, then 41 affected tests PASS; Ruff PASS; actual Linux completed/timeout process-group smoke PASS. Independent Windows containment review clean. Three fixture-startup RED failures now use explicit readiness before the unchanged 0.4s deadline; a separate unprepared-child regression retains the original deadline behavior. No production timing change. Raw checksummed tests: C:/NBSR-build/windows-durable-job-tests-20260925. Full-suite initial failures and follow-up are retained separately in quality-be07f67c-20260925.
