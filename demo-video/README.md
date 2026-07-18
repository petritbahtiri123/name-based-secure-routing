# NBSR Demo Video Production Package

This package supports a single continuous 2:48 narrated screen recording. It
does not contain a fabricated recording or generated voice track.

## Files

- `narration-script.md`: timestamped spoken script and pronunciation help.
- `shot-list.md`: exact one-take screen sequence.
- `recording-checklist.md`: privacy, preflight, recording, and upload checks.
- `subtitles.srt`: timed UTF-8 captions matching the narration.
- `terminal-commands.txt`: exact rehearsal and validation commands.
- `architecture-demo.mmd`: 1080p-friendly Mermaid architecture source.
- `title-card.html`: offline opening frame.
- `security-summary.html`: offline security-control frame.
- `codex-contribution.html`: factual human/Codex contribution split.
- `closing-card.html`: offline final frame and public repository.
- `assets/`: destination for locally rendered images or recording exports.

## Recommended tools

OBS Studio is recommended because it supports a fixed 1920×1080 canvas,
microphone monitoring, window capture, and local recording without paid
services. Windows Game Bar is the simplest alternative. Clipchamp can record
and trim dead time. Do not install or pay for anything solely for this package.

## Prepare and rehearse

From the repository root:

```powershell
docker compose up -d --build
./scripts/video-demo.ps1 -NoPause
./scripts/video-demo.ps1 -Rehearsal
```

The first command validates the real run without presentation delays. The
second is the spoken rehearsal. Both fail if services or scenarios fail.

Open each HTML file directly in a browser and use full-screen mode. No server or
internet connection is required. Render `architecture-demo.mmd` with a Mermaid
preview in an editor, Mermaid CLI if already installed, or GitHub's Mermaid
renderer. Keep labels readable at 1920×1080.

## Record the final take

1. Follow `recording-checklist.md`.
2. Arrange the title, architecture, PowerShell, security, contribution, GitHub,
   and closing windows in the order listed by `shot-list.md`.
3. Start OBS, show the title, narrate slowly, and use Alt+Tab between prepared
   windows.
4. Run `./scripts/video-demo.ps1` during the terminal segment.
5. Leave the closing repository URL visible through 2:48.

## Subtitles and upload

Import `subtitles.srt` into Clipchamp, YouTube Studio, or another local editor.
Do not burn captions over terminal results. After upload, open the YouTube link
in a private browser, confirm captions and 1080p readability, watch it once,
then add the verified URL to Devpost.

## Claim boundaries

Say “validated prototype,” not that NBSR is production-ready. NBSR does not
replace DNS; it adds authenticated authorization and short-lived route material
after naming. State that Compose was validated live and Kubernetes resources
passed offline validation, while live kind execution was not tested.
