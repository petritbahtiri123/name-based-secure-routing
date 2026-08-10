# Rust Transport-Session Replay-History Hard Cap

The Rust destination retains complete committed Application Stream replay history for the lifetime of each Transport Session. It does not evict old entries, use a replay window, or replace the exact set with a probabilistic representation.

`ReplayHistoryLimit` is the operational resource boundary. A deployment can construct each `ControlSession` with `ControlSession::new_with_replay_history_limit`; the positive limit is validated before construction and snapshotted immutably into that session. The compatibility constructor uses the type's absolute `u32::MAX` bound; production deployments must select a materially lower explicit value according to their memory and resource budget.

At exhaustion, an otherwise-valid fresh `STREAM_OPEN` fails closed with `StreamReject::OverCapacity` before replay insertion or application/upstream side effects. Existing committed IDs still receive `DuplicateStream`, and malformed or unauthorized opens retain their earlier security rejection. `OverCapacity` does not mean any replay history was discarded.

Clients should establish a fresh Transport Session before reaching the selected boundary. Seamless production Go session rotation is not implemented. Consequently, reaching the cap intentionally prevents new streams on that Transport Session until a fresh session is established; this is a server resource-safety boundary, not an availability solution.
