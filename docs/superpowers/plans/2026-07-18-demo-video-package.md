# NBSR Demo Video Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, validated package for recording the NBSR hackathon demo in one take.

**Architecture:** Static offline visuals and timed narration surround a real
Compose demo. Presentation wrappers validate readiness and delegate all security
outcomes to the existing scenario runner.

**Tech Stack:** Markdown, SRT, Mermaid, standalone HTML/CSS, PowerShell, Bash,
Python/pytest, Docker Compose.

## Global Constraints

- Do not alter security behavior, ticket lifetime, OPA decisions, Envoy fail-closed behavior, fixed routing, or network isolation.
- Do not print tokens, keys, Authorization headers, or generated secrets.
- Do not mock scenario results or claim production readiness.
- Target 2:48, within the required 2:20–2:55 window.

---

### Task 1: Package contract tests

**Files:** Create `tests/test_video_package.py`.

**Interfaces:** The tests consume the required file paths and validate SRT,
HTML, prohibited claims, and wrapper switches.

- [ ] Write tests that require every package asset, sequential non-overlapping
  subtitles, offline HTML, and `-NoPause`/`-Rehearsal`.
- [ ] Run `python -m pytest tests/test_video_package.py -q`; expect missing-file failures.

### Task 2: Presentation wrapper

**Files:** Create `scripts/video-demo.ps1`, `scripts/video-demo.sh`.

**Interfaces:** Both scripts call `scripts/demo.py`; PowerShell accepts
`-NoPause` and `-Rehearsal` and returns the child exit code.

- [ ] Implement prerequisite, service, health, presentation, and pause behavior.
- [ ] Run parser checks and `./scripts/video-demo.ps1 -NoPause`; expect eight real passes.

### Task 3: Narration and recording documents

**Files:** Create `demo-video/README.md`, `narration-script.md`, `shot-list.md`,
`recording-checklist.md`, `terminal-commands.txt`, `assets/README.md`.

- [ ] Write a 2:48 narration under 360 words and a one-take shot table.
- [ ] Document rehearsal, recording, subtitles, upload verification, and claim limits.

### Task 4: Visuals and subtitles

**Files:** Create `architecture-demo.mmd`, `title-card.html`,
`security-summary.html`, `codex-contribution.html`, `closing-card.html`,
`subtitles.srt`.

- [ ] Build offline 16:9 high-contrast assets with no JavaScript or external dependencies.
- [ ] Align subtitle blocks to narration with sequential, non-overlapping timestamps.
- [ ] Run `python -m pytest tests/test_video_package.py -q`; expect pass.

### Task 5: Optional rendering helpers

**Files:** Create `scripts/render-video-assets.ps1`,
`scripts/render-video-assets.sh`.

- [ ] Detect Mermaid CLI and optional rendering prerequisites without downloading tools.
- [ ] Render the Mermaid diagram when available and otherwise return an actionable error.

### Task 6: Full verification and publish

- [ ] Run pytest, Ruff, OPA tests, Compose config/build/health, no-pause video demo,
  PowerShell parsing, Bash syntax where available, content/security scans, and
  `git diff --check`.
- [ ] Commit only the video-preparation package and push `main`.
