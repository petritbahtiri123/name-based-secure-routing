# Admission reference cells are not automatically stable

Task 4i labeled its first offered-rate cell `BASELINE` without applying absolute
error, completion-ratio or repeat-variation gates. Task 4k then counted that
label as a stable boundary. A reference role alone is insufficient evidence of
stability; this matters when starting a ladder near an already degraded rate.

Two literal RED regressions demonstrated the issue: an unclassified baseline
was counted as 125/s stable, and a first cell containing an error/timeout was
still labeled BASELINE. Summaries now apply existing classification gates even
to the reference cell, with its reference role recorded separately. Boundary
comparison counts only explicitly STABLE cells.

Thirteen focused admission tests passed. Ruff passed for Task 4k and both test
files. Task 4i retains 21 pre-existing compact-style Ruff violations (E701,
E702, E731); this correction does not conceal or suppress them.

Historical raw runs and accepted analysis files remain unchanged. In particular,
do not promote a historical Task 4k BASELINE label into a fresh strict-stable
claim. New capacity acceptance still requires enough valid repeats, a matched
low-load reference, current binary/source identity and the existing absolute
and relative workload gates. This changes evidence classification only, not
protocol behavior, workload, admission deadlines or production implementation.
