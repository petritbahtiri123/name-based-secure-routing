from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "demo-video"
REQUIRED = {
    "README.md",
    "narration-script.md",
    "shot-list.md",
    "recording-checklist.md",
    "subtitles.srt",
    "terminal-commands.txt",
    "architecture-demo.mmd",
    "title-card.html",
    "security-summary.html",
    "codex-contribution.html",
    "closing-card.html",
    "assets/README.md",
}


def test_all_video_package_files_exist():
    missing = sorted(path for path in REQUIRED if not (VIDEO / path).is_file())
    assert missing == []


def test_video_demo_has_required_modes_and_delegates_real_scenarios():
    script = (ROOT / "scripts/video-demo.ps1").read_text(encoding="utf-8")
    assert "Set-StrictMode -Version Latest" in script
    assert "$ErrorActionPreference = \"Stop\"" in script
    assert "[switch]$NoPause" in script
    assert "[switch]$Rehearsal" in script
    assert "demo.py" in script


def test_video_demo_refreshes_local_credentials_before_running_scenarios():
    powershell = (ROOT / "scripts/video-demo.ps1").read_text(encoding="utf-8")
    bash = (ROOT / "scripts/video-demo.sh").read_text(encoding="utf-8")

    assert powershell.index("bootstrap.ps1") < powershell.index("demo.py")
    assert bash.index("bootstrap.sh") < bash.index("demo.py")


def test_video_demo_prepares_short_lived_demo_ticket_before_visible_run():
    powershell = (ROOT / "scripts/video-demo.ps1").read_text(encoding="utf-8")
    bash = (ROOT / "scripts/video-demo.sh").read_text(encoding="utf-8")

    assert '$env:NBSR_TICKET_TTL_SECONDS = "2"' in powershell
    assert powershell.index("docker compose up -d --no-build") < powershell.index("Clear-Host")
    assert "NBSR_TICKET_TTL_SECONDS=2 docker compose up -d --no-build" in bash
    assert bash.index("NBSR_TICKET_TTL_SECONDS=2") < bash.index("clear")


def parse_time(value: str) -> int:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def test_subtitles_are_sequential_non_overlapping_and_end_before_175_seconds():
    blocks = (VIDEO / "subtitles.srt").read_text(encoding="utf-8").strip().split("\n\n")
    previous_end = 0
    for expected_number, block in enumerate(blocks, 1):
        lines = block.splitlines()
        assert int(lines[0]) == expected_number
        match = re.fullmatch(r"(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})", lines[1])
        assert match
        start, end = map(parse_time, match.groups())
        assert previous_end <= start < end
        previous_end = end
    assert previous_end < 175_000


def test_html_assets_are_offline_script_free_and_16_by_9():
    for name in ("title-card.html", "security-summary.html", "codex-contribution.html", "closing-card.html"):
        text = (VIDEO / name).read_text(encoding="utf-8").lower()
        assert "aspect-ratio: 16 / 9" in text
        assert "<script" not in text
        assert "http://" not in text
        assert "https://" not in text


def test_package_avoids_prohibited_claims_and_secret_material():
    text = "\n".join(path.read_text(encoding="utf-8") for path in VIDEO.rglob("*") if path.is_file()).lower()
    for phrase in ("unhackable", "production ready", "revolutionary", "dns replacement", "begin private key", "authorization: bearer", "authorization: nbsr"):
        assert phrase not in text


def test_subtitles_match_spoken_narration():
    narration = (VIDEO / "narration-script.md").read_text(encoding="utf-8").split("### Optional pronunciation")[0]
    spoken_lines = [
        line for line in narration.splitlines()
        if line and not line.startswith("#") and not line.startswith("**")
    ]
    subtitles = (VIDEO / "subtitles.srt").read_text(encoding="utf-8")
    subtitle_lines = [
        line for line in subtitles.splitlines()
        if line and not line.isdigit() and "-->" not in line
    ]
    def normalize(value: list[str]) -> list[str]:
        return re.sub(r"[`*_]", "", " ".join(value).replace("\n", " ")).split()

    assert normalize(spoken_lines) == normalize(subtitle_lines)
