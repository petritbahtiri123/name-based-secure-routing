# Non-destructive benchmark evidence ZIP helper

`scripts/benchmark_evidence_zip.py` accepts an explicit bounded path/size/SHA256
inventory. It retains originals, refuses overwrite/path redirection and checks
source identities, archive size, exact members, decompressed bytes, SHA256 and CRC.
A failed archive is retained as partial evidence, not promoted as a valid result.

Windows lstat and fstat may represent ctime differently. Cross-API comparison uses
file identity, type, size, mtime and available birthtime; each API's own ctime is
still compared against its own baseline after reading. This is not a guarantee
against hostile concurrent mutation. The caller must establish closed writers,
reserved construction/output space and a bounded invocation before using it.

Tests under tests/ci are already included by python-core. Fourteen offline cases
cover archive preservation/identity/bounds, parser preflight, duplicate and extra
members, archive replacement, cross-API ctime differences and same-API changes.
Cloud validation passed all 14 cases and Ruff. Independent native Windows
validation collected all 14 cases: 13 passed and the open-archive replacement
case was skipped because Windows prohibits that operation. The same race case
passed on Linux. Independent source review accepted this quiescent-input scope. No production post-run hook or pruning is
implemented here; no source is deleted and no benchmark validity is inferred.
