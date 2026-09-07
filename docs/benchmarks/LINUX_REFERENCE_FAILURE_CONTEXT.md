# Linux finite reference failure context

2026-09-07; parent ba8c93472969d8ecf13dac2b3322694e209d1d2d.

The retained edc0f96d third NBSR reference attempt failed with PermissionError
at /proc/230/fd. The sampler already attaches initial/rechecked process identity
and state as exception notes. The finite runner formatted only str(error),
discarding those notes. This is a proven diagnostic evidence loss, not an
attribution of the original permission failure.

Reuse the existing bounded failure_details helper: exception type, message,
traceback and terminal notes, with no local-variable dump. Successful sampling,
workload, timeout, cleanup and invalid-result rules remain unchanged.

RED: two injected source telemetry failures failed with KeyError: error_type.
GREEN: 97 tests passed across test_linux_b5_reference.py,
test_linux_failure_context.py, test_linux_sampler_zombie.py and
test_linux_resources.py. Ruff on the changed Python files and git diff --check
passed. Focused diff review confirmed that failed source sampling still prevents
completion ACK and retains the failed record and cleanup artifacts.

Next: use retained release binaries with explicit old-binary/new-harness binding
for a DIAGNOSTIC reproduction. Capture nonreaping child exit correlation only
after a failure. Never promote this diagnostic to a qualified reference or
replace the original invalid attempt.
