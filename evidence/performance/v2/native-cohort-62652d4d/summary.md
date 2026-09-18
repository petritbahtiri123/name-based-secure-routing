# Native comparison-cohort integrity

Read-only analyzer 62652d4d revalidates all sixteen retained native peer pairs
from 1d24cb4c without rerunning workloads or rewriting their sealed evidence.
Five counterbalanced pairs for 1 KiB/64 streams and three for 16 KiB/eight
streams satisfy the declared cohort integrity contract. Direct 1 KiB dispersion
remains unresolved at 10.092%; NBSR is 2.475%. The 16 KiB goodput CVs are 0.229%
and 1.938%. No unfavorable repeat is filtered out. Medians and paired deltas
are derived from each pair's validated operation counts and measured duration.

A real under-repeated negative control truncates only a separate analysis
manifest to the first three 1 KiB pairs. The CLI rejects it because first-three
Direct CV is 11.670% and both paths require five repeats. Original peer outputs,
the complete five-pair manifest and every valid result remain intact.

The gate rejects missing/reordered repeats, inconsistent recorded configuration
or authority, duplicate roots, identical sealed evidence reused as a new repeat,
and any invalid peer pair. It never converts finite integrity into strict-stable
capacity, runtime-ownership cleanup, observer qualification or external hardware.
Manifest order is declared rather than independently timestamp-proven, and
undisclosed attempts outside a manifest cannot be detected. Checksums are not
signatures, authenticated transfer or remote attestation.

Eleven literal RED tests precede implementation. The first GREEN correctly
rejected reused synthetic fixture identities; corrected fixtures model distinct
process epochs. All thirty-two cohort/pair tests pass, as do Ruff, diff and real
CLI positive/negative controls. Failed fixture logs remain retained. This is
external execution preparation, not closure of the full remote workload matrix.
