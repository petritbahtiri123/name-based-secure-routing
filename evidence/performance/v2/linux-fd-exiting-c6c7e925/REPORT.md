# Opted-in finite lifecycle exit observations

Harness-only change against c6c7e925; no Rust, protocol, security, timeout or
workload change. Linux finite reference opts into identity-checked PF_EXITING
observations after FD PermissionError. fd_count is null, explicitly
UNAVAILABLE_EXITING, and process state is preserved. Other sampler callers keep
the strict default. The finite owner rejects missing prior identity and reversal
to an ordinary live state; it still requires final zombie CPU/identity, exit-code
validation, post-close ownership reports and source completion ACK ordering.

RED: eight focused cases failed before implementation. GREEN: 121 focused tests
across Linux sampler, finite reference, failure context, resource and sustained
CLI contracts; Ruff and diff checks pass. Focused review verified no ordinary
live permission denial is suppressed and intermediate CPU is never final CPU.

Actual unprivileged Linux regression: 500 owned-child lifecycles completed,
including 939 explicitly unavailable exiting observations. All final samples
were same-identity zombies with nondecreasing CPU; all 500 joins returned zero.
The source snapshot includes a comment-only clarification made after this probe;
the tested executable behavior is unchanged. This is lifecycle regression
evidence, not an exact-byte benchmark reference or observer qualification.

Seven raw files are indexed in raw-evidence.json. The original FD failure remains
invalid and cannot be retrospectively attributed. Full current-source finite
reference/observer qualification and B5 resource-sampler integration remain
pending; this opt-in intentionally does not change LinuxResourceSampler yet.
