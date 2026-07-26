# NBSR WP0 Documentation Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Protocol Vision V3 the repository authority while preserving the hardened prototype, Vision V2, feasibility research, and all verified evidence.

**Architecture:** Merge the reviewed WP0 overlay into the newer hardened branch instead of overwriting it. Add the V3/history/research/protocol documents at repository-relative paths, then update the current README and documentation regression tests so direction and implemented behavior remain visibly separate.

**Tech Stack:** Markdown, PDF source artifacts, Python 3.12–3.13, pytest, Ruff, OPA/Rego, Docker Compose.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not modify `main`.
- Treat `NBSR_WP0_WP1_Ready_2026-07-26.zip` as an input overlay prepared from an older snapshot, not as an authoritative replacement for newer repository files.
- Preserve every existing runtime, deployment, test, and demonstration file.
- Preserve the existing enterprise and ISP-profile claims exactly where the branch has stronger current evidence.
- Vision V3 is authoritative; Vision V2 and the feasibility study remain accessible as historical/supporting sources.
- Do not claim that WP1, the universal Name Node, QUIC, federation, production readiness, or complete V3 conformance exists.
- Do not change dependencies, network behavior, routes, firewall rules, generated artifacts, or release contents in WP0.
- Run the focused documentation test first, then the full relevant suite.

---

### Task 1: Place authoritative, historical, research, and planning assets

**Files:**
- Create: `docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md`
- Create: `docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.pdf`
- Create: `docs/architecture/README.md`
- Create: `docs/history/NBSR_Protocol_Vision_v2.pdf`
- Create: `docs/history/README.md`
- Create: `docs/research/Name-Based-Secure-Routing-feasibility-study.pdf`
- Create: `docs/research/README.md`
- Create: `docs/protocol/terminology.md`
- Create: `docs/protocol/status.md`
- Create: `docs/protocol/wp1-decisions.md`
- Create: `docs/superpowers/plans/2026-07-26-wp1-protocol-data-model.md`
- Preserve: `docs/architecture/NBSR_Protocol_Vision_v2.pdf`
- Preserve: `docs/vision-v2-conformance.md`

**Interfaces:**
- Consumes: the verified repository overlay from `NBSR_WP0_WP1_Ready_2026-07-26.zip`.
- Produces: stable repository-relative documentation paths consumed by README links, documentation tests, and the later WP1 implementation.

- [ ] **Step 1: Verify package hashes before copying**

For every overlay file, compute SHA-256 and compare it with
`MANIFEST.sha256`, normalizing the manifest prefix
`output/NBSR_WP0_WP1_Ready_2026-07-26/` to the extracted package root.
The manifest's self-entry is excluded because it records the SHA-256 of an
empty pre-manifest placeholder rather than the finalized manifest.

Expected: every non-manifest entry matches its declared SHA-256.

- [ ] **Step 2: Confirm source and destination collisions**

Run:

```powershell
git status --short --branch
Get-ChildItem docs/architecture,docs/history,docs/research,docs/protocol -ErrorAction SilentlyContinue
```

Expected: the new V3/history/research/protocol destinations do not overwrite
tracked files. The existing Vision V2 PDF remains at its original architecture
path until all current links are deliberately migrated.

- [ ] **Step 3: Copy exact binary and Markdown assets**

Copy the files listed in this task from `repository-overlay/` to the exact
repository-relative paths. Do not copy the overlay README or
`tests/test_documentation.py` in this step.

- [ ] **Step 4: Verify copied hashes**

Compute SHA-256 for every copied asset and compare it with its staged overlay
source.

Expected: all pairs are byte-identical.

- [ ] **Step 5: Check the asset-only diff**

Run:

```powershell
git status --short
git diff --check
```

Expected: only the new documentation assets and plans appear, plus unrelated
pre-existing untracked files. No runtime or deployment file changes.

- [ ] **Step 6: Commit**

```powershell
git add -- docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md `
  docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.pdf `
  docs/architecture/README.md docs/history docs/research docs/protocol `
  docs/superpowers/plans/2026-07-26-wp1-protocol-data-model.md
git commit -m "docs: establish NBSR Protocol Vision V3 authority"
```

### Task 2: Merge resolver-first direction into the current README

**Files:**
- Modify: `README.md`
- Reference: `repository-overlay/README.md`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Consumes: the V3 document paths created by Task 1 and the current hardened
  README at commit `c0ade42`.
- Produces: primary project copy that explains resolver-first V3 while
  retaining current security-hardening, release, Kind, and test instructions.

- [ ] **Step 1: Add failing README assertions**

Extend `tests/test_documentation.py` with:

```python
def test_readme_separates_v3_direction_from_current_implementation() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    assert "NBSR Name Node resolves every configured name" in readme
    assert "Name/Resolution Plane" in readme
    assert "Secure Route/Tunnel Plane" in readme
    assert "not Protocol Core v0.1" in normalized
    assert "not a production system" in normalized
    assert "docs/protocol/status.md" in readme
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```powershell
python -m pytest tests/test_documentation.py::test_readme_separates_v3_direction_from_current_implementation -q
```

Expected: fail because the current README identifies Vision V2 and does not
yet contain the resolver-first/two-plane V3 language.

- [ ] **Step 3: Merge the V3 introduction and authority links**

Replace only the opening authority and architectural-direction sections with
the overlay's resolver-first language. Retain the current branch's:

- functional ISP-profile description;
- optional enterprise authorization description;
- security boundaries;
- exact supported Python range and pinned constraints;
- Compose and Kind instructions;
- deterministic release archive workflow;
- explicit limitations; and
- current documentation links.

Update the limitations and links to distinguish current prototype evidence
from V3 authority. Do not copy older commands, port claims, dependency
versions, or test counts from the overlay README when the current README is
newer.

- [ ] **Step 4: Run the focused test**

Run:

```powershell
python -m pytest tests/test_documentation.py::test_readme_separates_v3_direction_from_current_implementation -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add -- README.md tests/test_documentation.py
git commit -m "docs: align README with resolver-first Vision V3"
```

### Task 3: Enforce document precedence, preservation, and link integrity

**Files:**
- Modify: `tests/test_documentation.py`
- Modify: `docs/architecture.md`
- Modify: `docs/security-model.md`
- Modify: `docs/threat-model.md`
- Modify: `docs/vision-v2-conformance.md`
- Modify: `docs/security-hardening-report.md`

**Interfaces:**
- Consumes: the WP0 document tree and status vocabulary.
- Produces: regression coverage proving V3 precedence without rewriting
  historical V2 evidence.

- [ ] **Step 1: Add failing structure and link tests**

Add the overlay's local-link helper and these checks to the existing
`tests/test_documentation.py`, preserving all current tests:

```python
def test_wp0_sources_are_preserved() -> None:
    assert (DOCS / "architecture" / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md").is_file()
    assert (DOCS / "architecture" / "NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.pdf").is_file()
    assert (DOCS / "history" / "NBSR_Protocol_Vision_v2.pdf").is_file()
    assert (DOCS / "research" / "Name-Based-Secure-Routing-feasibility-study.pdf").is_file()


def test_protocol_status_defines_required_vocabulary() -> None:
    status = (DOCS / "protocol" / "status.md").read_text(encoding="utf-8")
    for word in ("Implemented", "Partial", "Planned", "Normative"):
        assert f"| {word} |" in status
    assert "does not imply Core v0.1 conformance" in status
```

Extend the local-link test over:

```python
(
    ROOT / "README.md",
    DOCS / "architecture" / "README.md",
    DOCS / "history" / "README.md",
    DOCS / "research" / "README.md",
    DOCS / "protocol" / "status.md",
)
```

- [ ] **Step 2: Run focused documentation tests**

Run:

```powershell
python -m pytest tests/test_documentation.py -q
```

Expected: failures identify remaining V2-authority wording or broken links;
existing hash and evidence-vocabulary tests continue to run.

- [ ] **Step 3: Add contextual V3 notices**

Update current architecture and security overview documents so they point to
Vision V3 as current authority. In historical evidence documents, add a short
notice that the report records the Vision V2 baseline and has not been
retroactively converted into V3 implementation evidence.

Keep the existing Vision V2 PDF hash test against its original path and add a
second hash assertion proving the preserved history copy is byte-identical:

```python
assert hashlib.sha256(
    (DOCS / "history" / "NBSR_Protocol_Vision_v2.pdf").read_bytes()
).hexdigest() == VISION_SHA256
```

- [ ] **Step 4: Run focused documentation tests and link scan**

Run:

```powershell
python -m pytest tests/test_documentation.py -q
```

Expected: all documentation tests pass and no local target is missing.

- [ ] **Step 5: Commit**

```powershell
git add -- tests/test_documentation.py docs/architecture.md `
  docs/security-model.md docs/threat-model.md `
  docs/vision-v2-conformance.md docs/security-hardening-report.md
git commit -m "test(docs): enforce Vision V3 precedence and preservation"
```

### Task 4: Verify WP0 and freeze the handoff to WP1

**Files:**
- Modify: `docs/protocol/status.md` only if observed test evidence differs from
  the prepared snapshot.
- Verify: all WP0 documentation and existing runtime files.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: a tested WP0 baseline and a still-unapproved WP1 decision gate.

- [ ] **Step 1: Run the full Python suite**

Run:

```powershell
python -m pytest -q
```

Expected: every existing test and the new documentation tests pass. Report the
observed count; do not copy the package snapshot's older count.

- [ ] **Step 2: Run static and policy checks**

Run:

```powershell
python -m ruff check .
python -m ruff format --check .
opa test policy -v
docker compose config --quiet
```

Expected: Ruff passes, five OPA tests pass, and Compose validates. If a tool is
unavailable, record the exact command and reason instead of claiming success.

- [ ] **Step 3: Confirm WP0 changed no runtime behavior**

Run:

```powershell
git diff c0ade42 --name-only
```

Expected: only `README.md`, `docs/**`, and `tests/test_documentation.py`.

- [ ] **Step 4: Review WP1 decision gate**

Read `docs/protocol/wp1-decisions.md` and present D1–D5 for explicit human
approval. Do not edit `pyproject.toml`, add `cbor2` or Hypothesis, or create
`nbsr/protocol/` until approval is recorded.

- [ ] **Step 5: Commit observed status evidence if needed**

If `docs/protocol/status.md` required an evidence correction:

```powershell
git add -- docs/protocol/status.md
git commit -m "docs: record verified WP0 status"
```

If no correction was required, do not create an empty commit.

