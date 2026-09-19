# Native lifecycle bind prerequisite

The established benchmark supports explicit source placement, but the separate
lifecycle path rejects it and calls the production loopback-default connector.
The retained release RED at parent c7ca8651 requests 127.0.0.2:0 with a genuine
one-cycle fixture and fails at the explicit unsupported-mode guard.

Use the existing benchmark-only connector in the lifecycle path, with the same
validated ephemeral IPv4 bind and unchanged TLS/peer/service authority. Omitted
flags retain the existing loopback default. Production builds keep `connect`.
No timeout, admission, replay, close or ACK rule changes.

Validation must observe the actual source UDP binding during active lifecycle
work, retain full cleanup, and reject malformed or unavailable addresses. A
loopback-alias pass is a prerequisite, not external two-host/server evidence.
Remote lifecycle/admission orchestration remains a separate task.
