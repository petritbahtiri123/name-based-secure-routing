> Scope: component-level implementation notes retained from development. Historical test counts and verification paths below describe development evidence that is intentionally not distributed. See [current setup and delivery status](../README.md) for the integrated workflow. A standalone component does not start a collector.

# Prefix bridge integration (2026-11-14)

Status: local consumer verified, **not an activated live remote collector**.

`lab.bridge.PrefixBridge(capture_directory, inbox, source_identity, experiment)`
accepts complete growing raw byte prefixes through `accept(prefix_bytes)`.
Use one new private capture directory and unique experiment per actual run.
`finish()` requires a parsed final and closes only local persistence; it does
not establish campaign validity, remote cleanup or clock qualification.

The authenticated acquisition owner must bind the run/control identity to the
exact regular source stdout file, reject file replacement, preserve byte zero,
and supply immutable prefix snapshots (maximum adapter bound, currently 4 MiB).
The bridge compares all previously accepted bytes, so rewrites and truncation
fail closed. File identity itself is not authenticated by this bridge. Equal
prefixes produce no publication; partial lines remain buffered. One call every
five seconds is sufficient; no repeated historical replay as live.

The bridge enables the origin-record contract: origin bytes remain in raw.bin
and the extraction ledger but do not become fabricated chart samples. Only
validated grouped snapshots are atomically exported using existing feed.export.
No polling, subprocess, SSH, benchmark lifecycle control or production writes
are started by importing the module. It cannot recover/reuse an old capture
directory after failure. Preserve evidence, stop only the collector, and report
failure separately; older delivery packets remain historical evidence.

UI must prominently label source progress/final as NOT overall campaign PASS.
Source final can coexist with invalid post-calibration or unresolved cleanup.
Acquisition must have a bounded owned lifetime, pinned host validation and one
outstanding reader. Initial remote integration is diagnostic and observer cost
must be disclosed; this local test proves no remote interference claim.

Validation: full local suite 127 passed in 6.55 seconds. Seven new tests cover
origin forwarding, prefix dedup/raw retention, truncation, rewrite, malformed
records, partial lines and exporter failure. Windows restricted sandbox denied
existing hard-link publication; unrestricted local test invocation passed.
No real next-run acquisition or production inbox was activated.

## Owned acquisition implementation

`lab/remote_reader.py` is standalone stdlib code for the remote Python process.
It writes no remote files and launches no subprocess. Required arguments:
`--source ABSOLUTE_EXACT_STDOUT --run UNIQUE_RUN --seconds 1..90 --wire-bytes N`.
N is cumulative emitted JSON bytes (1..4MiB), NOT just one frame. Choose N from
the existing aggregate budget; source maximum remains4MiB. Unchanged prefixes
are not emitted. Poll cadence5seconds. Exact regular-file dev/inode and prefix
are checked every observation; replacement/truncate/rewrite/budget breach fails.
It exits when a complete last source line has grouped-final schema, or lifetime
expires. Neither is a campaign success assertion. Full parser validation remains
local and rejects malformed source even if the reader observed a final marker.

Local `FramedBridge(captureDir,inbox,run,source)` validates exact envelope fields,
run/path/file identity, contiguous sequence and base64; `FrameLogPump(consumer,
wireBudget).poll(stdoutLog)` reads the owned acquisition output without newnetwork,
buffers partial framing and rejects local log replacement/rewrite/truncation.
Caller must stop the pump on failure and surface acquisition failure explicitly.

Use the existing candidate's bounded.run generic argv launcher: its Windows Job
contains worker, SSH and jump descendants, while stdout.log grows during capture.
Do NOT introduce an unmanaged subprocess launcher. Its owner deadline is capped
by coordinator105s; leave startup/drain margin below work bound. Pin existingSSH
host verification and execute only this exact script with safely quoted args.
Bind hashes/run/path in the candidate manifest before starting. No installation
or dependency is required on VM beyond existingPython3.

Start after TLS setup and before freshPRE so startup does not age PRE. Read-only
management traffic, extra CPU and full cleanup guard scans are observable costs;
remote final polling can lag5seconds, cleanup may overlap POST. Do not treat this
as zerooverhead or a comparison-qualified benchmark. Reader/pump/source/inbox/raw
snapshots must fit the SAME16MiB aggregate budget, not separate unlimited budgets.
Stop/reap only reader resources and preserve its evidence; do not signal workload.

Validation now137passed7.97seconds, including finite real local process expiry,
early source-final exit and wire-budget failure. Remote launch/owned integration
has not been executed; no live/campaign readiness claim follows from local tests.

START readiness added: reader emits nbsr-lab-reader-start-v1 before sourceexists,
with exactrun/source, waiting-for-source, cadence_seconds5, lifetime_seconds and
wire_budget. FramedBridge.started is true only after validatedSTART; it is NOT
source existence or clock qualification. Prefix/end withoutSTART fails. Latest
fullsuite139passed8.92s. Currentcodehashes are supplied to continuationowner for
itsfreeze; olderhashes/reports above describe earlierlocaliterations only.
