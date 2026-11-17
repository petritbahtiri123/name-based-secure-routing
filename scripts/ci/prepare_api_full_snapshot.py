"""No-spend full-scope preparation at latest remote dev; never a live analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ci.api_repository_plan import exclusion, plan
from scripts.ci.prepare_api_snapshot import REPO, REF, reject_links, resolve_latest

MAX_FILE = 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def git_bytes(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(["git", *args], cwd=repo, input=data, capture_output=True, timeout=30, check=False, env=env)
    if result.returncode:
        raise ValueError("exact Git snapshot unavailable; no fetch or local-HEAD fallback")
    return result.stdout


def read_inventory(repo: Path, commit: str, cache_root: Path | None = None) -> tuple[list[dict], dict[str, bytes]]:
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("invalid commit")
    origin = git_bytes(repo, "remote", "get-url", "origin").decode().strip()
    if origin not in {f"https://github.com/{REPO}.git", f"https://github.com/{REPO}", f"git@github.com:{REPO}.git"}:
        raise ValueError("wrong source repository")
    raw = git_bytes(repo, "ls-tree", "-rz", commit)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("tree metadata exceeds bound")
    entries = []
    for row in raw.split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        mode, kind, sha = metadata.decode("ascii").split()
        if not re.fullmatch("[0-9a-f]{40}", sha):
            raise ValueError("invalid tree object")
        entries.append({"path": name.decode("utf-8"), "mode": mode, "sha": sha})
    if len(entries) > 50000:
        raise ValueError("tree entry bound exceeded")
    eligible = [e for e in entries if not exclusion(e["path"], e["mode"])]
    ids = sorted({e["sha"] for e in eligible})
    if not ids:
        return entries, {}
    sizes = {}
    check = git_bytes(repo, "cat-file", "--batch-check", data=("\n".join(ids) + "\n").encode()).decode("ascii").splitlines()
    if len(check) != len(ids):
        raise ValueError("incomplete object metadata")
    for sha, row in zip(ids, check):
        parts = row.split()
        if parts == [sha, "missing"]:
            continue
        if len(parts) != 3 or parts[:2] != [sha, "blob"]:
            raise ValueError("unexpected object metadata")
        size = int(parts[2])
        if not 0 <= size <= MAX_FILE:
            raise ValueError("source file exceeds bound")
        sizes[sha] = size
    if sum(sizes.values()) > MAX_TOTAL:
        raise ValueError("source total exceeds bound")
    present = sorted(sizes)
    blobs = {}
    if present:
        output = git_bytes(repo, "cat-file", "--batch", data=("\n".join(present) + "\n").encode())
        offset = 0
        for sha in present:
            end = output.index(b"\n", offset)
            if output[offset:end] != f"{sha} blob {sizes[sha]}".encode():
                raise ValueError("object changed during read")
            offset = end + 1
            blobs[sha] = output[offset : offset + sizes[sha]]
            offset += sizes[sha]
            if output[offset : offset + 1] != b"\n":
                raise ValueError("truncated object")
            offset += 1
        if offset != len(output):
            raise ValueError("unexpected object data")
    if cache_root is not None:
        reject_links(cache_root.absolute())
        for sha in set(ids) - set(blobs):
            path = cache_root / sha
            reject_links(path)
            if path.is_file():
                with path.open("rb") as f:
                    data = f.read(MAX_FILE + 1)
                if len(data) > MAX_FILE:
                    raise ValueError("cached source exceeds bound")
                blobs[sha] = data  # plan() verifies exact Git identity before use.
                sizes[sha] = len(data)
    if sum(map(len, blobs.values())) > MAX_TOTAL:
        raise ValueError("source total exceeds bound")
    for e in eligible:
        e["size"] = sizes.get(e["sha"])
    return entries, blobs


def prepare(parent: Path, repo: Path, *, resolve=resolve_latest, inventory=read_inventory) -> Path:
    commit = resolve()
    entries, blobs = inventory(repo, commit)
    report = plan(commit, entries, blobs.get)
    report.update(
        repository=REPO,
        ref=REF,
        scope="code-docs-configuration",
        openai_api_calls=0,
        live_execution_authorized=False,
        preparation_complete=not any(e["status"] == "unavailable" for e in report["files"]),
        next_gate="Independent scope review and separately approved full weekly cost preflight required.",
    )
    report["source_set_sha256"] = hashlib.sha256(
        json.dumps([(e["path"], e.get("sha256")) for e in report["files"] if e["status"] == "planned"], separators=(",", ":")).encode()
    ).hexdigest()
    reject_links(parent.absolute())
    parent.mkdir(parents=True, exist_ok=True)
    output = parent / commit
    output.mkdir()
    source_dir = output / "sources"
    source_dir.mkdir()
    written = set()
    for e in report["files"]:
        if e["status"] == "planned" and e["git_blob"] not in written:
            with (source_dir / e["git_blob"]).open("xb") as f:
                f.write(blobs[e["git_blob"]])
            written.add(e["git_blob"])
    with (output / "snapshot.json").open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path)
    args = parser.parse_args()
    try:
        out = prepare(args.output_root, args.repo, inventory=lambda repo, commit: read_inventory(repo, commit, args.cache_root))
        report = json.loads((out / "snapshot.json").read_text())
        print(
            json.dumps(
                {
                    "commit": report["commit"],
                    "preparation_complete": report["preparation_complete"],
                    "openai_api_calls": 0,
                    "manifest": str(out / "snapshot.json"),
                }
            )
        )
        return 0 if report["preparation_complete"] else 2
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Full preparation failed closed; no stale source or live analysis used.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
