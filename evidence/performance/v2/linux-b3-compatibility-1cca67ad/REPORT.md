# Linux B3 compatibility

12 authoritative compatibility runs: three each of materialized streams16/32
across8fixed channels,16simultaneous bundles, and three same-process cycles.
All analyses retain DIAGNOSTIC_BINARY_SOURCE_MISMATCH: staged controller
1cca67ad092292acec85f622c7d2825c47654a67; unchanged Rust binaries
3644c324a535586e89af72a8c9796e8d58fadf48. run_b3_v2 CLI live NOT_RUN.
This validates the staged run_cell/backend/analyzer path in Docker Desktop's
Linux guest; no dedicated server, external NIC, or current Rust build claim.

Accepted capture verified425checksum entries over219files before releasing the
owned container. Three-repeat scale gates pass (private-resident CV0.56-2.08%).
All processes joined; destination materialized markers prove16/32streams with8
channels and64streams per same-process cycle.15source post-close samples explicitly
record unavailable memory after expected clean bundle exits, never zero memory.

Important gate qualification: existing B3 controller enforces8ownership fields.
Independent retained-raw verification checks all11exact-integer-zero fields in
24final source/destination reports plus9source cycle reports (33total), allPASS.
Original records are unchanged; this does not pretend the old controller had an
11-field gate. A separate gate repair follows.

The first attempt's terminal reported12passes but docker cp of the running tmpfs
returned an empty directory. It is INVALID/FAILED_EVIDENCE_CAPTURE, not12valid
runs. Its console/inspect/failure inventory is retained. The accepted rerun uses
binary subprocess docker exec tar streaming and verifies nonempty expected data
and all hashes before the wrapper exits. Historical analysis input indexes are
retained in analysis-input-checksums.txt, matching each analysis's input hash.

Both containers used the same immutable image dd08db4a391b16a9d303a251d2693808baf470f2fc4870d8e3c54b7523deed71,
nonroot, networknone, read-only root/controller, cap-dropALL, no-new-privileges,
768MiB RAM/swap bound,1CPUquota,128PIDbound,16MiB/tmp and256MiB/evidence
noexec/nosuid/nodev tmpfs. Original immutable image binaries executed; no build,
image pull, host network/firewall/port or privilege change. Inspected stopped
owned containers were removed after evidence capture; no unrelated cleanup.

Canonical files preserve raw bytes. Executable copies and complete source/tar
archives remain at hash-bound external paths listed in external-inputs.json;
rehydrate those files for standalone load_input replay. Package checksums bind
all files retained here; external indexes bind the complete originals.
