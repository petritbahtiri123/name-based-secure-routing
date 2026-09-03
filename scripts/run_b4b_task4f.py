"""Task 4f only: unchanged workloads at 128/256/512 with stderr draining."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b4b_v2 as v2
from scripts.run_b4b_mixed_connections import SOURCE_FILES, checksums


def run(output):
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    historical = v2.ROOT / "evidence/performance/v2/b4b-task4d-361c315038bb/analysis.json"
    old = json.loads(historical.read_text())["cells"][0]
    baseline = dict(established_goodput_bytes_per_second=old["median_established_gbps"]*1e9/8,
                    established_p99_latency_ns=old["median_established_p99_latency_ns"])
    binaries = v2.build(Path(os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\b4b-task4e-profile")))
    environment = v2.host_environment()
    environment.update(timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       build="release", duration_seconds=20, warmup_seconds=2,
                       planned_clients=[128,256,512], command=[sys.executable,*sys.argv],
                       baseline=str(historical), baseline_sha256=hashlib.sha256(historical.read_bytes()).hexdigest(),
                       binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binaries.items()},
                       source_sha256={p:hashlib.sha256((v2.ROOT/p).read_bytes()).hexdigest() for p in SOURCE_FILES})
    v2.write_json(output/"environment.json", environment)
    records, cells = [], []
    for clients in (128,256,512):
        selected=[]
        repeat=1
        count=3
        while repeat <= count:
            print(f"clients={clients} repeat={repeat}/{count}", flush=True)
            try:
                record=v2.run_measured_cell(clients,1,repeat,binaries,raw,duration=20,warmup=2,
                    planned_clients=[128,256,512],counter_path=raw/f"clients-{clients}-r{repeat}-host.csv")
            except Exception as error:
                record=dict(clients=clients,repeat=repeat,valid=False,failure=repr(error))
            v2.write_json(raw/f"clients-{clients}-connections-1-r{repeat}.json",record)
            records.append(record)
            selected.append(record)
            if not record["valid"]:
                break
            if repeat==3:
                count=v2.required_repeats(selected)
            repeat+=1
        if not all(r["valid"] for r in selected):
            break
        cell=v2.summarize_cell(selected,baseline)
        cell["median_destination_cleanup_wait_seconds"]=statistics.median(r["destination_cleanup_wait_seconds"] for r in selected)
        cell["stderr_bytes"]=[r["stderr_capture"]["bytes"] for r in selected]
        cells.append(cell)
    v2.write_json(output/"analysis.json",dict(cells=cells,invalid_runs=[r for r in records if not r["valid"]],
        baseline_comparison="Historical Task4d baseline, not a new zero-client control",
        stderr_capture_pass=all(r.get("stderr_capture",{}).get("valid",False) for r in records)))
    checksums(output)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    run(parser.parse_args().output)
