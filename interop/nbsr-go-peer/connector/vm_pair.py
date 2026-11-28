"""Opt-in positive two-VM fixture; local preparation/checks are the default.
Adapted from retained run-pair.py. Never stores private worker output.
"""

import hashlib
import json
import argparse
import re
import uuid
from pathlib import Path
import queue
import subprocess
import threading
import time

from vm_pair_overlay import BASE, GO, RUST, digest, overlay, pinned_sources

TAG = "nbsr-connector-38f485cf-" + uuid.uuid4().hex[:12]
ROOT = "/tmp/" + TAG
HERE = None
WORK_END = TOTAL_END = 0.0
CLEANING = False
EVENTS = []
HOSTS = {"client": "10.77.0.2", "server": "10.77.0.1"}
FILES = {"client": ["go-connector"], "server": ["rust-gateway", "request.cbor"]}
OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "UpdateHostKeys=no",
    "-o",
    "ConnectTimeout=5",
    "-o",
    "ConnectionAttempts=1",
    "-o",
    "ServerAliveInterval=5",
    "-o",
    "ServerAliveCountMax=1",
]
attempted = set()
started = set()
removed = set()
created = set()
processes = []


def host(role):
    return "nbsr-" + role


def ssh(role, command):
    return ["ssh", "-T", *OPTS, host(role), command]


def remaining(seconds):
    left = (TOTAL_END if CLEANING else WORK_END) - time.monotonic()
    if left <= 0:
        raise TimeoutError("shared trial deadline")
    return min(seconds, left)


def emit(event):
    EVENTS.append(event)
    print(event, flush=True)


def run(args, seconds=35):
    return subprocess.run(
        args, cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining(seconds)
    )


def checked(result, msg):
    if result.returncode:
        raise RuntimeError(msg + f" (exit {result.returncode})")
    return result.stdout


def stage(role, expected_hashes):
    files = FILES[role]
    for name in files:
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected_hashes[name]:
            raise ValueError("artifact changed after validation")
    attempted.add(role)
    ip = HOSTS[role]
    check = f"""test "$(hostname -s)" = {role} && ip -o -4 addr show dev eth1 | grep -Fq " {ip}/24 " """
    checked(run(ssh(role, check + f" && umask 077 && mkdir -m 700 -- {ROOT}")), role + " identity or exclusive staging check failed")
    created.add(role)
    checked(run(["scp", *OPTS, *["./" + f for f in files], host(role) + ":" + ROOT + "/"], 65), role + " transfer failed")
    # Pin the remote bytes to the validated manifest, even if local files change during SCP.
    hashes = [expected_hashes[f] + "  " + f for f in files]
    script = f"cd {ROOT} && printf '%s\\n' " + " ".join("'" + h + "'" for h in hashes) + " | sha256sum -c -"
    script += " && chmod 700 " + files[0]
    if role == "server":
        script += " && mkdir -p crates/nbsr-transport vectors/connector-registration-development-v1 && mv request.cbor vectors/connector-registration-development-v1/request.cbor"
    checked(run(ssh(role, script)), role + " checksum/staging failed")
    emit(role + " staged_sha256_verified")


def start(role, command):
    started.add(role)
    remaining(1)
    # A remote completion file is written only after timeout has reaped its worker.
    # Missing receipt leaves staging retained and cleanup explicitly unconfirmed.
    command = (
        f"cd {ROOT} && : > worker.started && " + command + "; code=$?; printf '%s\\n' \"$code\" > " + ROOT + '/worker.exit; exit "$code"'
    )
    p = subprocess.Popen(ssh(role, command), cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    processes.append(p)
    q = queue.Queue(maxsize=100)
    overflow = threading.Event()
    q.overflow = overflow

    def reader():
        try:
            while True:
                line = p.stdout.readline(150000)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    overflow.set()
                    return
                q.put_nowait(line.rstrip(b"\r\n"))
        except (queue.Full, OSError):
            overflow.set()
        finally:
            try:
                q.put_nowait(None)
            except queue.Full:
                overflow.set()

    threading.Thread(target=reader, daemon=True).start()
    return p, q


def each(q, seconds):
    end = time.monotonic() + remaining(seconds)
    while True:
        if q.overflow.is_set():
            raise RuntimeError("worker output limit exceeded")
        left = min(end - time.monotonic(), remaining(seconds))
        if left <= 0:
            raise TimeoutError("worker observation deadline")
        line = q.get(timeout=left)
        if q.overflow.is_set():
            raise RuntimeError("worker output incomplete")
        if line is None:
            return
        yield line


def write(p, data):
    p.stdin.write(data)
    p.stdin.flush()


def test():
    worker_seconds = max(1, int(remaining(45)) - 4)
    cp, cq = start(
        "client",
        f"cd {ROOT} && printf 'CLIENT_READY\\n' && export NBSR_CONNECTOR_LOOPBACK=1 && timeout --kill-after=3s {worker_seconds}s ./go-connector '-test.run=^TestDevelopmentLoopbackProcess$' -test.count=1 -test.timeout=15s",
    )
    if next(each(cq, 18), None) != b"CLIENT_READY":
        raise RuntimeError("client not ready")
    worker_seconds = max(1, int(remaining(40)) - 4)
    sp, sq = start(
        "server",
        f"cd {ROOT} && timeout --kill-after=3s {worker_seconds}s ./rust-gateway --exact isolated_go_rust_control_registration --ignored --nocapture",
    )
    lines = each(sq, 35)
    for line in lines:
        if line.startswith(b"SPHERE_HANDOFF "):
            fixture = line[len(b"SPHERE_HANDOFF ") :]
            d = json.loads(fixture)
            port = validate_handoff(d)
            write(cp, fixture + b"\n")
            cp.stdin.close()
            del d, fixture, line
            break
    else:
        raise RuntimeError("Gateway did not emit an approved synthetic test fixture")
    cl = list(each(cq, 22))
    if cp.wait(timeout=remaining(3)) or not any(valid_client_cleanup(x) for x in cl):
        raise RuntimeError("Connector did not finish successfully with its private UDP socket released")
    emit("SPHERE_CONNECTOR_CLEANUP client_socket_released=true process_exit=0")
    write(sp, b"CONNECTOR_EXIT_0_SOCKET_RELEASED\n")
    sp.stdin.close()
    seen = set()
    for line in lines:
        event = validate_server_line(line, port)
        if event:
            if event in seen:
                raise RuntimeError("duplicate worker receipt")
            seen.add(event)
            emit(event)
    if sp.wait(timeout=remaining(3)) or seen != {"peer_verified", "gateway_cleanup_verified", "synthetic_positive_pass", "one_test_passed"}:
        raise RuntimeError("Gateway result incomplete")


def validate_handoff(d):
    if d.get("Case") != "positive":
        raise ValueError("fixture case mismatch")
    endpoint = d.get("Endpoint", "")
    match = re.fullmatch(r"10\.77\.0\.1:([0-9]+)", endpoint)
    if not match or not 1024 <= int(match[1]) <= 65535:
        raise ValueError("fixture endpoint mismatch")
    return match[1]


def valid_client_cleanup(line):
    match = re.fullmatch(rb"loopback_socket_released=10\.77\.0\.2:([0-9]+)", line)
    return bool(match and 1 <= int(match[1]) <= 65535)


def validate_server_line(line, port):
    if line.startswith(b"SPHERE_PEER "):
        match = re.fullmatch(rb"SPHERE_PEER 10\.77\.0\.2:([0-9]+) -> 10\.77\.0\.1:" + port.encode(), line)
        if not match or not 1 <= int(match[1]) <= 65535:
            raise ValueError("peer receipt mismatch")
        return "peer_verified"
    expected = {
        b"SPHERE_GATEWAY_CLEANUP ": (b"SPHERE_GATEWAY_CLEANUP gateway_socket_released=true owner_count=0", "gateway_cleanup_verified"),
        b"SPHERE_CONNECTOR_PASS ": (b"SPHERE_CONNECTOR_PASS synthetic_authority=true", "synthetic_positive_pass"),
    }
    for prefix, (exact, event) in expected.items():
        if line.startswith(prefix):
            if line != exact:
                raise ValueError("worker receipt mismatch")
            return event
    if line.startswith(b"test result:"):
        if not re.fullmatch(
            rb"test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; [0-9]+ filtered out; finished in [0-9.]+s", line
        ):
            raise ValueError("test result mismatch")
        return "one_test_passed"
    return None


def cleanup(role):
    require_exit = "test -f worker.exit && " if role in started else ""
    cmd = f'cd {ROOT} && {require_exit}if test -e worker.started; then test -f worker.exit || exit 5; fi && rm -f -- worker.started worker.exit go-connector rust-gateway request.cbor vectors/connector-registration-development-v1/request.cbor && for d in crates/nbsr-transport crates vectors/connector-registration-development-v1 vectors; do if test -d "$d"; then rmdir -- "$d" || exit 4; fi; done && cd /tmp && rmdir -- {ROOT} && test ! -e {ROOT}'
    checked(run(ssh(role, cmd)), role + " cleanup not verified")
    removed.add(role)
    emit(role + " staging_removed")


def execute(manifest):
    global WORK_END, TOTAL_END, CLEANING
    EVENTS.clear()
    attempted.clear()
    started.clear()
    removed.clear()
    created.clear()
    processes.clear()
    CLEANING = False
    start_time = time.monotonic()
    WORK_END, TOTAL_END = start_time + 95, start_time + 120
    errors = []
    try:
        for role in HOSTS:
            stage(role, manifest["artifacts"])
        test()
    except (Exception, KeyboardInterrupt) as exc:
        errors.append("trial:" + type(exc).__name__)
    finally:
        CLEANING = True
        for p in processes:
            try:
                if p.stdin is not None and not p.stdin.closed:
                    p.stdin.close()
            except Exception as exc:
                errors.append("local_stdin_close:" + type(exc).__name__)
            try:
                if p.poll() is None:
                    try:
                        p.wait(timeout=remaining(2))
                    except (subprocess.TimeoutExpired, TimeoutError):
                        # Kill must still be attempted when the shared wait budget is exhausted.
                        p.kill()
                        p.wait(timeout=remaining(2))
            except Exception as exc:
                errors.append("local_reap:" + type(exc).__name__)
        for role in sorted(created):
            try:
                cleanup(role)
            except Exception as exc:
                errors.append(role + "_cleanup:" + type(exc).__name__)
    return {
        "base_sha": BASE,
        "synthetic_authority": True,
        "ready": "NOT_ESTABLISHED",
        "pass": not errors and attempted == removed,
        "errors": errors,
        "events": EVENTS,
        "elapsed_seconds": time.monotonic() - start_time,
        "staging_root": ROOT,
        "local_ssh_exit_codes": [p.poll() for p in processes],
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cleanup_confirmed": attempted == removed and not any("cleanup:" in e or "reap:" in e for e in errors),
    }


def source_receipt(repo):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip()
    if head != BASE:
        raise ValueError("source checkout must be the pinned base")
    originals = pinned_sources(repo)
    patched = overlay(*originals)
    return originals, patched


def record_artifacts(repo, artifacts):
    originals, patched = source_receipt(repo)
    changed = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=repo).decode().splitlines()
    if set(changed) != {GO, RUST}:
        raise ValueError("build checkout must contain only the two overlay edits")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "interop/nbsr-go-peer", "crates/nbsr-transport"], cwd=repo
    )
    if untracked.strip():
        raise ValueError("build source contains untracked files")
    for path, expected in zip((GO, RUST), patched):
        if (repo / path).read_text(encoding="utf-8") != expected:
            raise ValueError("build checkout overlay mismatch")
    record = {
        "base_sha": BASE,
        "synthetic_authority": True,
        "provenance": "operator-declared build; hashes are not build attestation",
        "source_sha256": dict(zip((GO, RUST), map(digest, originals))),
        "overlay_sha256": dict(zip((GO, RUST), map(digest, patched))),
        "artifacts": {
            name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest() for name in ("go-connector", "rust-gateway", "request.cbor")
        },
    }
    with (artifacts / "manifest.json").open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)


def check_artifacts(repo, artifacts):
    originals = pinned_sources(repo)
    patched = overlay(*originals)
    record = json.loads((artifacts / "manifest.json").read_text())
    if (
        record.get("base_sha") != BASE
        or record.get("synthetic_authority") is not True
        or record.get("source_sha256") != dict(zip((GO, RUST), map(digest, originals)))
        or record.get("overlay_sha256") != dict(zip((GO, RUST), map(digest, patched)))
    ):
        raise ValueError("artifact provenance mismatch")
    for name in ("go-connector", "rust-gateway", "request.cbor"):
        if hashlib.sha256((artifacts / name).read_bytes()).hexdigest() != record["artifacts"].get(name):
            raise ValueError("artifact hash mismatch")
    request = subprocess.check_output(
        [
            "git",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            "show",
            BASE + ":vectors/connector-registration-development-v1/request.cbor",
        ],
        cwd=repo,
    )
    if (artifacts / "request.cbor").read_bytes() != request:
        raise ValueError("request fixture mismatch")
    # Do not echo arbitrary manifest fields into the public receipt.
    return {
        "base_sha": BASE,
        "synthetic_authority": True,
        "source_sha256": record["source_sha256"],
        "overlay_sha256": record["overlay_sha256"],
        "artifacts": {name: record["artifacts"][name] for name in ("go-connector", "rust-gateway", "request.cbor")},
    }


def main():
    global HERE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", type=Path, help="write overlay copies to a NEW local directory")
    modes.add_argument("--record-artifacts", action="store_true")
    modes.add_argument("--run-vm", action="store_true", help="explicitly contact both configured VMs")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.prepare:
        originals, patched = source_receipt(args.repo)
        args.prepare.mkdir(parents=False, exist_ok=False)
        for path, text in zip((GO, RUST), patched):
            dest = args.prepare / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8", newline="\n")
        print("OVERLAY_PREPARED_LOCAL_ONLY")
        return
    if args.artifacts is None:
        parser.error("--artifacts is required for checks, recording or execution")
    HERE = args.artifacts.resolve()
    if args.record_artifacts:
        record_artifacts(args.repo, HERE)
        print("ARTIFACT_HASHES_RECORDED_LOCAL_ONLY")
        return
    manifest = check_artifacts(args.repo, HERE)
    if not args.run_vm:
        print("ARTIFACTS_VALID_LOCAL_ONLY; VM execution not performed")
        return
    if args.evidence is None:
        parser.error("--run-vm requires a new --evidence directory")
    args.evidence.mkdir(parents=False, exist_ok=False)
    result = execute(manifest)
    result["manifest"] = manifest
    (args.evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (args.evidence / "redacted.log").write_text("\n".join(EVENTS) + "\n", encoding="utf-8")
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
