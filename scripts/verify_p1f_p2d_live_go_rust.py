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

from tests.federation.test_independent_wire_peer import _write_test_authority  # noqa: E402


AUTHORITY = ROOT / "docs/protocol/registries/core-v0.2-p1p2-overlay.json"
AUTHORITY_SHA256 = "7a33b7d6dd87031018563da0e8d2b1857515bc3ae2427094a6967d9e6329d3e4"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_ready(path: Path, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and process.poll() is None:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.02)
    raise RuntimeError(f"Rust server did not become ready; exit={process.poll()}")


def run_case(root: Path, rust: Path, go: Path, name: str, mutation: str = "", operations: int = 1) -> dict[str, object]:
    case = root / name
    case.mkdir(parents=True, exist_ok=False)
    authority = case / "authority"
    _write_test_authority(authority)
    ready, result, ack = case / "ready.json", case / "server-result.json", case / "complete.ack"
    server = subprocess.Popen(
        [str(rust), "--ready", str(ready), "--result", str(result), "--authority-dir", str(authority), "--completion-ack", str(ack)],
        cwd=ROOT,
        env={**os.environ, "NBSR_P2D_MODE": "after", "NBSR_P2D_OPERATIONS": str(operations), "NBSR_P2D_CONCURRENCY": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    readiness = wait_ready(ready, server)
    config = case / "peer-config.json"
    config.write_text(
        json.dumps(
            {
                "readiness_path": str(ready),
                "f75_package": str(ROOT / "vectors/wp8-f75-route-open"),
                "local_attestation_package": str(ROOT / "vectors/wp8-local-admission"),
                "safe_payload": "Z" * 1024,
                "benchmark_samples": operations,
                "stream_credit_profile": "nbsr-stream-credit-1",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    peer = subprocess.run(
        [str(go), "--config", str(config)],
        cwd=ROOT / "interop/nbsr-go-peer",
        env={**os.environ, "NBSR_INTEROP_TEST_MUTATION": mutation},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    ack.touch()
    try:
        server_stdout, server_stderr = server.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        server.terminate()
        server_stdout, server_stderr = server.communicate(timeout=5)
    observation = {
        "case": name,
        "mutation": mutation or None,
        "endpoint": readiness["endpoint"],
        "server_pid": server.pid,
        "peer_exit": peer.returncode,
        "server_exit": server.returncode,
        "peer_stdout": peer.stdout.strip(),
        "peer_stderr": peer.stderr.strip(),
        "server_stdout": server_stdout.strip(),
        "server_stderr": server_stderr.strip(),
        "result": json.loads(result.read_text(encoding="utf-8")) if result.exists() else None,
    }
    if not mutation:
        if peer.returncode != 0 or server.returncode != 0 or observation["result"] is None:
            raise RuntimeError(f"positive live case failed: {observation}")
    else:
        rejected = observation["result"]
        if (
            peer.returncode == 0
            or server.returncode != 0
            or not isinstance(rejected, dict)
            or rejected.get("status") != "REJECTED"
            or rejected.get("payload_exposed") is not False
            or rejected.get("reason") != "APPLICATION_STREAM_REJECTED"
        ):
            raise RuntimeError(f"negative live case did not fail closed cleanly: {observation}")
    return observation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-root", type=Path, required=True)
    args = parser.parse_args()
    build = args.build_root.resolve()
    if "OneDrive" in str(build):
        raise SystemExit("build root must be outside OneDrive")
    rust = build / "cargo-target/release/wp8_interop_server.exe"
    go = build / "go/nbsr-go-peer.exe"
    if sha256(AUTHORITY) != AUTHORITY_SHA256:
        raise SystemExit("unapproved P1F/P2D authority digest")
    run_root = build / "live-run"
    if run_root.exists():
        raise SystemExit(f"refusing to overwrite prior live evidence: {run_root}")
    run_root.mkdir(parents=True)
    cases = [run_case(run_root, rust, go, "approved"), run_case(run_root, rust, go, "multiple-refill", operations=80)]
    for name, mutation in (
        ("malformed-preface", "malformed_credit_preface"),
        ("profile-mismatch", "credit_profile_mismatch"),
        ("legacy-downgrade", "credit_legacy_downgrade"),
    ):
        cases.append(run_case(run_root, rust, go, name, mutation))
    evidence = {
        "schema": "nbsr-p1f-p2d-live-go-rust-closure-1",
        "authority_sha256": AUTHORITY_SHA256,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
        "rust_binary": {"path": str(rust), "sha256": sha256(rust)},
        "go_binary": {"path": str(go), "sha256": sha256(go)},
        "topology": "Go peer process -> QUIC v1/TLS 1.3 nbsr-quic-1 -> Rust server process",
        "cases": cases,
    }
    output = run_root / "live-result.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "cases": len(cases), "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
