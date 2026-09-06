# Rust B3 eleven-field cleanup gate

Literal RED42 missing-helper failures precede implementation. Focused GREEN85
passes, RuffPASS; parent independently42cleanup testsPASS and scoped review
found no Important issues. Exact tested code/test bytes: raw/source-hashes.json.
Final documentation/plan bindings: raw/final-source-hashes.json.

Rust B3 now checks shared FIELDS (all11) for exact integer zero in destination,
source final and every same-process cycle, with exact expected report counts.
Missing/nonzero/bool/string values in each of the3previously omitted fields are
covered in each report role. Historical Go destination8field behavior remains
unchanged and explicitly labelled. No Rust/transport/workload/timeout changes.

raw/replay.json replays12accepted older-binary Linux compatibility cells through
the new gate:24final reports+9source cycle reportsPASS. This is postprocessing,
not12new runs. Compatibility raw records remain unchanged in the separately
committed linux-b3-compatibility-1cca67ad package (including invalid firstcapture).
No benchmark or Docker was rerun for the postprocessing correction.
