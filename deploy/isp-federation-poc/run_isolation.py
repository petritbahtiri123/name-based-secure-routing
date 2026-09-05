"""Bounded live isolation evidence for one exact prepared Compose project.

No Docker repair, implicit base-image pull, host firewall edit or runtime
ownership-zero claim. Requires a usable engine and prepare.py output.
"""

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
SERVICES = {"federation-preflight", "private-origin", "isp-a-runtime", "isp-b-runtime", "isp-a-adapter", "isp-b-adapter", "client-workload"}
NETWORKS = {"isp_a_access", "federation_transit", "isp_b_private"}
VOLUMES = {"runtime", "projection_a", "projection_b", "control"}
COUNTERS = {"connections", "accepted_requests", "rejected_requests"}
MEMBERSHIPS = {
    "private-origin": {"isp_b_private"},
    "isp-a-runtime": {"isp_a_access", "federation_transit"},
    "isp-b-runtime": {"federation_transit", "isp_b_private"},
    "client-workload": {"isp_a_access"},
}
PROBE_CODE = """import json,signal,socket,sys
def expired(*args): raise TimeoutError('probe deadline')
signal.signal(signal.SIGALRM,expired)
signal.alarm(3)
target=sys.argv[1]
result={'connected':False,'resolved':False,'reason':'dns_failed'}
try:
 addresses=socket.getaddrinfo(target,8080,socket.AF_INET,socket.SOCK_STREAM)
 result['resolved']=bool(addresses)
 if len({item[4][0] for item in addresses})!=1: raise OSError('ambiguous')
 result['reason']='connect_failed'
 connection=socket.create_connection((addresses[0][4][0],8080),timeout=2)
 connection.close()
 result.update(connected=True,reason='connected')
except OSError: pass
print(json.dumps(result,sort_keys=True))
"""
COUNTER_CODE = "from pathlib import Path; print(Path('/state/counter.json').read_text())"


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


class Backend:
    def __init__(self, output):
        self.output = output
        self.commands = []

    def run(self, argv, *, check=True):
        ordinal = len(self.commands)
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=180)
            code, out, err = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            code = -1
            out = error.stdout or b""
            err = error.stderr or b""
            out = out.decode(errors="replace") if isinstance(out, bytes) else out
            err = err.decode(errors="replace") if isinstance(err, bytes) else err
        (self.output / f"{ordinal:03d}.stdout").write_text(out, encoding="utf-8")
        (self.output / f"{ordinal:03d}.stderr").write_text(err, encoding="utf-8")
        self.commands.append(
            {"argv": argv, "exit_code": code, "raw_stdout": f"{ordinal:03d}.stdout", "raw_stderr": f"{ordinal:03d}.stderr"}
        )
        write_json(self.output / "commands.json", self.commands)
        if check and code != 0:
            raise RuntimeError("command failed; raw output preserved")
        return code, out, err


def validate_compose(value, images):
    if set(value.get("services", {})) != SERVICES or set(value.get("networks", {})) != NETWORKS:
        raise ValueError("unexpected Compose service/network inventory")
    if set(value.get("volumes", {})) != VOLUMES or any(network.get("internal") is not True for network in value["networks"].values()):
        raise ValueError("networks/volumes do not match the isolated topology")
    for name, service in value["services"].items():
        expected_image = images["adapter"] if name in ("isp-a-adapter", "isp-b-adapter") else images["runtime"]
        if service.get("image") != expected_image or service.get("pull_policy") != "never" or service.get("user") != "65532:65532":
            raise ValueError("unverified runtime image or user")
        if (
            service.get("ports")
            or service.get("privileged")
            or service.get("read_only") is not True
            or "ALL" not in service.get("cap_drop", [])
        ):
            raise ValueError("unsafe container exposure or privilege")
        if service.get("cap_add") or service.get("devices") or service.get("pid") == "host" or service.get("ipc") == "host":
            raise ValueError("host/privileged capability forbidden")
        for mount in service.get("volumes", []):
            if (
                not isinstance(mount, dict)
                or mount.get("type") != "volume"
                or mount.get("source") not in VOLUMES
                or "docker.sock" in str(mount)
            ):
                raise ValueError("unexpected filesystem mount")
        if name in MEMBERSHIPS:
            if set(service.get("networks", {})) != MEMBERSHIPS[name] or service.get("network_mode"):
                raise ValueError("network membership leaked")
        elif name == "federation-preflight":
            if service.get("network_mode") != "none" or service.get("networks"):
                raise ValueError("preflight network forbidden")
        else:
            runtime = "isp-a-runtime" if name == "isp-a-adapter" else "isp-b-runtime"
            if service.get("network_mode") != "service:" + runtime or service.get("networks"):
                raise ValueError("adapter namespace mismatch")


def validate_owned_inspection(raw, project, kind):
    values = loads(raw)
    if not isinstance(values, list):
        raise ValueError("inspection is not an array")
    for value in values:
        labels = value.get("Config", {}).get("Labels", {}) if kind == "container" else value.get("Labels", {})
        labels = labels or {}
        expected = SERVICES if kind == "container" else NETWORKS if kind == "network" else VOLUMES
        label = "service" if kind == "container" else kind
        if (
            labels.get("com.docker.compose.project") != project
            or labels.get("nbsr.isp-poc.scope") != "logical-isolation"
            or labels.get("com.docker.compose." + label) not in expected
        ):
            raise ValueError("ownership label mismatch; resource will not be deleted")
        identifier = value.get("Id") if kind != "volume" else value.get("Name")
        if kind != "volume" and not re.fullmatch(r"[0-9a-f]{64}", identifier or ""):
            raise ValueError("invalid resource ID")
        if kind == "volume" and not re.fullmatch(re.escape(project) + r"_[a-z_]+", identifier or ""):
            raise ValueError("volume name escaped project")
    return values


def inventory(backend, project):
    result = {}
    for kind, argv in (
        ("container", ["docker", "ps", "--all", "--quiet"]),
        ("network", ["docker", "network", "ls", "--quiet"]),
        ("volume", ["docker", "volume", "ls", "--quiet"]),
    ):
        names = backend.run([*argv, "--filter", "label=com.docker.compose.project=" + project])[1].split()
        if not names:
            result[kind] = []
            continue
        inspect = ["docker", "inspect"] if kind == "container" else ["docker", kind, "inspect"]
        result[kind] = validate_owned_inspection(backend.run([*inspect, *names])[1], project, kind)
    return result


def validate_live_topology(resources, images, private_cidr):
    containers = {item["Config"]["Labels"]["com.docker.compose.service"]: item for item in resources["container"]}
    if len(containers) != len(resources["container"]) or set(containers) != SERVICES - {"client-workload"}:
        raise ValueError("unexpected live service inventory")
    networks = {item["Labels"]["com.docker.compose.network"]: item for item in resources["network"]}
    if set(networks) != NETWORKS or any(item.get("Internal") is not True for item in networks.values()):
        raise ValueError("live networks are not isolated")
    private_subnets = [entry.get("Subnet") for entry in networks["isp_b_private"].get("IPAM", {}).get("Config", [])]
    if private_subnets != [private_cidr]:
        raise ValueError("private subnet changed from preparation")
    for network_name, network in networks.items():
        expected_members = {container["Id"] for name, container in containers.items() if network_name in MEMBERSHIPS.get(name, set())}
        if set(network.get("Containers", {})) != expected_members:
            raise ValueError("unexpected participant in isolated network")
    for name, container in containers.items():
        config = container["HostConfig"]
        if (
            config.get("Privileged")
            or config.get("PortBindings")
            or config.get("PublishAllPorts")
            or config.get("ReadonlyRootfs") is not True
            or config.get("CapAdd")
        ):
            raise ValueError("live exposure/privilege mismatch")
        if (
            "ALL" not in config.get("CapDrop", [])
            or config.get("PidMode") == "host"
            or config.get("IpcMode") == "host"
            or config.get("Devices")
        ):
            raise ValueError("live host capability mismatch")
        if any(container.get("NetworkSettings", {}).get("Ports", {}).values()):
            raise ValueError("live host port publication")
        if container["Config"].get("User") != "65532:65532" or any(
            mount.get("Type") == "bind" or "docker.sock" in str(mount) for mount in container.get("Mounts", [])
        ):
            raise ValueError("live user/mount mismatch")
        expected_image = images["adapter"] if name in ("isp-a-adapter", "isp-b-adapter") else images["runtime"]
        if container["Image"] != expected_image:
            raise ValueError("live image differs from prepared image")
        attached = {item["NetworkID"] for item in container.get("NetworkSettings", {}).get("Networks", {}).values()}
        if name in MEMBERSHIPS:
            if attached != {networks[key]["Id"] for key in MEMBERSHIPS[name]}:
                raise ValueError("live network membership leaked")
        elif name == "federation-preflight":
            endpoints = container.get("NetworkSettings", {}).get("Networks", {})
            # Moby preserves a named none endpoint; it is not a project bridge.
            none = endpoints.get("none", {})
            address_fields = (
                "IPAddress",
                "Gateway",
                "GlobalIPv6Address",
                "IPv6Gateway",
                "MacAddress",
                "IPPrefixLen",
                "GlobalIPv6PrefixLen",
                "IPAMConfig",
            )
            if (
                config.get("NetworkMode") != "none"
                or set(endpoints) - {"none"}
                or any(none.get(key) for key in address_fields)
                or container["State"].get("ExitCode") != 0
            ):
                raise ValueError("preflight did not finish safely")
        else:
            runtime = "isp-a-runtime" if name == "isp-a-adapter" else "isp-b-runtime"
            if config.get("NetworkMode") != "container:" + containers[runtime]["Id"] or attached:
                raise ValueError("live adapter namespace mismatch")
        if name != "federation-preflight" and container.get("State", {}).get("Health", {}).get("Status") != "healthy":
            raise ValueError("service health unavailable")
    private_id = networks["isp_b_private"]["Id"]
    entries = containers["private-origin"]["NetworkSettings"]["Networks"].values()
    origin_ip = next(item["IPAddress"] for item in entries if item["NetworkID"] == private_id)
    if ipaddress.IPv4Address(origin_ip) not in ipaddress.IPv4Network(private_cidr, strict=True):
        raise ValueError("origin address escaped private subnet")
    return origin_ip, networks["isp_a_access"]["Id"]


def execute_probe(backend, prefix, target, *, by_name):
    result = loads(backend.run([*prefix, "-c", PROBE_CODE, target])[1])
    if set(result) != {"connected", "resolved", "reason"} or type(result["connected"]) is not bool or type(result["resolved"]) is not bool:
        raise ValueError("probe result missing")
    if result["connected"] or (by_name and result["resolved"]):
        raise ValueError("private origin reachable or resolvable from unauthorized namespace")
    if result["reason"] not in ("dns_failed", "connect_failed"):
        raise ValueError("unexpected probe result")
    return result


def read_counters(backend, compose):
    value = loads(backend.run([*compose, "exec", "-T", "private-origin", "python3", "-c", COUNTER_CODE])[1])
    if not isinstance(value, dict) or set(value) != COUNTERS or any(type(number) is not int or number < 0 for number in value.values()):
        raise ValueError("origin counters missing or malformed")
    return value


def check_authorized_delta(before, after):
    if {key: after[key] - before[key] for key in COUNTERS} != {"connections": 1, "accepted_requests": 1, "rejected_requests": 0}:
        raise ValueError("authorized origin counter delta is not exactly one")


def run_workload(backend, compose):
    output = backend.run([*compose, "run", "--rm", "--no-deps", "client-workload"])[1]
    if output.strip() != "NBSR_ISP_POC_WORKLOAD status=PASS_BODY_ONLY":
        raise ValueError("workload did not verify the exact body")


def validate_preflight_result(value, sha):
    artifacts = (
        "vectors/wp8-f75-route-open/federation-context.cbor",
        "vectors/wp8-local-admission/source.cose",
        "vectors/wp8-local-admission/destination.cose",
    )
    expected = {
        "schema": "nbsr-isp-preflight-v1",
        "status": "PASS",
        "source_sha": sha,
        "operators": ["isp-a", "isp-b"],
        "admitted_grants": 1,
        "active_allocations": 0,
        "limit_buckets": 8,
        "artifacts": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in artifacts},
        "live_runtime_federation": "NOT_CLAIMED",
    }
    if value != expected or any(type(value.get(key)) is not int for key in ("admitted_grants", "active_allocations", "limit_buckets")):
        raise ValueError("federation preflight result or artifact binding invalid")


def preserve_and_cleanup(backend, project):
    resources = inventory(backend, project)
    ids = [item["Id"] for item in resources["container"]]
    if ids:
        backend.run(["docker", "stop", "--time", "5", *ids])
    holders = [item for item in resources["container"] if item["Config"]["Labels"]["com.docker.compose.service"]
               in {"federation-preflight", "isp-a-runtime", "isp-b-runtime"}]
    if holders:
        # Child stdout/stderr are files in the shared runtime volume, not Docker logs.
        source = f"{holders[0]['Id']}:/src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/{project}/logs"
        target = backend.output / "runtime-child-logs"
        backend.run(["docker", "cp", source, str(target)])
        files = list(target.rglob("*"))
        if not files or any(path.is_symlink() or not path.is_file() for path in files):
            raise ValueError("child log export missing or unexpected; runtime resources retained")
        write_json(backend.output / "runtime-child-logs-manifest.json", {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files
        })
    elif resources["volume"]:
        raise ValueError("runtime volume exists without inspectable holder; retained for evidence")
    return cleanup(backend, project)


def cleanup(backend, project):
    # Inventory and validate every final ID before issuing any deletion.
    resources = inventory(backend, project)
    ids = [value["Id"] for value in resources["container"]]
    if ids:
        backend.run(["docker", "stop", "--time", "5", *ids], check=False)
        backend.run(["docker", "rm", *ids], check=False)
    ids = [value["Id"] for value in resources["network"]]
    if ids:
        backend.run(["docker", "network", "rm", *ids], check=False)
    names = [value["Name"] for value in resources["volume"]]
    if names:
        backend.run(["docker", "volume", "rm", *names], check=False)
    remaining = inventory(backend, project)
    if any(remaining.values()):
        raise ValueError("cleanup left project-owned resources")
    return {"status": "PASS_DOCKER_RESOURCES_ZERO", "containers": 0, "networks": 0, "volumes": 0, "runtime_owned_counters": "NOT_MEASURED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True, help="prepare.py manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepared = args.prepared.resolve()
    manifest = loads(prepared.read_text())
    project = manifest["project"]
    if (
        not re.fullmatch(r"nbsr-isp-poc-[a-z0-9-]{1,40}", project)
        or project.endswith("-")
        or manifest.get("status") != "BUILD_AND_CONFIG_ONLY"
    ):
        parser.error("prepared bounded project required")
    images = manifest["images"]
    if set(images) != {"runtime", "adapter"} or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in images.values()):
        parser.error("prepared immutable image IDs required")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if sha != manifest["source_sha"]:
        parser.error("prepared/current source SHA mismatch")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True):
        parser.error("clean accepted checkout required")
    expected_env = {
        "NBSR_ISP_RUNTIME_IMAGE": images["runtime"],
        "NBSR_ISP_ADAPTER_IMAGE": images["adapter"],
        "NBSR_ISP_RUN_ID": project,
        "NBSR_SOURCE_SHA": sha,
        "ISP_B_PRIVATE_CIDR": manifest["private_cidr"],
    }
    env_path = prepared.with_name("compose.env")
    lines = env_path.read_text().splitlines()
    if len(lines) != len(expected_env) or dict(line.split("=", 1) for line in lines) != expected_env:
        parser.error("Compose environment changed from preparation")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    backend = Backend(raw)
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "--project-name",
        project,
        "--file",
        "deploy/isp-federation-poc/compose.yaml",
    ]
    analysis = {
        "network_isolation": "NOT_RUN",
        "federation_admission_preflight": "NOT_RUN",
        "live_runtime_federation": "NOT_CLAIMED",
        "runtime_owned_counters": "NOT_MEASURED",
        "cleanup": "NOT_RUN",
        "status": "FAIL",
    }
    started = False
    try:
        configuration = loads(backend.run([*compose, "config", "--format", "json"])[1])
        validate_compose(configuration, images)
        if any(inventory(backend, project).values()):
            raise ValueError("project already owns resources; refusing adoption")
        started = True
        backend.run([*compose, "up", "--abort-on-container-exit", "--exit-code-from", "federation-preflight", "federation-preflight"])
        backend.run([*compose, "up", "--detach", "--no-deps", "--wait", "--wait-timeout", "60", "private-origin"])
        backend.run([*compose, "up", "--detach", "--no-deps", "--wait", "--wait-timeout", "90", "isp-a-runtime", "isp-b-runtime"])
        backend.run([*compose, "up", "--detach", "--no-deps", "--wait", "--wait-timeout", "30", "isp-a-adapter", "isp-b-adapter"])
        resources = inventory(backend, project)
        write_json(output / "topology.json", resources)
        origin_ip, access_id = validate_live_topology(resources, images, manifest["private_cidr"])
        preflight_path = f"/src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/{project}/preflight.json"
        preflight_code = "from pathlib import Path;import sys;print(Path(sys.argv[1]).read_text())"
        preflight = loads(backend.run([*compose, "exec", "-T", "isp-a-runtime", "python3", "-c", preflight_code, preflight_path])[1])
        validate_preflight_result(preflight, sha)
        write_json(output / "preflight.json", preflight)
        analysis["federation_admission_preflight"] = "PASS"
        baseline = read_counters(backend, compose)
        write_json(output / "origin-before.json", baseline)
        if any(baseline.values()):
            raise ValueError("origin saw traffic before isolation checks")
        probes = []
        for by_name, target in ((True, "private-origin"), (False, origin_ip)):
            suffix = "dns" if by_name else "ip"
            name = project + "-probe-" + suffix
            prefix = [*compose, "run", "--no-deps", "--name", name, "--entrypoint", "python3", "client-workload"]
            result = execute_probe(backend, prefix, target, by_name=by_name)
            inspection = validate_owned_inspection(backend.run(["docker", "inspect", name])[1], project, "container")
            if len(inspection) != 1 or {value["NetworkID"] for value in inspection[0]["NetworkSettings"]["Networks"].values()} != {
                access_id
            }:
                raise ValueError("client probe namespace not access-only")
            write_json(raw / ("client-probe-" + suffix + "-topology.json"), inspection)
            backend.run(["docker", "rm", inspection[0]["Id"]])
            probes.append({"source": "client", "target_kind": suffix, "result": result})
            result = execute_probe(backend, [*compose, "exec", "-T", "isp-a-runtime", "python3"], target, by_name=by_name)
            probes.append({"source": "isp-a", "target_kind": suffix, "result": result})
        write_json(output / "probes.json", probes)
        after_probes = read_counters(backend, compose)
        write_json(output / "origin-after-probes.json", after_probes)
        if after_probes != baseline:
            raise ValueError("direct-origin probes reached the origin")
        analysis["network_isolation"] = "PASS_FOUR_DENIED_PROBES"
        run_workload(backend, compose)
        after_workload = read_counters(backend, compose)
        write_json(output / "origin-after-workload.json", after_workload)
        check_authorized_delta(after_probes, after_workload)
        analysis["authorized_body"] = "PASS_EXACT_BODY_AND_ONE_ORIGIN_REQUEST"
        result_path = f"/src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/{project}/destination/supervisor-result.json"
        deadline = time.monotonic() + 20
        while True:
            code = "from pathlib import Path;import sys;path=Path(sys.argv[1]);print(path.read_text() if path.exists() else 'null')"
            result = loads(backend.run([*compose, "exec", "-T", "isp-b-runtime", "python3", "-c", code, result_path])[1])
            if result is not None:
                if result.get("status") != "PASS_PROCESS_EXIT":
                    raise ValueError("destination did not finish successfully")
                write_json(output / "destination-result.json", result)
                break
            if time.monotonic() > deadline:
                raise ValueError("destination completion result missing")
            time.sleep(0.2)
        analysis["status"] = "PASS_SCOPED_ISOLATION_AND_BODY"
    except Exception as error:
        analysis["reason"] = str(error)
        raise
    finally:
        if started:
            try:
                log_code = backend.run([*compose, "logs", "--no-color"], check=False)[0]
                analysis["log_capture"] = "PASS" if log_code == 0 else "FAIL"
            except Exception:
                analysis["log_capture"] = "FAIL"
            try:
                analysis["cleanup"] = preserve_and_cleanup(backend, project)
            except Exception as error:
                analysis["cleanup"] = {"status": "FAIL", "reason": str(error)}
                analysis["status"] = "FAIL"
            if analysis["log_capture"] != "PASS":
                analysis["status"] = "FAIL"
        write_json(output / "analysis.json", analysis)
        write_json(
            output / "manifest.json",
            {
                "source_sha": sha,
                "project": project,
                "images": images,
                "prepared_manifest_sha256": hashlib.sha256(prepared.read_bytes()).hexdigest(),
                "claim_scope": "one logical Docker topology",
                "runtime_owned_counters": "NOT_MEASURED",
                "live_runtime_federation": "NOT_CLAIMED",
            },
        )
        (output / "summary.md").write_text(
            "# ISP isolation evidence\n\nStatus: "
            + analysis["status"]
            + "\n\nRuntime ownership counters: NOT_MEASURED. Live runtime federation: NOT_CLAIMED.\n"
        )
        files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "checksums.sha256")
        (output / "checksums.sha256").write_text(
            "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(output).as_posix() + "\n" for path in files)
        )
    if analysis["status"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
