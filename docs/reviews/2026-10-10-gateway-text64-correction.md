# Stage 2 gateway text64 correction

The previous 420-test offline closure missed a config-to-registration mismatch:
all three gateway IDs required 64 hex characters, while approved REQUEST key 6
requires canonical text64. The unchanged old example passed preflight but failed
actual `decode_body("REQUEST", ...)` after insertion into retained REQUEST bytes.
The expected red run retained four failures and one passing boundary case.

The minimal correction applies the shared protocol grammar and `require_text_id`
to client, gateway and origin-service gateway IDs: 1–64 ASCII characters starting
with a lowercase letter, with the approved separator grammar. The example uses
`gateway.fixture`; schema and tests are synchronized. No hashing, truncation,
case folding or coercion occurs. Operator/service identifiers are unchanged.

The example-to-REQUEST regression invokes the actual approved body validator for
all three roles, and tests accepted boundary values, malformed IDs and mismatched
roles. These checks establish representation compatibility, not authenticated
registration or runtime authority. Stage 2's offline closure is restored with
this correction; Stage 1 remains accepted, total 2/10. Historical evidence remains
unchanged, including the original erroneous example snapshot and 420-test result.

Focused result: 101 passed. Final scoped result: **459 passed, zero failed/skipped**
(101 configuration + 103 CRP + 187 model/federation + 68 CBOR). Ruff check/format
passed. Independent review found no blocking findings; reviewer inspected code
and tests without rerunning them. Python 3.14.6 local evidence is not a platform
matrix or hosted CI result. All five supervised children reaped without abort;
no task-created containers/background workers. Final supervisor 6.63 seconds,
disk start 12,174,155,776/end 12,174,118,912 bytes; RAM end 4,771,553,280 bytes.

This correction changes no protocol registry, carrier, credential, trust or
runtime behavior. No commit/push/live activation. The subsequent Stage 3 approval
is separate and does not retroactively change this checkpoint's scope.
