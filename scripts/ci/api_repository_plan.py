"""Offline, source-free coverage plan. Does not call an API or authorize upload."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
import re

BINARY = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp4", ".woff", ".woff2", ".bin", ".cbor", ".der", ".zip", ".gz"}
SUPPORTED = {
    ".py",
    ".go",
    ".rs",
    ".md",
    ".txt",
    ".rst",
    ".adoc",
    ".ps1",
    ".psm1",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".sh",
    ".bash",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".xml",
    ".mod",
    ".rego",
    ".mmd",
    ".srt",
    ".dockerfile",
    ".wprp",
    ".in",
}
SUPPORTED_NAMES = {"dockerfile", "makefile", "license", "copying", "notice", ".gitignore", ".gitattributes", ".dockerignore"}
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:password|api_key|access_token)\s*[:=]\s*['\"][^'\"]+['\"]"
)


def exclusion(path: str, mode: str) -> str | None:
    p = PurePosixPath(path)
    if mode not in {"100644", "100755"}:
        return "non-regular"
    if {s.lower() for s in p.parts} & {"evidence", "archive", "archives", "weekly-evidence"} or path.lower().startswith(
        (".superpowers/sdd/", "docs/history/")
    ):
        return "archive"
    if p.name == ".env" or p.name.startswith(".env.") or p.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return "credential-path"
    if p.suffix.lower() in BINARY:
        return "binary-media"
    if p.suffix == ".snapshot" or p.name in {"Cargo.lock", "package-lock.json", "go.sum"} or "artifacts" in p.parts:
        return "generated"
    if (
        p.suffix.lower() not in SUPPORTED
        and p.name.lower() not in SUPPORTED_NAMES
        and path != "tools/demo-lab/container/demo-container-worker"
    ):
        return "unsupported-category"
    return None


def plan(commit: str, entries: list[dict], read_blob, chunk_bytes: int = 98304) -> dict:
    """Read verified Git blobs via caller; None means unavailable, never omitted silently.

    Chunks are byte ranges with UTF-8 boundaries. Metadata contains no source text.
    Reader must return exact committed bytes, not working-tree substitutions.
    """
    if not re.fullmatch("[0-9a-f]{40}", commit) or type(chunk_bytes) is not int or not 4 <= chunk_bytes <= 98304:
        raise ValueError("invalid commit or chunk bound")
    files, seen, total = [], set(), 0
    for e in sorted(entries, key=lambda x: x["path"]):
        name = e["path"]
        if not isinstance(e["sha"], str) or not re.fullmatch("[0-9a-f]{40}", e["sha"]):
            raise ValueError("invalid blob identity")
        p = PurePosixPath(name)
        if not name or name in seen or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name or str(p) != name:
            raise ValueError("invalid or duplicate path")
        seen.add(name)
        item = {"path": name, "git_blob": e["sha"], "bytes": e.get("size"), "status": "excluded"}
        reason = exclusion(name, e["mode"])
        if reason:
            item["reason"] = reason
            files.append(item)
            continue
        data = read_blob(e["sha"])
        if data is None:
            item.update(status="unavailable", reason="missing-blob")
            files.append(item)
            continue
        digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if digest != e["sha"] or (e.get("size") is not None and len(data) != e["size"]):
            raise ValueError("blob identity mismatch")
        try:
            text = data.decode("utf-8")
            reason = "binary-content" if b"\0" in data else "possible-credential" if SECRET.search(text) else None
        except UnicodeDecodeError:
            reason = "non-utf8"
        if reason:
            item["reason"] = reason
        else:
            chunks, start = [], 0
            while start < len(data):
                end = min(start + chunk_bytes, len(data))
                while end < len(data) and data[end] & 0xC0 == 0x80:
                    end -= 1
                part = data[start:end]
                chunks.append({"start_byte": start, "end_byte": end, "bytes": len(part), "sha256": hashlib.sha256(part).hexdigest()})
                start = end
            item.update(status="planned", sha256=hashlib.sha256(data).hexdigest(), chunks=chunks)
            total += len(data)
        files.append(item)
    return {
        "commit": commit,
        "api_calls": 0,
        "files": files,
        "planned_bytes": total,
        "limitation": "Offline candidate plan only. No model analysis or privacy certification. Exclusions and unavailable blobs are not covered.",
    }
