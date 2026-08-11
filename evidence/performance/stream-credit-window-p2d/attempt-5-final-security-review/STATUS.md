# Attempt 5 status

This is the **sole authoritative final-source acceptance campaign**. It is
bound to corrected commit `8cc935e1a08de20eaab1abd814906d1854da9bc8`,
complete measured-source SHA-256
`e32e8b4c4b2187c2fb1412909fcdc2449b771e2b096c763175ade7e2396c2cb3`,
and exact rebuilt release binary hashes recorded in `build.json`.

Every bound input had empty status, worktree-diff, and index-diff identities.
The generic repository-dirty flag is true only because the immutable Attempt 5
output directory was created before source binding; the separately recorded
35-input binding is clean and exact. The full runner returned Outcome A with
every mandatory gate PASS. Its oversized soak JSON is preserved losslessly as
`raw/soak/after.json.gz`; exact original/compressed identities and deterministic
recompression verification are recorded in the package compression manifest.
