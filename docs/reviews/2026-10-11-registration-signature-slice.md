# Full-model checkpoint: native signature prerequisite

Controller-only fallback is superseded. The corrected provider proposal and full
acceptance matrix preserve every applicable controller/normal/emergency obligation.
The implementation plan retains the explicit comprehensive security-audit gate
before a real pilot. Stage 3 remains partial.

Implemented only `connector_signature.rs`, compiled in its integration-test target,
with exact bounded tagged COSE_Sign1 parsing, expected payload/kid binding and
Ed25519 strict verification. Its private result has no authority, registration,
event or readiness conversion. It does not check signer purpose/lifecycle/validity,
thresholds or currentness. A cryptographically valid wrong-purpose fixture explicitly
passes this primitive while remaining an authority rejection in the source vector.

The extractor checks 14 existing public signed cases with Python: eight ordinary
positive cases, the signed wrong-purpose negative and five individual signatures
from existing global-trust 3/5 and emergency 2/5 fixtures. These are primitive
checks, not normal-revocation quorum acceptance. No keys/signatures were generated;
existing vector packages are unchanged. Extracted bytes live under tests/fixtures.
CI selects the Rust target and Python `--check`; hosted CI was not run.

## Verification

- Final native signature target: 6 passed, no ignored tests; includes tampering,
  wrong expected context/key/kid, truncation, trailing bytes, headers/detachment,
  canonical lengths and bounded inputs.
- Rust neighbors: 25 passed; one existing live loopback test intentionally ignored.
- 109 distinct Python authority/revocation/threshold/CI tests passed across runs.
  This was not one all-green run: initial group 105 passed/4 temp-directory errors;
  fresh-temp CI rerun 24 passed/1 timeout-cleanup error; exact host-permission
  cleanup rerun 1 passed. No assertion or cleanup condition was weakened.
- Python oracle/drift: 14 signature cases verified. Clippy, Cargo formatting,
  Ruff and tracked diff whitespace checks passed. Include-path formatting drift
  after relocating the fixture was corrected and final native tests/fmt rerun.
- Independent security review found no remaining blocker for this narrow component
  after correcting scope wording and adding parser negatives. Reviewer did not
  independently rerun tests; no full-model security equivalence is claimed.

All red/environment failures and final results are retained with commands,
commit/branch, source snapshots, working patch, public fixture/source hashes and
final native binary hash in the adjacent JSON and
`evidence/connector-registration-development/2026-10-11-full-model-signature/`.
Every supervised command stayed bounded; disk/RAM remained above guards. The
initial timeout cleanup failure was not hidden: its descendant PID was later
verified absent, and the exact host-permission rerun verified successful reap.
No task sockets or containers were created. Existing unrelated work is preserved.

## Blocking runtime choices

The retained named policy `global-trust-v1` is for FederationTrustBundle replacement;
it cannot stand in for normal TypedRevocationRecord 3/5 authority. Resolve that
exact approved named-policy mapping and runtime authority of the existing Option C
version. Do not invent new wire bytes or downgrade to controller authority. Real
bootstrap/currentness delivery, restart floors, real clock/retention and all-mode
event/active-work integration remain required. Registry runtime/live-trust flags
remain false. No source overlay, installation, activation, commit or push occurred.
