# Rust B3 cleanup gate correction

The Linux compatibility raw audit found that the inherited B3 controller checked
eight ownership fields, despite newer documentation referring to eleven. It
omitted pending-route, channel-registry and stream-registry current entries.

Rust B3 now uses the shared `post_close_cleanup.FIELDS` list for destination,
source-final and each same-process cycle report. All eleven values must be exact
integers equal to zero; missing, nonzero, Boolean and string values fail. Source
final and cycle report counts must match the expected counts. The historical Go
destination-only eight-field path is unchanged and explicitly labelled.

Literal RED:42 missing-helper failures. GREEN:85 focused tests, Ruff PASS.
The twelve accepted Linux compatibility raw cells were replayed through the new
gate:24final source/destination and9source cycle reports PASS. This is additional
postprocessing evidence, not a new workload run or a rewrite of original records.
Those original controller records retain their eight-field scope and older Rust
binary source classification. The failed first capture remains invalid.

Raw repair evidence: `C:/NBSR-build/b3-cleanup-11-20260906`.
Compatibility evidence: `evidence/performance/v2/linux-b3-compatibility-1cca67ad/`.

Parent focused review PASS; fresh parent42 cleanup tests PASS. Canonical evidence:
`evidence/performance/v2/b3-cleanup-11-field-7bac0ca8/`.
