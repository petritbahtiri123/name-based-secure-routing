# Catchable signal cleanup for the native endpoint controller

**MEASURED:** three source and three destination SIGTERM controls pass at release
source 3c3f784a. Each starts sixteen materialized bundles and reaches both active
barriers before signalling the Python endpoint controller, not its Rust child.
A same-UID probe checks exact argv and PID/start epoch, opens a pidfd, rechecks
identity and sends SIGTERM through that handle. No capability, security-policy
or production change is made.

The signalled controller records catchable cancellation and delegates owned
child kill/reap to the existing native runner. The other controller receives
EOF during coordinator cleanup. All six runs exit nonzero, reject positive
results, require no forced local relay termination and leave no owned measurement
executable visible in either namespace before fixture stop. These are successful
**negative controls**, not graceful eleven-counter ownership lifecycles.

Retained preparation failures precede the valid six-cell cohort: a helper named
`signal.py` shadowed the standard library before workload launch; Docker's default
address pools were exhausted; and a root-UID probe could not read a non-root
controller's `/proc/PID/exe`. The latter sent no signal and is not a valid SIGTERM
trial. Its endpoints were cancelled by EOF; sealed outputs were recovered from
the stopped, explicitly owned containers and verified. The corrected probe uses
the same UID 65532 as the controller. Two verified empty campaign networks were
removed to release their address pools, without changing host network policy.

`analyze.py` verifies indexes, exact targeted command/source, failure reasons,
nonzero exits and process absence. The raw driver retains the historical filename
`*-eof-result.json` for its bounded exit timing; `signal.json` and the error reason
identify the actual SIGTERM trigger. Real SSH disconnection, network partition,
host loss, SIGKILL and Windows TerminateProcess are not established by these tests.
