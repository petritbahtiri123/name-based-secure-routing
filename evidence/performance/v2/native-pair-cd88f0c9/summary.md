# Transferred native pair integrity gate

Analyzer source: cd88f0c9f3314fb1dd3ad15215f018d8676460c1. The unchanged 16 finite namespace cells from
1d24cb4c740c53c945932ff8d67bdd34b3b75209 all pass the new read-only join gate.
No benchmark was rerun, and no old raw evidence was rewritten. The gate requires
an explicitly expected source SHA, complete checksum inventory, matching build,
workload, CA, readiness and endpoint, executed binary and command, valid source
output, and consistent owned-process terminal samples/exit. Failed or forced
cleanup evidence is rejected. Checksums are not signatures/remote attestation.

Literal RED: 16 tests failed because the module was absent. Initial GREEN exposed
a Windows-generated synthetic fixture path incompatibility; the fixture was
corrected to represent Linux argv, without weakening production validation.
Final focused suite: 54 PASS; Ruff and diff checks PASS. This is an offline
integrity gate, not observer qualification, steady-state CPU accounting, strict
stable throughput, runtime ownership cleanup or external hardware validation.

A focused parent review covered inventory traversal/duplicates, source/build and
role joins, command equivalence, sample PID/CPU monotonicity and result arithmetic.
No production/security/wire/authority changes or new dependencies were introduced.

Cleanup removed three stopped, campaign-owned containers and their isolated
internal bridge after authoritative raw index verification. Approximate disposed
writable layers: 922787840 bytes; host SSD recovery is not inferred from Docker
layer removal. Required images, binaries, raw evidence, source and Git data remain.
Git automatic maintenance reported a permission error on existing worktree
metadata during the preceding commit; that commit succeeded. No manual deletion
or destructive repair of Git metadata was attempted.
