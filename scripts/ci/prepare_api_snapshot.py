"""Prepare latest development CI sources without OpenAI calls or local-HEAD fallback."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re

REPO = "petritbahtiri123/name-based-secure-routing"
REF = "refs/heads/codex/nbsr-v3-wp0-wp1"
PATHS = ["docs/CI.md", "scripts/ci/check.py"]
MAX_BYTES = 98304
CONTROLS = {
    "scripts/ci/api_analysis.py": "46d7a284c78ae3090995ec0ccf8df999f6d4827b65f4928abd6e4d818d94b345",
    "scripts/ci/run_api_analysis.ps1": "70d8ee1e250729f5cdd74d2a402dc75207d65d852431d6885a9d4892557dc720",
}
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:password|api_key|access_token)\s*[:=]\s*['\"][^'\"]+['\"]"
)


def fetch_bytes(host: str, path: str, limit: int) -> bytes:
    if host not in {"api.github.com", "raw.githubusercontent.com"}:
        raise ValueError("unapproved host")
    connection = http.client.HTTPSConnection(host, timeout=20)
    try:
        connection.request("GET", path, headers={"User-Agent": "NBSR-read-only-snapshot"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("source retrieval failed; no redirect or retry")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("oversized source response")
        return data
    finally:
        connection.close()


def reject_links(path: Path) -> None:
    for item in [path, *path.parents]:
        if item.is_symlink() or item.is_junction():
            raise ValueError("linked path rejected")


def resolve_latest(*, fetch=fetch_bytes) -> str:
    """Return only the current remote development commit; never local HEAD."""
    raw_ref = fetch("api.github.com", f"/repos/{REPO}/git/ref/heads/codex/nbsr-v3-wp0-wp1", 16384)
    if len(raw_ref) > 16384:
        raise ValueError("oversized ref")
    ref = json.loads(raw_ref)
    obj = ref.get("object") if isinstance(ref, dict) else None
    if not isinstance(obj, dict) or ref.get("ref") != REF or obj.get("type") != "commit":
        raise ValueError("unexpected remote ref")
    commit = obj.get("sha")
    if not isinstance(commit, str) or not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("invalid remote commit")
    return commit


def prepare(parent: Path, trusted_root: Path, *, fetch=fetch_bytes) -> Path:
    """Resolve remote once, pin all reads to that SHA, and create an exclusive snapshot.

    The old approved controls are copied byte-for-byte; downloaded source is
    never imported or executed. A failed read never falls back to a laptop copy.
    """
    controls = {}
    for name, expected in CONTROLS.items():
        path = trusted_root / name
        reject_links(path)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("control changed; review and repin required")
        controls[name] = data
    reject_links(parent.absolute())
    commit = resolve_latest(fetch=fetch)
    sources, files, total = {}, [], 0
    for name in PATHS:
        data = fetch("raw.githubusercontent.com", f"/{REPO}/{commit}/{name}", MAX_BYTES)
        total += len(data)
        if total > MAX_BYTES or b"\0" in data:
            raise ValueError("binary or oversized source")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("non-UTF8 source") from None
        if SECRET.search(text):
            raise ValueError("possible credential; source requires review")
        sources[name] = data
        files.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "repository": REPO,
        "ref": REF,
        "commit": commit,
        "scope": "ci",
        "files": files,
        "controls": CONTROLS,
        "openai_api_calls": 0,
        "source_set_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        "limitation": "Two selected CI files at remote resolution time; not a whole-project analysis.",
    }
    parent.mkdir(parents=True, exist_ok=True)
    output = parent / commit
    output.mkdir()  # Exclusive: never overwrite a previous receipt/snapshot.
    for name, data in {**sources, **controls}.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as f:
            f.write(data)
    with (output / "snapshot.json").open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-root", type=Path)
    mode.add_argument("--resolve-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.resolve_only:
            print(json.dumps({"repository": REPO, "ref": REF, "commit": resolve_latest(), "openai_api_calls": 0}))
            return 0
        output = prepare(args.output_root, Path(__file__).resolve().parents[2])
        print(f"Prepared source snapshot (no OpenAI call): {output}")
        return 0
    except (ValueError, OSError, http.client.HTTPException):
        print("Snapshot preparation failed closed; no stale-source fallback or overwrite.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
