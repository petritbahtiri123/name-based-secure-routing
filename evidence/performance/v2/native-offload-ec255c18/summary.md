# Native UDP segmentation attribution and retained partial cohort

MEASURED: three counterbalanced Direct on/off pairs at ec255c18, identical
64,000 one-KiB request/response operations and identical release binaries.
Only tx-udp-segmentation changes on two disposable internal-network veths;
GRO remains off and GSO/TSO remain on. On-state captures exceed MTU 1500
and are correctly rejected. All three off-state captures have no IPv4 length
over 1500, pass zero-loss accounting and observed start/end markers. This
attributes this captured representation effect to the scoped UDP-segmentation
setting. It does not establish physical Ethernet sizes or solve admission delay.
CAP_NET_ADMIN was limited to these test containers; no privileged mode, host
network namespace, host NIC changes or production/security semantics changes.

Earlier db7edb19 attempt retained five completed diagnostic cells and a sixth
readiness failure: a coordinator observed an empty, not-yet-complete JSON file.
ec255c18 publishes the closed marker by atomic rename. Literal RED missing
helper; GREEN 49 focused tests, then 68 affected tests; scoped Ruff PASS.
The new live series passes six diagnostic captures and starts the formal cohort.
The formal series remains INVALID_PARTIAL: the fourth cell fails the unchanged
five-GiB free-space preflight. Three formal cells complete, insufficient repeats
for any accepted paired overhead result. No failed result was replaced or pooled.

All three Linux release hashes remain identical. Timing under this observer is
DIAGNOSTIC only. Socket/process ownership, established-phase separation, actual
physical interfaces and a complete repeat-qualified Direct/NBSR cohort remain
unproven. No strict-stable or production speedup claim follows.

Six stopped, campaign-owned containers were removed after retained bind-mounted
evidence was sealed; 2,691,866,624 writable-layer bytes were disposable source
clones. No authoritative artifact, image or volume was deleted. Actual host SSD
space returned by Docker is not measured. Current reserve prevents further
large captures until safe storage recovery is sufficient.
