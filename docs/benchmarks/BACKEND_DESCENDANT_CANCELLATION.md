# Windows descendant cancellation evidence

The existing100ms whole-operation timeout can complete before the Go helper
enters its descendant branch. A diagnostic startup marker remained absent.
Separate verified-executable preparation measured154.7001ms; stripping helper
debug symbols still measured135.3845ms and did not close the startup proof.
Pre-verification also failed to establish descendant startup within100ms.
These diagnostic changes were rejected and removed. The original helper,
production implementation,100ms timeout and750ms outer bound are unchanged.
Windows descendant termination specifically by that100ms deadline remains
INCONCLUSIVE, while the timeout return itself is tested.

A separate Windows cancellation test now waits for the existing marker written
only after `child.Start()` succeeds. It then cancels the pending operation,
requires the task to report cancellation and requires the descendant executable
image to become removable. Readiness and cleanup each have750ms bounds. The
test additionally requires total runtime after launch to be below the helper's
three-second natural exit, so spontaneous child completion cannot satisfy the
assertion. The ten-second operation timeout is the existing cancellation-test
configuration; it is not an extension of the100ms timeout test.

RED: blind100ms cancellation failed the started-descendant assertion.
GREEN: readiness-based cancellation passed. After focused review added explicit
natural-exit exclusion and unexpected-file-error reporting, both process-tree
tests passed in five fresh serial repetitions (10 test passes). Scoped Windows
release clippy with `--test demo_backend -- -D warnings` and fmt passed.
This is stronger test coverage; no production fix or security change was needed.

Raw diagnostics, rejected test snapshots and final test-source hash are indexed
in `evidence/performance/v2/descendant-cancellation-9f61f79f`. This is scoped local
Windows process cleanup evidence, not a general process-isolation/security proof.
