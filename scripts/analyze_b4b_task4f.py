"""Reproduce Task4d/4f comparisons without modifying raw measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_b4b_task4c import handshake_percentiles
from scripts.run_b4b_mixed_connections import write_json


def compare(before, after, output):
    if output.exists():
        raise FileExistsError(output)
    result = {}
    for label, root in (("before", before), ("after", after)):
        cells = json.loads((root/"analysis.json").read_text())["cells"]
        result[label] = []
        for clients in (128,256,512):
            cell = dict(next(c for c in cells if c["clients"] == clients))
            records = [json.loads(p.read_text()) for p in sorted((root/"raw").glob(f"clients-{clients}-connections-1-r*.json"))]
            handshake = [handshake_percentiles(p.read_text()) for p in sorted((root/"raw").glob(f"clients-{clients}-connections-1-r*/admission-source.stdout"))]
            cell["handshake_p95_ms"] = statistics.median(h["p95_ms"] for h in handshake)
            cell["handshake_p99_ms"] = statistics.median(h["p99_ms"] for h in handshake)
            cell["admitted_per_repeat"] = [r["successful_admissions"] for r in records]
            cell["cleanup_zero_per_repeat"] = [r["cleanup"]["all_zero"] for r in records]
            cell["forced_cleanup_overruns"] = sum("cleanup exceeded" in (r.get("failure_detail") or "") for r in records)
            if label == "after":
                for r in records:
                    path = root/"raw"/f"clients-{clients}-connections-1-r{r['repeat']}"/"admission-destination.stderr.raw"
                    raw = path.read_bytes()
                    assert len(raw) == r["stderr_capture"]["bytes"]
                    assert hashlib.sha256(raw).hexdigest() == r["stderr_capture"]["sha256"]
                    assert r["stderr_capture"]["valid"] and r["stderr_capture"]["flushed"]
            result[label].append(cell)
    result["scope"] = "Windows loopback; before/after not simultaneous; no handshake cause attribution"
    write_json(output,result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compare(args.before,args.after,args.output)
