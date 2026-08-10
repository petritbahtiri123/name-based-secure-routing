# TDD summary

RED was observed with `cargo test channel_streams::tests --lib`: compilation failed because `ReplayHistoryLimit` and the limit-taking `ChannelStreams::new` API did not exist. No production cap code existed at that point.

The minimal GREEN change added the validated positive `u32`-bounded type, immutable owner snapshot, and one capacity branch after duplicate, per-channel, and `StreamGate` authorization checks but before `PreparedStreamOpen` and `commit_open`. The first GREEN run exposed two fixture errors (invalid QUIC stream-ID shape and an incorrect expected typed mismatch); correcting only those literals produced 11/11 passing focused tests. The final focused set contains 12 ordinary tests plus one ignored evidence soak.

The adversarial ordinary test committed 10,000 IDs, released every active stream without erasing replay history, rejected 15,000 later unique IDs, retained duplicate precedence, and never exceeded 10,000 logical entries.
