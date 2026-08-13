# P1/P2 Test Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a trustworthy full repository gate at local `codex/nbsr-v3-wp0-wp1` before pushing that branch, without weakening frozen protocol, replay, admission, or federation authorities.

**Architecture:** First make byte-locked repository inputs checkout-stable under Windows `core.autocrlf=true`, then reclassify the remaining failures from fresh focused runs. Preserve the original Core lock and F75 overlay byte-for-byte; if later P1/P2 source changes require a new additive overlay, produce an exact candidate and stop for explicit approval before treating it as authority. Run the Windows wire test from a prebuilt external Cargo target instead of weakening or skipping it.

**Tech Stack:** Git attributes, Python 3.14, pytest, Rust 2024, Cargo/Quinn, Go/quic-go, Ruff, Git LFS, PowerShell.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`, currently based on `799cc93`; never modify, switch, merge, rebase, or push `main`.
- Keep `main` and `origin/main` equal to `1938154d498b32d81a3564319969430644e8a688`.
- Preserve the original Core v0.2 baseline lock digest `21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef`.
- Preserve P1F complete replay history and exact 10,000-entry hard-cap semantics.
- Preserve P2D V1 no-downgrade enforcement, actual Quinn stream handles, payload-before-ACCEPT quarantine, and Attempt 8 authority.
- Do not restore rejected P2C production behavior.
- Do not skip, xfail, or relabel a semantically failing test to obtain green status.
- Treat Windows Application Control `os error 4551` as a visible environment gate, never as PASS.
- Use exact path staging; never use `git add .`.
- Push only `HEAD:refs/heads/codex/nbsr-v3-wp0-wp1` after every mandatory gate passes and the remote target still has the expected lease value.

---

## File map

- `.gitattributes`: repository-owned working-tree byte policy; must retain the existing historical CRLF-preservation exception and LFS rules.
- `tests/test_checkout_byte_stability.py`: executable contract for Git attributes and representative byte-locked paths.
- `docs/protocol/registries/core-v0.2-baseline-lock.json`: frozen original authority; inspect only, never modify.
- `docs/protocol/registries/core-v0.2-f75-overlay.json`: frozen four-path F75 authority; inspect only, never modify.
- `nbsr/federation/profile.py`: current fail-closed baseline/F75 validation; change only after a separately approved additive overlay exists.
- `tests/federation/test_baseline_immutability.py` and `tests/federation/test_f75_core_baseline_overlay.py`: existing RED evidence and later overlay regression surface.
- `docs/protocol/registries/core-v0.2-p1p2-overlay.candidate.json`: candidate authority generated only when Task 2 proves an authority conflict; it is not active authority.
- `docs/reviews/2026-08-13-p1-p2-test-failure-classification.md`: exact failure inventory, byte evidence, and authority decision gate.
- `tests/federation/test_independent_wire_peer.py`: live Go-to-Rust wire test; no skip or semantic weakening.
- `docs/reviews/2026-08-13-p1-p2-publication-verification.md`: final commands, counts, SHAs, LFS state, and publication evidence.

### Task 1: Make byte-locked checkout behavior deterministic

**Files:**
- Create: `tests/test_checkout_byte_stability.py`
- Modify: `.gitattributes`

**Interfaces:**
- Consumes: Git's `check-attr` output and the repository's byte-locked authority paths.
- Produces: `assert_checkout_attributes(repo: Path) -> None`, a test helper that fails when a locked text family does not resolve to `text=set,eol=lf` or when the historical approved-source exception stops resolving to `text=unset`.

- [ ] **Step 1: Write the attribute RED test**

Create `tests/test_checkout_byte_stability.py` with a subprocess helper that runs:

```python
ATTR_CASES = {
    "docs/protocol/core-v0.1-wire.md": ("set", "lf"),
    "docs/protocol/registries/core-v0.2-baseline-lock.json": ("set", "lf"),
    "vectors/core-v0.2/manifest.json": ("set", "lf"),
    "vectors/core-v0.2/README.md": ("set", "lf"),
    "interop/nbsr-go-peer/go.mod": ("set", "lf"),
    "interop/nbsr-go-peer/go.sum": ("set", "lf"),
    "docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt": ("unset", "unspecified"),
}

def _attribute(path: str, name: str) -> str:
    result = subprocess.run(
        ["git", "check-attr", name, "--", path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip().rsplit(": ", 1)[1]

def test_byte_locked_paths_have_explicit_checkout_policy() -> None:
    for path, (text_value, eol_value) in ATTR_CASES.items():
        assert _attribute(path, "text") == text_value, path
        assert _attribute(path, "eol") == eol_value, path
```

- [ ] **Step 2: Verify literal RED**

Run:

```powershell
python -m pytest tests/test_checkout_byte_stability.py -q
```

Expected: FAIL because the current attributes leave one or more locked families unspecified under global `core.autocrlf=true`.

- [ ] **Step 3: Add the minimum attribute policy**

Add these rules above the existing historical exception and LFS rules in `.gitattributes`:

```gitattributes
*.md text eol=lf
*.json text eol=lf
*.hex text eol=lf
*.py text eol=lf
*.rs text eol=lf
*.mjs text eol=lf
*.mod text eol=lf
*.sum text eol=lf
```

Keep the later line below unchanged so it overrides the broad text rule:

```gitattributes
docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt -text whitespace=cr-at-eol
```

Do not run repository-wide `git add --renormalize` and do not stage any authority, vector, source, or fixture content.

- [ ] **Step 4: Verify GREEN and no content rewrite**

Run:

```powershell
python -m pytest tests/test_checkout_byte_stability.py -q
git diff --name-only
git diff --check
```

Expected: one passing test; only `.gitattributes` and the new test appear in the diff; whitespace check exits 0.

- [ ] **Step 5: Commit the byte policy**

```powershell
git add -- .gitattributes tests/test_checkout_byte_stability.py
git diff --cached --name-only
git diff --cached --check
git commit -m "test: pin byte-stable checkout policy"
git show --check --stat --oneline HEAD
```

Expected staged paths: exactly the two named files.

### Task 2: Reproduce and classify every remaining failure cluster

**Files:**
- Create: `docs/reviews/2026-08-13-p1-p2-test-failure-classification.md`
- Create when required by evidence: `docs/protocol/registries/core-v0.2-p1p2-overlay.candidate.json`
- Inspect only: `docs/protocol/registries/core-v0.2-baseline-lock.json`
- Inspect only: `docs/protocol/registries/core-v0.2-f75-overlay.json`

**Interfaces:**
- Consumes: Task 1 attribute policy, existing pytest failures, Git blobs at `b1edfa8`, F75 overlay entries, and current `HEAD` bytes.
- Produces: a closed table with columns `cluster`, `representative_test`, `root_cause`, `semantic_status`, `required_action`, and `authority_impact`; optionally produces a non-active candidate overlay containing exact `path`, `length`, and lowercase SHA-256 entries.

- [ ] **Step 1: Materialize a disposable LF checkout**

Use a temporary sibling worktree outside OneDrive so the proof observes a fresh checkout:

```powershell
$auditRoot = Join-Path $env:TEMP 'nbsr-p1p2-byte-audit'
if (Test-Path -LiteralPath $auditRoot) { throw "audit path already exists: $auditRoot" }
git -c core.autocrlf=true worktree add --detach $auditRoot HEAD
git -C $auditRoot status --short --branch
```

Expected: detached clean worktree at the current commit.

- [ ] **Step 2: Run representative RED tests in the fresh checkout**

```powershell
python -m pytest tests/federation/test_baseline_immutability.py::test_core_v02_baseline_accepts_exact_110_artifact_inventory -q
python -m pytest tests/protocol/test_vectors.py::test_generator_is_deterministic_target_bounded_and_in_sync -q
python -m pytest tests/federation/test_repository_safety.py::test_dependency_inventory_is_closed_and_unchanged -q
python -m pytest tests/test_wp4_exporter_vectors.py::test_generator_check_and_independent_python_vectors -q
```

Run these commands with `workdir=$auditRoot`. Expected: vector/authority byte failures caused only by checkout conversion become GREEN; the baseline inventory test remains RED if current P1/P2 source bytes exceed the F75 overlay authority.

- [ ] **Step 3: Compute the exact remaining locked-source delta**

For every path in the baseline lock, compare current bytes against the original entry and the F75 replacement, using a read-only one-liner:

```powershell
@'
import hashlib, json, pathlib
root = pathlib.Path('.')
lock = json.loads((root/'docs/protocol/registries/core-v0.2-baseline-lock.json').read_bytes())
overlay = json.loads((root/'docs/protocol/registries/core-v0.2-f75-overlay.json').read_bytes())
approved = {x['path']: x for x in overlay['replacements']}
for path, original in sorted(lock['artifacts'].items()):
    data = (root/path).read_bytes()
    actual = {'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    expected = approved.get(path, original)
    if actual != {k: expected[k] for k in ('length', 'sha256')}:
        print(json.dumps({'path': path, 'expected': expected, 'actual': actual}, sort_keys=True))
'@ | python -
```

Expected: output only for current files that are not authorized by the frozen baseline plus F75 overlay. Any unrelated protocol/vector path is an independent regression and must be investigated before proceeding.

- [ ] **Step 4: Write the classification report and candidate only if required**

Record exact commands, exit codes, and every remaining path in `docs/reviews/2026-08-13-p1-p2-test-failure-classification.md`. If and only if the remaining set consists solely of already accepted P1F/P2D implementation paths, create `core-v0.2-p1p2-overlay.candidate.json` with this closed schema:

```json
{
  "format_version": 1,
  "authority_id": "NBSR-P1F-P2D-CORE-OVERLAY-CANDIDATE",
  "status": "CANDIDATE_NOT_AUTHORITY",
  "original_baseline": {
    "path": "docs/protocol/registries/core-v0.2-baseline-lock.json",
    "sha256": "21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef"
  },
  "parent_overlay": {
    "path": "docs/protocol/registries/core-v0.2-f75-overlay.json"
  },
  "replacements": []
}
```

Populate `parent_overlay.sha256` and `replacements` from observed bytes; keep replacements sorted by path. Do not edit `profile.py` or any test to consume the candidate.

- [ ] **Step 5: Remove the disposable worktree**

```powershell
git worktree remove $auditRoot
git worktree prune
```

Resolve and verify `$auditRoot` is under the intended temporary directory before removal.

- [ ] **Step 6: Commit the classification evidence**

```powershell
git add -- docs/reviews/2026-08-13-p1-p2-test-failure-classification.md
if (Test-Path 'docs/protocol/registries/core-v0.2-p1p2-overlay.candidate.json') {
  git add -- docs/protocol/registries/core-v0.2-p1p2-overlay.candidate.json
}
git diff --cached --name-only
git diff --cached --check
git commit -m "docs: classify P1 P2 repository gate failures"
```

Expected: only the report and, when required, the explicitly non-authoritative candidate.

- [ ] **Step 7: Mandatory authority checkpoint**

If a candidate overlay exists, stop execution and request explicit human approval of its exact path set, lengths, SHA-256 values, parent overlay digest, and activation semantics. Plan approval alone does not activate this candidate. If no candidate is needed, continue to Task 4.

### Task 3: Activate an explicitly approved P1F/P2D additive overlay

**Precondition:** Execute this task only after the Task 2 candidate receives explicit human approval. Otherwise this task is blocked by design.

**Files:**
- Rename/modify: `docs/protocol/registries/core-v0.2-p1p2-overlay.candidate.json` to `docs/protocol/registries/core-v0.2-p1p2-overlay.json`
- Modify: `nbsr/federation/profile.py`
- Modify: `tests/federation/test_baseline_immutability.py`
- Create: `tests/federation/test_p1p2_core_overlay.py`

**Interfaces:**
- Consumes: approved exact overlay bytes and the frozen F75 overlay.
- Produces: `assert_p1p2_core_overlay(root: Path) -> None`, which validates original baseline, F75 parent, a closed approved replacement set, safe paths, exact lengths/digests, complete inventory, and fail-closed mutation behavior.

- [ ] **Step 1: Write literal overlay RED tests**

Add tests covering: exact approved overlay passes; original baseline mutation fails; F75 parent mutation fails; each replacement mutation fails; missing/extra/duplicate replacement fails; fifth unauthorized path fails; `..`, absolute, backslash, case-alias, and symlink paths fail; unknown top-level/nested fields fail; length/digest type errors fail; and current baseline inventory still rejects missing/unlisted files.

The positive test must import a missing symbol so the first run is literal RED:

```python
from nbsr.federation.profile import assert_p1p2_core_overlay

def test_exact_approved_p1p2_overlay_passes() -> None:
    assert assert_p1p2_core_overlay(ROOT) is None
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/federation/test_p1p2_core_overlay.py -q
```

Expected: collection/import failure because `assert_p1p2_core_overlay` does not exist.

- [ ] **Step 3: Implement the minimal closed validator**

In `profile.py`, reuse `_read_json_authority` and `_safe_overlay_path`; add distinct P1/P2 constants and a validator that checks the approved document byte digest before parsing. Do not generalize F75 validation or replace `assert_f75_core_overlay`. Update the current-HEAD positive assertion in `test_baseline_immutability.py` to call both `assert_core_baseline_lock_authority(ROOT)` and `assert_p1p2_core_overlay(ROOT)`; retain the original F75-only tests against copied F75 fixtures.

- [ ] **Step 4: Verify GREEN and frozen F75 behavior**

```powershell
python -m pytest tests/federation/test_p1p2_core_overlay.py tests/federation/test_f75_core_baseline_overlay.py tests/federation/test_baseline_immutability.py -q
```

Expected: all selected tests pass; mutation and alias negatives remain fail closed.

- [ ] **Step 5: Commit the approved authority activation**

```powershell
git add -- docs/protocol/registries/core-v0.2-p1p2-overlay.json nbsr/federation/profile.py tests/federation/test_baseline_immutability.py tests/federation/test_p1p2_core_overlay.py
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: bind accepted P1F P2D core overlay"
git show --check --stat --oneline HEAD
```

### Task 4: Run the live wire test through an allowed external build path

**Files:**
- Modify only if RED proves the current environment contract is insufficient: `tests/federation/test_independent_wire_peer.py`
- Document: `docs/reviews/2026-08-13-p1-p2-publication-verification.md`

**Interfaces:**
- Consumes: existing `NBSR_TASK10B_CARGO_TARGET` and `NBSR_TASK10B_GO_PEER` environment hooks.
- Produces: a real cross-process Go-to-Rust PASS or a documented Application Control BLOCKED result; never a skip.

- [ ] **Step 1: Prebuild into the known external Cargo target**

```powershell
$env:CARGO_TARGET_DIR='C:\Users\bajra\.codex\cargo-target\nbsr-publish-verify'
cargo build --manifest-path crates/nbsr-transport/Cargo.toml --bin wp8_interop_server
go build -trimpath -o "$env:TEMP\nbsr-go-peer.exe" ./cmd/nbsr-go-peer
```

Run the Go command from `interop/nbsr-go-peer`. Expected: both commands exit 0.

- [ ] **Step 2: Run the exact live test with explicit binaries**

```powershell
$env:NBSR_TASK10B_CARGO_TARGET='C:\Users\bajra\.codex\cargo-target\nbsr-publish-verify'
$env:NBSR_TASK10B_GO_PEER="$env:TEMP\nbsr-go-peer.exe"
python -m pytest tests/federation/test_independent_wire_peer.py::test_cross_process_go_source_exchanges_frozen_route_and_stream -q
```

Expected: PASS with the real Go peer and Rust listener. If Application Control still blocks execution, record BLOCKED and stop; do not edit the test to skip.

- [ ] **Step 3: Add a RED regression only if the environment hooks are ignored**

If Step 2 proves that an existing hook is not propagated, add a focused test that supplies the hook and asserts the configured target/binary is executed; watch it fail, implement only the missing propagation, and rerun it GREEN. If the hooks work, make no code change and record the command/result only.

### Task 5: Full verification and explicit publication

**Files:**
- Modify: `docs/reviews/2026-08-13-p1-p2-publication-verification.md`

**Interfaces:**
- Consumes: completed Tasks 1-4 and approved authority state.
- Produces: exact fresh counts, protected-ref evidence, and a remote branch whose SHA equals local `HEAD`.

- [ ] **Step 1: Run Python gates**

```powershell
$env:NBSR_TASK10B_CARGO_TARGET='C:\Users\bajra\.codex\cargo-target\nbsr-publish-verify'
$env:NBSR_TASK10B_GO_PEER="$env:TEMP\nbsr-go-peer.exe"
python -m pytest -q --tb=short
python -m ruff check .
python -m ruff format --check .
```

Expected: full pytest has zero failures; Ruff commands exit 0. Record exact passed/skipped counts.

- [ ] **Step 2: Run Rust gates**

```powershell
$env:CARGO_TARGET_DIR='C:\Users\bajra\.codex\cargo-target\nbsr-publish-verify'
cargo test --manifest-path crates/nbsr-transport/Cargo.toml
cargo test --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness
cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check
cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets --features benchmark-harness -- -D warnings
```

Expected: zero failures and zero Clippy warnings; record exact test/ignored counts separately for both test commands.

- [ ] **Step 3: Run integrity gates**

```powershell
python tools/generate_core_v01_vectors.py --check
python scripts/generate_core_v02_vectors.py --check
python scripts/generate_federation_v01_vectors.py --check vectors/federation-v0.1
python scripts/generate_wp4_exporter_vectors.py --check
git lfs fsck
git diff --check
git status --short --branch
```

Expected: all generators and LFS checks pass; only the untracked pre-existing `.worktrees/` container may remain outside staging.

- [ ] **Step 4: Commit final verification evidence**

Write exact commands, exit codes, counts, local HEAD, remote target SHA, `main`, `origin/main`, and LFS result to the publication report, then:

```powershell
git add -- docs/reviews/2026-08-13-p1-p2-publication-verification.md
git diff --cached --name-only
git diff --cached --check
git commit -m "docs: record P1 P2 publication verification"
git show --check --stat --oneline HEAD
```

- [ ] **Step 5: Re-run lightweight post-commit guards**

```powershell
git status --short --branch
git diff --check
git lfs fsck
git rev-parse main
git rev-parse origin/main
git fetch origin
git rev-parse origin/codex/nbsr-v3-wp0-wp1
```

Expected: protected main SHAs remain `1938154d498b32d81a3564319969430644e8a688`. Stop if the remote target is no longer the expected pre-push SHA.

- [ ] **Step 6: Push only the named branch with an explicit refspec**

Capture the fetched remote target SHA as `$expectedRemote`, then:

```powershell
$expectedRemote = git rev-parse origin/codex/nbsr-v3-wp0-wp1
git push --force-with-lease=refs/heads/codex/nbsr-v3-wp0-wp1:$expectedRemote origin HEAD:refs/heads/codex/nbsr-v3-wp0-wp1
git fetch origin
$local = git rev-parse HEAD
$remote = git rev-parse origin/codex/nbsr-v3-wp0-wp1
if ($local -ne $remote) { throw "remote/local mismatch: $local != $remote" }
if ((git rev-parse main) -ne '1938154d498b32d81a3564319969430644e8a688') { throw 'local main moved' }
if ((git rev-parse origin/main) -ne '1938154d498b32d81a3564319969430644e8a688') { throw 'remote main moved' }
```

Expected: push succeeds under the exact lease; remote/local target SHAs match; both main refs remain unchanged. Do not open a PR.
