from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.federation.test_independent_wire_peer import _write_test_authority



def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_json(path: Path, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and process.poll() is None:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.02)
    raise RuntimeError(f"server did not become ready: {process.poll()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-root", type=Path, required=True)
    args = parser.parse_args()
    build = args.build_root.resolve()
    if "OneDrive" in str(build):
        raise SystemExit("build root must be outside OneDrive")
    rust = build / "cargo-target/release/wp8_interop_server.exe"
    go = build / "go/nbsr-go-peer.exe"
    run = build / "rotation-run"
    if run.exists():
        raise SystemExit(f"refusing to overwrite {run}")
    run.mkdir(parents=True)

    processes: list[subprocess.Popen[str]] = []
    readiness: list[dict[str, object]] = []
    paths: list[Path] = []
    results: list[Path] = []
    acks: list[Path] = []
    for index, operations in enumerate((1, 2), start=1):
        case = run / f"generation-{index}"
        authority = case / "authority"
        case.mkdir()
        _write_test_authority(authority)
        ready, result, ack = case / "ready.json", case / "server-result.json", case / "complete.ack"
        process = subprocess.Popen(
            [str(rust), "--ready", str(ready), "--result", str(result), "--authority-dir", str(authority), "--completion-ack", str(ack)],
            cwd=ROOT,
            env={**os.environ, "NBSR_P2D_MODE": "after", "NBSR_P2D_OPERATIONS": str(operations), "NBSR_P2D_CONCURRENCY": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(process)
        paths.append(ready)
        results.append(result)
        acks.append(ack)
        readiness.append(wait_json(ready, process))

    config = run / "peer-config.json"
    config.write_text(json.dumps({
        "readiness_path": str(paths[0]),
        "rotation_readiness_paths": [str(path) for path in paths],
        "f75_package": str(ROOT / "vectors/wp8-f75-route-open"),
        "local_attestation_package": str(ROOT / "vectors/wp8-local-admission"),
        "safe_payload": "Z" * 1024,
        "benchmark_samples": 3,
        "stream_credit_profile": "nbsr-stream-credit-1",
    }, sort_keys=True), encoding="utf-8")
    peer = subprocess.run([str(go), "--config", str(config)], cwd=ROOT / "interop/nbsr-go-peer", capture_output=True, text=True, timeout=45, check=False)
    for ack in acks:
        ack.touch()
    server_observations = []
    for process, result in zip(processes, results, strict=True):
        stdout, stderr = process.communicate(timeout=20)
        server_observations.append({"pid": process.pid, "exit": process.returncode, "stdout": stdout.strip(), "stderr": stderr.strip(), "result": json.loads(result.read_text(encoding="utf-8")) if result.exists() else None})
    if peer.returncode != 0:
        raise RuntimeError(f"rotation peer failed: {peer.stderr}\n{peer.stdout}")
    peer_result = json.loads(peer.stdout)
    rotation = peer_result.get("rotation", {})
    required_true = ("a_descendant_pinned", "a_state_unusable", "final_b_current", "final_b_usable", "third_generation_rejected")
    if peer_result.get("status") != "PASS" or not all(rotation.get(key) is True for key in required_true):
        raise RuntimeError(f"incomplete rotation evidence: {peer_result}")
    if rotation.get("a_transport") == rotation.get("b_transport") or rotation.get("maximum_generations") != 2 or rotation.get("application_data_replayed") is not False:
        raise RuntimeError(f"invalid transport/replay evidence: {rotation}")
    expected_operations = (1, 2)
    for observed, expected in zip(server_observations, expected_operations, strict=True):
        result = observed["result"]
        if observed["exit"] != 0 or not isinstance(result, dict) or result.get("completed_operations") != expected or result.get("errors") != 0:
            raise RuntimeError(f"server evidence mismatch: {observed}")
    evidence = {
        "schema": "nbsr-tranche5-real-rotation-1",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
        "rust_binary": {"path": str(rust), "sha256": digest(rust)},
        "go_binary": {"path": str(go), "sha256": digest(go)},
        "readiness": readiness,
        "peer": peer_result,
        "servers": server_observations,
    }
    output = run / "rotation-evidence.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(output), "a_transport": rotation["a_transport"], "b_transport": rotation["b_transport"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
