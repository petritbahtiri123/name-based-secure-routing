# NBSR Demo Video Package Design

## Goal

Provide a one-take, narrated 2:20–2:55 OpenAI Build Week screen-recording
package centered on a real eight-scenario Docker Compose demonstration.

## Recording flow

The target duration is 2:48. The owner opens a local title card, a rendered
Mermaid architecture visual, a clean PowerShell terminal, two local summary
cards, the public GitHub repository, and a local closing card. The terminal
segment runs the real Compose services through a presentation wrapper that
delegates scenario execution to `scripts/demo.py`.

## Presentation wrapper

`video-demo.ps1` is the primary path. It validates Docker and Compose, confirms
the five required services exist and are ready, clears the screen only before
the visible run, prints eight numbered scenario headings, and invokes the
existing real scenario implementation once. `-NoPause` disables presentation
delays; `-Rehearsal` lengthens them. Any readiness or scenario failure exits
nonzero without clearing evidence. Bash provides equivalent practical behavior.

## Visual and narration assets

All HTML is standalone, offline, JavaScript-free, high-contrast 16:9 content.
The architecture remains consistent with the repository: DNS/name resolution
is a bootstrap layer, OPA authorizes, the control plane signs, Envoy enforces,
the verifier has only the public key, and the backend remains isolated.
Narration stays below 360 words and makes only validated prototype claims.

## Validation

Automated tests verify required files, wrapper switches, subtitle ordering,
offline HTML, prohibited claims, and secret hygiene. Live validation runs the
Python suite, Ruff, OPA tests, Compose parsing/health, and the no-pause video
demo. No video, voice track, or upload is fabricated.
