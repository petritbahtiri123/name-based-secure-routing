# Demo Lab preview 2026-11

This is a limited development preview for independent local exploration. Identify
it by the full commit SHA supplied in the preview link. It is not a production
release, security certification, throughput/capacity result or guaranteed install.

## What has been checked

Windows: local Go/Rust allowed-service run, five named fixture regressions,
independent receipt verification, cancellation/cleanup, browser launch/stop/restart
and Petrit's personal testing of the base and updated evidence-path UI. The
updated diagram was checked against live and fixture receipts; intentional idle
server loss disabled actions and marked retained evidence historical.

The final setup-only changes passed125 scoped Python component tests, the Node
frontend regression, an offline eight-artifact Windows build, and source/binary
hash validation. The staging write/read/delete probe passed on this laptop.
No new live run was performed after those setup-only changes; earlier receipts
retain their original source identities. Test counts describe this local record,
not a cross-platform CI certification.

Observed environment: Windows x64, Python3.14.6, Go1.26.5, Rust/Cargo1.97.1,
MSVC14.44.35207, Windows SDK10.0.26100.0. Supported metadata version ranges are
broader than the environments actually tested.

## Limitations to keep with every shared copy

- Fresh-machine installation has not been tested; no VM validation was performed.
- Mac is prepared but UNTESTED. We do not know whether it works on a real Mac.
  The planned route is a Mac dashboard plus Linux Docker container. Image assembly
  and native Intel/Apple Silicon acceptance are incomplete; this is not turnkey.
- Dependency fetch does not warm Rust compilation. Cold builds can hit the95s
  per-stage deadline. Preserve failures; do not silently increase limits.
- Negative scenarios are named fixture regressions, not live attacks on the Rust
  destination. Diagram steps are schematic unless explicitly tied to a verified
  assertion; no per-hop timings or unmeasured events are claimed.
- Native OS clipboard behavior was inconclusive in automation. The visible
  verification command can be copied manually; clipboard rejection has guidance.
- The original personal-test server interruption's initiating cause is unknown.
  The disconnected UI behavior was corrected and tested, not retroactively
  presented as proof of that old process's exit cause.

## Recipient workflow

Follow [README](README.md) for clone/cd, exact commit comparison, prerequisites,
explicit dependency preparation, bounded offline build, dashboard launch and
terminal verification. Keep the launching terminal open. Use Stop Demo Lab when
finished. Do not publish private runtime fixtures, session URLs, keys or local
.state folders. The repository contains source and tests, not the developer's
private caches, binaries or raw runtime credentials.

Sharing this preview does not mean sending an email has occurred. Delivery and
recipient access must be confirmed separately; private repository access may be
needed. Nothing here claims Mac or clean-machine validation.
