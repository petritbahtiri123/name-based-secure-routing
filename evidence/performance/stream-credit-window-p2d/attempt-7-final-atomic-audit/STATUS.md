# Attempt 7 status

This is the **sole authoritative final-source acceptance campaign**. It is
bound to commit `100b871db011ba514bd45f0354714e1f698ebdd5`, complete Git
tree `6d84e897b29e358c716c6c83b2ad6efc2ec445fa`, measured-source SHA-256
`921d4276f4aa28d7747c78622bb0a785a3333e3020188a8f45bc1b38483e7cb4`,
and exact rebuilt release binary hashes recorded in `build.json`.

Pre-output porcelain-v2 status was exactly empty, `git write-tree` equaled the
HEAD tree, and the post-output, post-build, every-cell-boundary, and final
runtime audits allowed only this exact attempt root. The final audit was
atomically transitioned from the known canonical `IN_PROGRESS` document to
`PASS`; commit, HEAD tree, and index tree remained equal with zero disallowed
changes.

The full live runner returned Outcome A after 879.4 seconds with every
mandatory gate PASS. The oversized soak JSON is preserved losslessly as
`raw/soak/after.json.gz`; exact original/compressed identities and deterministic
recompression verification are recorded in the package compression manifest.
