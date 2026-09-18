# External build-manifest source binding

The documented recipe previously read HEAD when writing the manifest, after
compilation. A changed checkout could therefore label existing binaries with
a later source SHA. It also did not refuse dirty source or manifest overwrite.

Three literal RED cases execute that actual inline Python recipe with synthetic
metadata: changed HEAD, dirty source and an existing manifest were accepted.
The unchanged clean case passes. Fix 18225789 uses the pre-build SHA inventory,
rejects HEAD/status changes and exclusively creates the manifest. The recipe
also unsets its build-only NBSR variable before workload execution.

Six focused recipe/server-definition tests pass; Ruff and diff checks pass.
This is source-provenance regression coverage with controlled Git responses and
synthetic binary bytes, not new compiler, performance or external-host evidence.
Pre/post checks cannot attest against transient edits later reverted; builds
still require an unchanged clean checkout. Failed attempts must be preserved
and rebuilt in fresh output, never relabeled. No production or protocol change.
