# BLOCKED_ARCHITECTURAL: federation package trust-anchor mismatch

The full Go race suite at df8b7808 fails TestCheckedInPackage in the independent
federation verifier. Its trusted manifest digest is:

`1ff9591b925e926e757bb57ab8f3cd1620b6ff9d41149df92ad5672ff810ab35`

The checked-in manifest, matching the Git blob exactly, is:

`2ab8286179221e06c2c24843f6a1015f24247c6a1de9d8cb81f20e5fe88aa497`

This is not checkout line-ending corruption. The mismatch already exists at
this continuation's start,09a669a343330b381c67605114338cdc87d420e4.
e15b2511bc9cc0c0917b74bdd09e354422c805d6 updates the authority locks and manifest
to a registry that had already gained ACP_RESULT_SIGNING(15) and
ENROLLMENT_RESULT_SIGNING(16), moving the reserved range to17..255. The clean-room
verifier introduced at7af98223 retains the older manifest pin. Both package
versions use the same published package-version identifier.

The verifier rejects the untrusted digest before accepting the package. This is
a pre-existing compatibility/authority-version problem, not evidence of an
authorization bypass introduced by benchmark optimization. Four other Go modules'
full race suites pass, and all five module vet runs pass. Other federation
verifier package tests pass; its package-level suite is not globally green.

No trusted digest, frozen registry, manifest, assertion or fail-closed check was
changed. Resolving which immutable package versions the independent verifier
must trust requires an explicit authority/package compatibility decision. A
versioned publication can preserve the old immutable package and separately bind
the expanded authority; silently replacing the trust anchor or weakening the
current-package assertion is not an authorized benchmark repair.

Raw diagnosis and complete failing output:
C:/NBSR-build/go-quality-df8b7808/manifest-attribution.json
C:/NBSR-build/go-quality-df8b7808/verifiers_federation-go-test.log
