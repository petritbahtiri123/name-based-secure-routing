# Linux sampler lifecycle repair

Parent base 513e50d4; failed Linux build/smoke source 6227fd86. Release build
PASS, smoke FAIL with zero accepted runs. A same-UID restricted-container probe
proved live FD reads work while an unreaped zombie returns PermissionError.

The minimal harness repair records zombie FD count as null with explicit
UNAVAILABLE_ZOMBIE state. A live-to-zombie permission race is accepted only after
re-reading the same PID/start ticks and proving state Z. Final CPU comes from
that re-read. Live permission errors and identity changes still fail. Existing
wait/exit validation and affinity checks are unchanged. No container permissions,
protocol, production implementation, timeout or workload change was made.

Literal RED: three failures. GREEN: thirteen focused tests (six new, seven
existing). Scoped Ruff and diff checks PASS. One focused parent review found no
Important finding. Live Docker rerun remains pending at this commit.

raw-index.json binds fifty verified artifacts across the original failed run and
regression package. Canonical text and copied manifests normalize line endings;
the index binds the actual retained raw manifest bytes. No Linux capacity, server,
physical-core or NIC result follows from the diagnostic Direct terminal record.
