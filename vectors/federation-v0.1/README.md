# Federation v0.1 Development Profile conformance vectors

This closed package is the normative deterministic cross-language test authority for the approved Federation v0.1 Development Profile. It binds static and signed objects, public trusted-signer records and payload-derived signer requirements, threshold-container v1 literals, capability agreement, ordered state transitions, exact decisions, symbolic reasons, enforcement, mutation, state digests, dependencies, fixed times, and resource expectations.

The 28 Task 2 schema literals, Task 6 specification-authored state manifest, and 89 threshold-container literals remain independent oracles. Generation verifies and references their bytes; disagreement fails and never rewrites them. `THRESHOLD_EVIDENCE = 6` is required and `FEDERATION_OBJECTS` alone is insufficient.

Run `python scripts/generate_federation_v01_vectors.py --check vectors/federation-v0.1`. Check mode is read-only.

## Non-claims

This package does not claim independent Node or Go verification, live federation deployment, production governance, live DNS/HTTPS, remote verification, or real-world threshold custody. Those are outside Task 7.
