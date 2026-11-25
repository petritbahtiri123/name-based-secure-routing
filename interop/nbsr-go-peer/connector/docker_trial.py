"""Opt-in synthetic Connector stop/start trial. Requires prebuilt Linux workers.

No downloads/builds, published ports, Docker socket mounts or real credentials.
Private fixture stdout is intercepted in memory; Docker logging is disabled.
"""
import argparse
import hashlib
import ipaddress
import json
import pathlib
import queue
import shutil
import subprocess
import threading
import time
import traceback
import uuid


def choose_subnet(occupied):
    for candidate in ipaddress.ip_network("10.254.0.0/16").subnets(new_prefix=29):
        if not any(candidate.overlaps(n) for n in occupied if n.version == 4):
            return candidate
    raise RuntimeError("no non-overlapping trial subnet")


def existing_subnets(networks):
    # Docker's built-in host/none networks legitimately have null IPAM Config.
    return [ipaddress.ip_network(c["Subnet"]) for n in networks
            for c in (n["IPAM"]["Config"] or []) if c.get("Subnet")]


def validate_stop(state, attach_exit, mode, graceful_marker):
    if mode not in ("term", "kill"):
        raise RuntimeError("unknown stop mode")
    expected_exit = 137 if mode == "kill" else 0
    if (state["Running"] or state["Pid"] != 0 or state["OOMKilled"]
            or state["ExitCode"] != expected_exit or attach_exit != expected_exit
            or graceful_marker != (mode == "term")):
        raise RuntimeError("stop evidence mismatch")


def validate_same_process(before, after):
    state = after["State"]
    if (before["Id"] != after["Id"] or not state["Running"] or state["OOMKilled"]
            or state["Pid"] <= 0 or state["Pid"] != before["State"]["Pid"]
            or state["StartedAt"] != before["State"]["StartedAt"]):
        raise RuntimeError("network change altered Connector process identity")


def session_count(mode, cycles, cleanup_failure=False):
    if cleanup_failure and (mode != "auto-network" or cycles != 1):
        raise ValueError("cleanup failure requires one auto-network cycle")
    if type(cycles) is not int or not 1 <= cycles <= 5:
        raise ValueError("cycles must be an integer from 1 through 5")
    if mode != "auto-network" and cycles != 1:
        raise ValueError("multiple cycles require auto-network mode")
    return cycles + 1 if mode == "auto-network" else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--artifacts", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    parser.add_argument("--first-stop", choices=("term", "kill", "network", "auto-network"), default="term")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--cleanup-failure", action="store_true")
    args = parser.parse_args()
    automatic = args.first_stop == "auto-network"
    sessions = session_count(args.first_stop, args.cycles, args.cleanup_failure)
    artifacts = args.artifacts.resolve(strict=True)
    repo = pathlib.Path(__file__).resolve().parents[3]
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    for binary in ("gateway-test", "connector-test"):
        if not (artifacts / binary).is_file():
            raise RuntimeError("prebuilt worker missing")
    start_free = shutil.disk_usage(evidence).free
    if start_free < 8 * 1024**3:
        raise RuntimeError("8 GiB pre-trial disk gate")
    started = time.monotonic()
    prefix = "nbsr-connector-trial-" + uuid.uuid4().hex[:10]
    label = "nbsr.connector.trial=" + prefix
    names = [prefix + "-gateway", prefix + "-connector"]
    network = prefix + "-net"
    owned = []
    created_network = False
    processes = []
    readers = []
    events = queue.Queue()
    pending = []
    report = {"project": prefix, "synthetic_authority": True, "ready": "NOT_ESTABLISHED",
              "commands": [], "stops": [], "status": "FAIL", "first_stop": args.first_stop,
              "cleanup_failure_requested": args.cleanup_failure, "requested_cycles": args.cycles, "expected_sessions": sessions}
    report["commit"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    source_paths = [*repo.glob("interop/nbsr-go-peer/connector/*.go"),
                    *repo.glob("interop/nbsr-go-peer/connector/*.py"),
                    repo / "crates/nbsr-transport/tests/connector_loopback.rs",
                    repo / "crates/nbsr-transport/tests/support/connector_loopback.rs",
                    repo / "crates/nbsr-transport/tests/support/connector_docker.rs",
                    *[repo / f"crates/nbsr-transport/src/connector_{n}.rs"
                      for n in ("control", "registration", "cleanup")]]
    report["source_sha256"] = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in source_paths}
    report["binary_sha256"] = {n: hashlib.sha256((artifacts/n).read_bytes()).hexdigest()
                               for n in ("gateway-test", "connector-test")}
    for source in source_paths:
        target = evidence / "source" / source.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    log = (evidence / "redacted.log").open("w", encoding="utf-8", buffering=1)

    def check():
        free = shutil.disk_usage(evidence).free
        if time.monotonic() - started > 95 or free < 6*1024**3 or start_free-free > 2*1024**3:
            raise RuntimeError("trial time/disk guard")

    def docker(*arguments):
        check()
        report["commands"].append(["docker", *arguments])
        try:
            return subprocess.check_output(["docker", *arguments], stderr=subprocess.PIPE,
                                           timeout=min(8, max(.1, 95-(time.monotonic()-started))), text=True).strip()
        except subprocess.CalledProcessError as error:
            # Control commands never carry private fixture data.
            log.write("docker control error: " + error.stderr)
            raise

    def reader(process, role):
        for line in process.stdout:
            marker = "NBSR_PRIVATE_FIXTURE "
            if marker in line:
                # Never persist this line, including on parse/error paths.
                events.put((role, "private", line.split(marker, 1)[1].strip()))
            else:
                log.write(role + ": " + line)
                events.put((role, "public", line.strip()))

    def attach(name, role):
        report["commands"].append(["docker", "start", "-ai", name])
        process = subprocess.Popen(["docker", "start", "-ai", name], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", bufsize=1)
        processes.append(process)
        thread = threading.Thread(target=reader, args=(process, role), daemon=True)
        thread.start()
        readers.append(thread)
        return process

    def event(role, marker=None, private=False):
        until = time.monotonic() + 18
        while time.monotonic() < until:
            check()
            for index, (source, kind, data) in enumerate(pending):
                if source == role and ((private and kind == "private") or
                                       (not private and kind == "public" and marker in data)):
                    pending.pop(index)
                    return data
            try:
                pending.append(events.get(timeout=.1))
            except queue.Empty:
                pass
        raise RuntimeError("event deadline: " + role + ":" + (marker or "private fixture"))

    try:
        report["before"] = {kind: docker(*cmd).splitlines() for kind, cmd in {
            "containers": ("ps", "-aq", "--no-trunc"),
            "networks": ("network", "ls", "-q", "--no-trunc"),
            "volumes": ("volume", "ls", "-q")}.items()}
        existing = json.loads(docker("network", "inspect", *report["before"]["networks"]))
        occupied = existing_subnets(existing)
        selected_subnet = choose_subnet(occupied)
        docker("network", "create", "--internal", "--subnet", str(selected_subnet), "--label", label, network)
        created_network = True
        net = json.loads(docker("network", "inspect", network))[0]
        assert net["Internal"]
        subnet = ipaddress.ip_network(net["IPAM"]["Config"][0]["Subnet"])
        assert subnet.version == 4 and subnet.is_private
        gateway_ip, connector_ip = str(subnet.network_address+2), str(subnet.network_address+3)
        address = gateway_ip + ":4444"
        base = ["create", "--pull=never", "-i", "--log-driver", "none", "--network", network,
                "--label", label, "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64",
                "--memory", "256m", "--cpus", "2",
                "--mount", f"type=bind,source={artifacts},target=/harness,readonly"]
        vectors = repo / "vectors/connector-registration-development-v1"
        docker(*base, "--name", names[0], "--ip", gateway_ip,
               "--mount", f"type=bind,source={repo / 'crates/nbsr-transport'},target=/src/crates/nbsr-transport,readonly",
               "--mount", f"type=bind,source={vectors},target=/src/vectors/connector-registration-development-v1,readonly",
               "--env", "NBSR_CONNECTOR_DOCKER_GATEWAY="+address,
               "--env", "NBSR_CONNECTOR_DOCKER_FIRST_STOP="+args.first_stop,
               "--env", "NBSR_CONNECTOR_DOCKER_FAIL_CLEANUP="+str(int(args.cleanup_failure)),
               "--env", "NBSR_CONNECTOR_DOCKER_CYCLES="+str(args.cycles),
               "--entrypoint", "/harness/gateway-test", args.image,
               "--exact", "isolated_docker_connector_restart", "--ignored", "--nocapture", "--test-threads=1")
        owned.append(names[0])
        docker(*base, "--name", names[1], "--ip", connector_ip,
               "--env", "NBSR_CONNECTOR_LOOPBACK=1",
               "--env", "NBSR_CONNECTOR_DOCKER_AUTO=" + ("1" if automatic else "0"),
               "--env", "NBSR_CONNECTOR_DOCKER_CYCLES="+str(args.cycles),
               "--env", "NBSR_CONNECTOR_DOCKER_ENDPOINT="+address,
               "--entrypoint", "/harness/connector-test", args.image,
               "-test.run=^" + ("TestDevelopmentDockerReconnectProcess" if automatic
                                else "TestDevelopmentLoopbackProcess") + "$",
               "-test.count=1", "-test.timeout=" + ("90s" if automatic and args.cycles > 1 else "45s"))
        owned.append(names[1])
        for name in names:
            config = json.loads(docker("inspect", name))[0]
            assert not config["HostConfig"]["PortBindings"]
            assert config["HostConfig"]["LogConfig"]["Type"] == "none"
        gateway = attach(names[0], "gateway")
        original_gateway_start = None
        connector_id = None
        original_connector = None
        connector = None
        for attempt in range(1, sessions + 1):
            fixture = event("gateway", private=True)
            # Validate privately; never include fixture bytes in errors or logs.
            try:
                valid_fixture = json.loads(fixture)["Endpoint"] == address
            except (ValueError, KeyError):
                valid_fixture = False
            if not valid_fixture:
                raise RuntimeError("invalid private fixture")
            if attempt == 1 or not automatic:
                connector = attach(names[1], "connector")
            connector.stdin.write(fixture + "\n")
            connector.stdin.flush()
            del fixture
            event("connector", "NBSR_CONNECTOR_ACCEPTED")
            event("gateway", f"NBSR_GATEWAY_ACCEPTED attempt={attempt}")
            gs = json.loads(docker("inspect", names[0]))[0]
            cs = json.loads(docker("inspect", names[1]))[0]
            assert gs["State"]["Running"] and cs["State"]["Running"]
            if attempt == 1:
                original_gateway_start = gs["State"]["StartedAt"]
                connector_id = cs["Id"]
                original_connector = cs
            assert gs["State"]["StartedAt"] == original_gateway_start
            assert cs["Id"] == connector_id
            if automatic:
                validate_same_process(original_connector, cs)
                if attempt > 1:
                    report["automatic_reconnect"] = {
                        "same_process": True, "connector_state": cs["State"],
                        "connector_id": connector_id, "generation": attempt,
                        "gateway_cleanup_confirmed_before_fixture": True}
                    report.setdefault("automatic_reconnections", []).append(report["automatic_reconnect"])
            mode = args.first_stop if attempt == 1 or (automatic and attempt < sessions) else "term"
            retained_observed = False
            if mode in ("network", "auto-network"):
                docker("network", "disconnect", network, names[1])
                detached = json.loads(docker("network", "inspect", network))[0]["Containers"]
                assert connector_id not in detached
                event("gateway", f"NBSR_OWNER_RETAINED attempt={attempt}")
                retained_observed = True
                disconnected = json.loads(docker("inspect", names[1]))[0]
                validate_same_process(cs, disconnected)
                docker("network", "connect", "--ip", connector_ip, network, names[1])
                restored = json.loads(docker("network", "inspect", network))[0]["Containers"]
                assert restored[connector_id]["IPv4Address"].split("/")[0] == connector_ip
                gateway.stdin.write(f"CHECK_RETAINED {attempt}\n")
                gateway.stdin.flush()
                event("gateway", f"NBSR_NETWORK_RESTORED_NO_RECONNECT attempt={attempt} window_ms=2000")
                reconnected_network = json.loads(docker("inspect", names[1]))[0]
                validate_same_process(cs, reconnected_network)
                report["network_disruption"] = {
                    "cycle": attempt,
                    "disconnected_state": disconnected["State"],
                    "restored_state": reconnected_network["State"],
                    "original_state": cs["State"], "connector_id": connector_id,
                    "endpoint_absent_while_disconnected": True,
                    "restored_ip": connector_ip, "restored_endpoints": restored,
                    "no_new_quic_connection_window_ms": 2000,
                    "owner_retained_until_cleanup_confirmation": True,
                    "recovery": "automatic_same_process_fresh_session" if automatic
                                else "explicit_stop_then_fresh_session_restart"}
                report.setdefault("network_disruptions", []).append(report["network_disruption"])
                if automatic:
                    event("connector", f"NBSR_CONNECTOR_SESSION_CLEANED attempt={attempt} owner_count=0")
                    validate_same_process(original_connector,
                                          json.loads(docker("inspect", names[1]))[0])
                    if args.cleanup_failure:
                        gateway.stdin.write(f"FAIL_CLEANUP {attempt}\n")
                        gateway.stdin.flush()
                        event("gateway", f"NBSR_CLEANUP_FAILED_BLOCKED attempt={attempt}")
                        validate_same_process(original_connector,
                                              json.loads(docker("inspect", names[1]))[0])
                        gateway.stdin.write(f"RETRY_CLEANUP {attempt}\n")
                        gateway.stdin.flush()
                        event("gateway", f"NBSR_CLEANUP_RETRY_BLOCKED attempt={attempt}")
                        validate_same_process(original_connector,
                                              json.loads(docker("inspect", names[1]))[0])
                        report["cleanup_failure"] = {
                            "injection": "synthetic_gateway_completion_error",
                            "owner_retained_failed_and_retry_pending": True,
                            "stale_ticket_rejected": True,
                            "no_new_connection_each_window_ms": 2000}
                    gateway.stdin.write(f"CONFIRM_RECONNECT_CLEANUP {attempt}\n")
                    gateway.stdin.flush()
                    event("gateway", f"NBSR_OWNER_RELEASED attempt={attempt}")
                    # Only Gateway's subsequent private fixture carries the
                    # exact prior-session cleanup receipt for the live worker.
                    continue
                # Network restoration alone is not process cleanup. Keep the
                # owner pending until this still-running process is stopped.
                mode = "term"
            if mode == "kill":
                docker("kill", "--signal", "SIGKILL", names[1])
            else:
                docker("stop", "--time", "5", names[1])
            connector.wait(timeout=5)
            readers[-1].join(timeout=1)
            if readers[-1].is_alive():
                raise RuntimeError("Connector output not drained")
            if mode == "term":
                event("connector", "NBSR_CONNECTOR_CLOSED owner_count=0")
                graceful_marker = True
            else:
                while True:
                    try:
                        pending.append(events.get_nowait())
                    except queue.Empty:
                        break
                graceful_marker = any(role == "connector" and kind == "public"
                    and "NBSR_CONNECTOR_CLOSED" in data for role, kind, data in pending)
            if not retained_observed:
                event("gateway", f"NBSR_OWNER_RETAINED attempt={attempt}")
            state = json.loads(docker("inspect", names[1]))[0]["State"]
            validate_stop(state, connector.returncode, mode, graceful_marker)
            remaining = json.loads(docker("network", "inspect", network))[0]["Containers"]
            assert connector_id not in remaining
            gateway_state = json.loads(docker("inspect", names[0]))[0]["State"]
            assert gateway_state["Running"] and gateway_state["StartedAt"] == original_gateway_start
            report["stops"].append({"attempt": attempt, "connector_state": state,
                "mode": mode, "graceful_cleanup_marker": graceful_marker,
                "attach_exit": connector.returncode, "connector_endpoint_absent": True,
                "gateway_started_at": original_gateway_start, "connector_id": connector_id,
                "network": remaining})
            confirmation = "CONFIRM_KILL" if mode == "kill" else "CONFIRM_STOP"
            gateway.stdin.write(f"{confirmation} {attempt}\n")
            gateway.stdin.flush()
            event("gateway", f"NBSR_OWNER_RELEASED attempt={attempt}")
        event("gateway", "NBSR_DOCKER_COMPLETE")
        gateway.wait(timeout=5)
        assert gateway.returncode == 0
        if automatic:
            assert len(report["network_disruptions"]) == args.cycles
            assert len(report["automatic_reconnections"]) == args.cycles
        report["status"] = "PASS"
    except Exception as error:
        # Do not serialize arbitrary exception payloads containing child stdout.
        report["error_type"] = type(error).__name__
        report["error_frames"] = [{"file": f.filename, "line": f.lineno}
                                  for f in traceback.extract_tb(error.__traceback__)]
        if isinstance(error, RuntimeError):
            report["error"] = str(error)
    finally:
        cleanup_errors = []

        def cleanup_budget(maximum):
            remaining = 119 - (time.monotonic() - started)
            if remaining <= 0:
                raise RuntimeError("cleanup budget exhausted")
            return min(maximum, remaining)

        for name in reversed(owned):
            try:
                subprocess.run(["docker", "rm", "-f", name], check=True, timeout=cleanup_budget(8),
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except Exception:
                cleanup_errors.append(name)
        if created_network:
            try:
                subprocess.run(["docker", "network", "rm", network], check=True, timeout=cleanup_budget(5),
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except Exception:
                cleanup_errors.append(network)
        for process in processes:
            try:
                process.wait(timeout=cleanup_budget(1))
            except (subprocess.TimeoutExpired, RuntimeError):
                process.kill()
                process.wait(timeout=1)
                cleanup_errors.append("docker attach did not exit")
        for thread in readers:
            thread.join(timeout=max(0, min(1, 119-(time.monotonic()-started))))
            if thread.is_alive():
                cleanup_errors.append("reader did not exit")
        try:
            after = {kind: subprocess.check_output(["docker", *cmd], text=True, timeout=cleanup_budget(3)).splitlines()
                     for kind, cmd in {
                         "containers": ("ps", "-aq", "--no-trunc"),
                         "networks": ("network", "ls", "-q", "--no-trunc"),
                         "volumes": ("volume", "ls", "-q")}.items()}
            report["after"] = after
            if any(set(after[k]) != set(report["before"][k]) for k in after):
                cleanup_errors.append("resource inventory changed")
        except Exception:
            cleanup_errors.append("resource inventory unconfirmed")
        log.close()
        report["cleanup_errors"] = cleanup_errors
        report["elapsed_seconds"] = time.monotonic()-started
        report["free_bytes"] = shutil.disk_usage(evidence).free
        if cleanup_errors or report["elapsed_seconds"] > 120:
            report["status"] = "FAIL"
        (evidence/"result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("status", "cleanup_errors", "elapsed_seconds")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
