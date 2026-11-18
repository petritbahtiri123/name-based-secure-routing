# Reader adapter candidate: offline contracts only

This candidate packages five reader adapters with regression tests in the existing
`python-core` / `reader-lifecycle` CI command on both platforms. Imports do not
launch a benchmark, a listener, or a native process. These helpers are not yet
wired into an approved campaign launcher.

## What is tested

- FinalCapture uses the real Performance Lab frame parser and verifies retained
  capture bytes, identities and hashes; mutations invalidate the capture.
- ReaderHandoff binds closure and settlement to an owner and deadline.
- ReceiptPair shares a bounded claim for closure, settlement and acquisition
  result publication and verifies retained evidence before later acceptance.
- ReceiptBarrier rejects mismatching supervision, invalid identities, failed
  callbacks and invalid POST evidence. Failures remain latched.
- ReaderLauncher connects acquisition, closure, settlement and POST consumption.
- The composed regression uses the real parser, acquisition, capture and receipt
  implementations, but an injected owner and synthetic POST evidence. It tests
  valid lifecycle completion and rejection of an over-90-second POST span,
  changed capture and failed aggregate claim.

## Explicit limitations

A completed reader lifecycle is not a valid scientific benchmark. Native process
containment, real command-wrapper integration, cross-process writer ownership,
full campaign peak accounting, actual calibration and endpoint cleanup still
require separate qualification. The composed test does not prove those gates.
No campaign is enabled, no dashboard is created and no historical run is changed.
The existing Performance Lab remains the single user dashboard on port 8765.

The source was promoted from the reviewed task-local offline adapter candidate.
Only package imports were changed in the five modules. Tests were made portable
and use repository fixtures. Two task-local AST tests of private launcher wiring
are deliberately not included: they would not prove the repository integration.
The repository composition test instead states its injected seams explicitly.
