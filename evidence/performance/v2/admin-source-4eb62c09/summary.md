# Prepared isolated source for the deferred Administrator capture

The original checkout has three pre-existing untracked OneDrive evidence
variants with different byte hashes. They remain unchanged. A separate local
clone at 4eb62c093273dcfe883c0bb5c02cf69dbd426c20 preserves the strict clean-source
capture gate without deleting files or altering parent refs/history. Git objects
are independently copied, not hardlinked. Only required source/fixture directories
are materialized. Keep this source path for the prepared binaries and future run.

Initial exact-byte verification caught system autocrlf conversion of the PowerShell
script. Clone-local LF settings restored committed bytes; explicit-path index
refresh removed stale modified stat metadata with no staged content change.
All failed preparation controllers and repair records are retained. No parent
Git configuration, frozen source, security policy or commit history changed.

Final clone status is clean on the expected feature branch; Git connectivity,
PowerShell parse, expected non-admin refusal and a locked Windows release build
pass. Three exact binary hashes and compiler/build commands are retained. These
are preparation checks, not WPR execution, performance or observer qualification.
The unchanged capture script still refuses an existing/unknown WPR recording.

The Administrator ledger contains one exact command pointing to this prepared
clone. Elevated end-to-end validation remains ADMIN_REQUIRED / NOT_RUN; no new
elevation request or automatic recording was started during preparation.
