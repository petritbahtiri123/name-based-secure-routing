# Offline probe preparation correction

No Docker command or live probe executed in this correction. All work remains uncommitted in the isolated reviewed source checkout.

## Changes
The worker catches launch exceptions and writes original type, message, errno and winerror in a request-hash-bound reply with code null. Host reply handling rejects this as a launch failure. Existing primary timeout, cleanup failure and retained ownership diagnostics remain unchanged. An injected OSError regression verifies exact preservation.

Windows command preflight uses subprocess.list2cmdline and counts UTF-16 units including NUL, rejecting above a conservative 30,000 before creating a request/helper. Worker checks again. Tests cover long ASCII and supplementary Unicode.

Compact shell probe reads the single exact lockfile mount. Host TOML validation accepts only crates.io package records with safe names/versions and exact checksums; the shell verifies the complete file hash, reads package tuples using AWK, checks its final count, prints installed tool versions and archive hashes/source presence. Outer timeout remains 15 seconds. No package list is embedded. Missing utilities fail explicitly; missing Rust/Cargo are reported. Archive presence/checksum evidence does not establish compiler compatibility, complete extracted sources/index, native prerequisites or build readiness.

## Proposal, not executed
Exact complete Docker argv is in proposal.json: 2,586 serialized UTF-16 units including NUL; Windows CommandLineToArgvW round-trip PASS. Entrypoint /usr/bin/timeout, arguments `15 /bin/sh -c <compact-program> cache-metadata /inspection/Cargo.lock <sha256> 130`. One unchanged read-only bind from C:/Users/OPERATOR/AppData/Local/Temp/nbsr-two-stream-source-20261013/crates/nbsr-transport/Cargo.lock to /inspection/Cargo.lock. No script-file mount, directory mount or secret content. Existing isolation flags retained. A future trial still requires explicit authority and fresh unique identity/resource/path checks.

## Validation
78 focused tests PASS in 2.26 seconds (3.22 seconds supervised); Ruff PASS. Windows full argv round-trip and current-lock 130-package AWK-versus-tomllib comparison passed. Missing-tool fixture passed. Independent reviewer found a platform-test gating issue, corrected; final read-only review found no remaining scoped blocker. No live environment or offline build-readiness claim.

Retained unsuccessful checks: initial test-file write hit host encoding before tests; restored that file from HEAD plus the exact retained cold30 patch before adding tests. First attempted red run collected no tests; second hit unavailable default pytest temp. A collection SyntaxError from an overly broad textual edit was corrected. Next run had 77 PASS and one sandbox Git Bash named-object failure. Approved shell fixture then exposed Git Bash resetting empty inherited PATH; corrected fixture sets PATH inside shell. Final run passed all 78. These failures are retained, not counted as red/green proof of the historical launch cause.

The previous 53,161-character launch remains a likely command-length failure, not a confirmed causal result: its original exception was not recorded. New regression evidence establishes future diagnostic retention only.
