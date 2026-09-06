# Bounded controller preparation

Base 3951dbc5. This stage adds the executable Windows grouped B5 controller;
it has not yet run live and establishes no soak/capacity result.

The stdout reader holds at most sixteen 64 KiB chunks. A polling consumer checks
the fixed source-launch deadline (warmup + measurement + existing 92-second
phase allowance) and resource health even during silence. Destination stdout
and all stderr go directly to retained files. Failure kills owned processes,
drains remaining observed stdout to raw evidence and joins the reader.

Resource/progress retention has explicit bounds derived from duration and sample
cadence. Private-growth checks cover each destination separately; drift excludes
mixed/drain intervals. Resource phase alignment is receive-clock approximate,
not synchronized process-clock evidence. Final NBSR eleven-counter reports and
all process exits are checked. Graceful internal thread joins on failure are
NOT_MEASURED. No thermal, live ownership, or STABLE claim is generated.

Soak mode requires a current clean-SHA, hash-verified ceiling, matching binaries,
shape, physical pool masks and stable topology fields. Those reference fields
come from the same checksum-verified bytes used by the loader. The topology API
does not identify a unique host: TOPOLOGY_ONLY_NO_HOST_ID. The run verifies the
same clean source again before summary. Diagnostic mode requires an explicit
rational rate, is separately labeled and cannot consume a ceiling. Normal mode
requires three valid repeats, five when CV exceeds 5%; failed runs remain retained.

Literal controller import RED and seven placement/source-binding RED failures
are retained. Final focused controller/ceiling/stream verification: 53 PASS.
Scoped Ruff and diff checks PASS. One focused parent review found the reference
placement gap; the tested binding closes it. No remaining Important finding in
the scoped re-review. Live execution, observer qualification, continuous resource
ownership coverage and long-soak acceptance remain pending.
