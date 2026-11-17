# Weekly full-analysis adapter (offline preparation only)

Run scripts/ci/build_weekly_api_plan.py --snapshot <fresh-reviewed-snapshot-directory> --output <new-per-commit-run-directory>. Never reuse a directory. Snapshot producer must first resolve the latest authorized development ref; adapter verifies exact provenance/scope, not remote freshness itself.

The output plan binds the retained snapshot, exact source ranges and request hashes. Exclusions remain visible. Sources are never executed. Input chunks are repacked at original line boundaries, encoded requests <=96000 bytes. Source digests and Git object hashes are rechecked. Empty files are represented explicitly. Budget state is blocked-needs-exact-counts when the conservative input-byte reserve plus $0.50 exceeds $10; no partial paid run should start.

Worker scripts/ci/api_weekly_worker.py uses a $10 per-run maximum and $0.50 synthesis margin. Reuse only the unchanged reviewed DPAPI wrapper with reviewed Python/client hashes and the NEW plan hash. Do not copy the old one-time $17.27 launcher. No launch automation or credentials are included here. No live calls have been made by this adapter development.

The worker ledger is per-run, not account-wide: coordinator must verify sufficient grant balance, concurrent usage and no recharge before paid execution; if uncertain, hold. Exact token counting is a separately authorized source transmission, not performed by preparation. Source/account checks do not authorize new permissions.

Offline checks: the combined snapshot/planner/adapter/worker suite collected and passed 83 cases; all ten changed Python files passed repository Ruff. Formatting normalization preserved the AST except for splitting import statements. Tests cover corruption, scope, incompleteness, path escape, no-overwrite, excluded-file preservation, worker budget/hash/snapshot guards, reservations/interruptions and mocked sends.

Original one-time batch and follow-up plans/receipts are unchanged. Repository publication is pending. Independent source review accepted full preparation and the long-line segmentation delta; the mini worker and the separate Sol asynchronous worker must not be conflated. This adapter is pinned to gpt-5.4-mini-2026-03-17, not Sol.

Long minified source lines are split into UTF-8-safe byte segments without omission. Each segment retains its original line number and contiguous original byte range. A segment may not be a standalone JSON document; findings must not infer absent surrounding context. This is source coverage, not a whole-program correctness guarantee.
