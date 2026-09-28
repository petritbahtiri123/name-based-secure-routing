from pathlib import Path
import hashlib
import json

base = Path("C:/NBSR-build")


def verify(root):
    for line in (root / "checksums.sha256").read_text().splitlines():
        sha, rel = line.split("  ", 1)
        p = (root / rel).resolve()
        assert p.is_relative_to(root.resolve())
        with p.open("rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == sha, p


out = {}
for label, name in [("before", "go-b3-97e0ca06"), ("after", "go-scope-20260926")]:
    root = base / name
    verify(root)
    attempts = json.loads((root / "attempts.json").read_text())
    rows = []
    for p in sorted((root / "raw/go-rust").glob("cycles-50-r*/cell.json")):
        cell = json.loads(p.read_text())
        runtime = [json.loads(line) for line in (p.parent / "go-runtime-0.ndjson").read_text().splitlines()]
        samples = cell["client_results"][0]["samples"]
        assert len(samples) == 400 and all(s["success"] for s in samples)
        if label == "after":
            c = cell["client_results"][0]["lifecycle_cleanup"]
            assert c == [dict(ordinal=i, workers_started=8, workers_live=0, peer_close_calls=1) for i in range(50)]
        role_data = {}
        for role in ["source", "destination"]:
            values = [r["private_bytes"] for r in cell["samples"] if r["role"] == role and r["phase"] == "cooldown"]
            role_data[role] = dict(first=values[0], last=values[-1], minimum=min(values), maximum=max(values))
        rows.append(
            dict(
                name=cell["name"],
                process_private_bytes=role_data,
                runtime_first=runtime[0],
                runtime_last=runtime[-1],
                runtime_min_goroutines=min(r["goroutines"] for r in runtime),
                runtime_max_goroutines=max(r["goroutines"] for r in runtime),
            )
        )
    out[label] = dict(
        root=str(root),
        attempts=len(attempts),
        passed=sum(r["status"] == "PASS_SCOPED" for r in attempts),
        failed=sum(r["status"] != "PASS_SCOPED" for r in attempts),
        cycles=rows,
    )
out["scope"] = (
    "Stage-bound Windows diagnostics, differing source commits and run times; no causal performance or full QUIC ownership claim. All successful source worker reports after change are joined/zero; memory cause not inferred from private bytes alone."
)
print(json.dumps(out, indent=2))
