# Attempt 5 status

This is valid security-correction evidence, but it is **superseded and not the
final-source acceptance authority**. It is bound to corrected commit
`8cc935e1a08de20eaab1abd814906d1854da9bc8`, selected-input SHA-256
`e32e8b4c4b2187c2fb1412909fcdc2449b771e2b096c763175ade7e2396c2cb3`,
and exact rebuilt release binary hashes recorded in `build.json`.

Every bound input had empty status, worktree-diff, and index-diff identities.
The generic repository-dirty flag is true only because the immutable Attempt 5
output directory was created before source binding; the separately recorded
35-input binding is clean and exact, but it omitted transitive imported inputs
and was captured after output creation. Attempt 7 supersedes it with a clean
pre-output whole-Git-tree identity and cell-boundary runtime audits. Attempt 5's
oversized soak JSON remains preserved losslessly as `raw/soak/after.json.gz`;
exact original/compressed identities and deterministic recompression
verification are recorded in the package compression manifest.
