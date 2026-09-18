# Retained ETL storage maintenance

Eight explicitly selected historical NBSR ETL files were compressed in place
using Windows NTFS `compact.exe /C /I /Q` with one absolute file path per call.
No directory recursion, wildcard, CompactOS change, deletion or relocation was
used. All eight original paths, logical byte lengths and SHA-256 hashes remain
unchanged. Full before/after hashes, allocation sizes, timestamps, exact commands
and tool outputs are retained. No source, Git data, user documents, keys, accepted
plans, raw trace content or unfavorable benchmark result was removed.

Measured file allocation reduction: 10030006272 bytes (approximately 9.34 GiB).
Observed C: free space increased from 6802305024 to 16830345216 bytes (about
6.34 to 15.67 GiB). The small difference between allocation savings and volume
free-space change can include unrelated background activity. This is actual host
storage accounting, distinct from previously removed Docker writable layers
whose deletion does not necessarily shrink the Docker VHD.

Compression was performed only after the active capture cohort had ended. These
are retained historical traces, not timed workload output directories or running
binaries. Windows transparently decompresses them for normal reads. This is
infrastructure maintenance, not a performance optimization or a proposed cause
of the preceding two-packet capture loss. No benchmark result is improved by it.

`results.json` binds each retained ETL path to its original and post-compression
SHA-256. The maintenance raw-root index binds the operation logs and manifest;
it does not replace historical benchmark evidence indices. Original trace data
remain local and must not be published without their normal privacy review.
