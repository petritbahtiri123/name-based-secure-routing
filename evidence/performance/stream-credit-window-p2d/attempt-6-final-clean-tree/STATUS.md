# Attempt 6 status

This attempt is **non-authoritative and failed**. It is preserved additively
because all timed cells completed, but the runner exited 1 while finalizing the
runtime repository audit. The initially exclusive-created
`runtime-repository-audit.json` remained `IN_PROGRESS`; the runner then tried
to exclusive-create that same path instead of atomically replacing the known
in-progress document and raised `FileExistsError`.

The attempt is bound to commit
`6cfe323ccc9128f63dd66d4133c85e2d4d6c86b4`, Git tree
`430416b57e8c17f1f5fa74b3c348a21e3369b8bb`, and measured-source SHA-256
`032b130945b5082850e2c69ccf0049902118b9f23c6a7cb878ca3ca0c34d067c`.
Those identities do not make the incomplete finalization authoritative. Do not
use the Outcome A written to `analysis.json` for final-source acceptance.

The oversized soak JSON is preserved losslessly as
`raw/soak/after.json.gz`. Its original and compressed identities and exact
deterministic recompression verification are recorded in the package
compression manifest. `RUNNER-FAILURE.txt` records the terminal failure.
Attempt 7 corrects the finalizer and is the sole authoritative final-source
acceptance campaign.
