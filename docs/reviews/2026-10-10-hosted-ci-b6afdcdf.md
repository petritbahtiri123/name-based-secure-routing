# Hosted CI b6afdcdf: all seven jobs passed

Exact SHA: `b6afdcdfe6daa85f50d633461df050d0e870ee7f`. [Run 38058799631](https://github.com/petritbahtiri123/name-based-secure-routing/actions/runs/38058799631) completed successfully; 2026-10-10T14:14:06Z to 2026-10-10T14:18:58Z.

- rust (windows-2025): PASS
- python (ubuntu-24.04): PASS
- node-policy: PASS
- go (ubuntu-24.04): PASS
- rust (ubuntu-24.04): PASS
- go (windows-2025): PASS
- python (windows-2025): PASS

Windows Go cleared all seven demo packages and demo vet, then all remaining modules and explicit v2 verification (zero divergences). The previous demo fixture blocker is cleared in hosted CI. Individual Go tests/skips are not enumerated by these nonverbose logs.

Coverage limits:

- Hosted Go logs are not verbose: individual prerequisite skips and Windows 8.3 regression execution versus skip are not exposed.
- Local retained demo evidence: 73 passing events, four real-process prerequisite skips; new Windows regression and child subtest ran successfully.
- Missing NBSR_TASK4_RUST_BINARY skips TestFullTask4RealSecureRoute. Missing NBSR_TASK4_CLIENT_BINARY skips TestStandaloneClientRealSecureRoute, TestStandaloneBackendFailureHasNoFallback, TestStandaloneTransportFailureHasNoFallback.
- Rust library retains one ignored soak; hosted bounded profiles do not prove full real-process, WAN, load/capacity or production readiness.
- Python Windows runs core only; protocol/federation profile results are Ubuntu evidence.

All seven decoded logs are retained locally with SHA-256 hashes in the adjacent JSON. Monitoring changed evidence only; no code, authority/security settings, publication or ACK work.
