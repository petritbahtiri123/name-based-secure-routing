# Linux resource sampler compatibility evidence

Classification: SAMPLER_PRIMITIVE_PASS; Linux container compatibility only.
Source base: bf53b8d4fbbd512ae925496f13f5f9dabef35214 plus the exact sampler/test
sources bound by raw/source-hashes.json. Final documentation/plan bindings are
in raw/final-source-hashes.json. No B3/B4/B5 port or external hardware claim.

- parser-red.txt: literal missing-module import failure before implementation.
- lifecycle-red.txt:25 missing-class failures,18 reader tests pass before class.
- final-pytest.txt:49 focused tests pass; final-ruff.txt:PASS.
- linux.stdout.ndjson: real Linux owned-child private-resident and same-identity
  zombie/null-memory records, child joined, PASS. linux.exit.txt:0.
- container-inspect.json: exact existing image and enforced restrictions;
  container-cleanup.txt identifies the inspected stopped container removed.
- Parent scoped review: no Important/Critical issues in the three implementation
  files and existing process-reader boundary.

The staged diagnostic uses a namespace scripts package (no scripts/__init__.py
exists in the repository). Only needed Python files were mounted read-only.
No container build, privilege, network or host policy changes were made.

All evidence paths are hash-bound in checksums.sha256; raw/checksums.sha256
retains the external package index. Original documentation copy predates the
canonical evidence link; final-source-hashes.json explicitly binds that addition.
