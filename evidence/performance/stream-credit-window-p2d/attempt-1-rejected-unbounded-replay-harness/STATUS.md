# Attempt 1 status

This attempt is **REJECTED AND NON-AUTHORITATIVE**. Its live cells reported a
replay limit of `4294967295`, not the required P1F bound of `10000`. The
resource gate therefore could not pass even though the initial analysis file
labeled it PASS.

No measured value has been relabeled or deleted. The original analysis is
preserved losslessly as `analysis.json.gz`; its original soak reference is now
stored losslessly as `raw/soak/after.json.gz`. Exact original and compressed
hashes and byte counts are recorded in the package-level
`compressed-artifacts.json`.

The evidence-driven correction configured both live benchmark endpoints with
the existing exact `ReplayHistoryLimit(10000)` and made the validator require
that exact value. Attempts 2-4 were subsequently superseded. Attempt 5 is the
sole authoritative final-source acceptance campaign.
