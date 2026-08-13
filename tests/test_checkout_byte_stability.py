from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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
