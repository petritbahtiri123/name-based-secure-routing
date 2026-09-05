import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("isp_isolation", Path(__file__).with_name("run_isolation.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeBackend:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.commands = []

    def run(self, argv, *, check=True):
        self.commands.append(argv)
        value = next(self.responses)
        if check and value[0]:
            raise RuntimeError("command failed")
        return value


class IsolationTests(unittest.TestCase):
    @staticmethod
    def inspected_topology():
        """Synthetic contract data, not retained Docker execution evidence.

        Moby v28.0.0 daemon/container_operations.go initializes Networks["none"]
        in updateContainerNetworkSettings, but returns early for container mode.
        daemon/inspect.go copies those endpoint maps into the inspect response.
        """
        images = {"runtime": "sha256:" + "a" * 64, "adapter": "sha256:" + "b" * 64}
        network_ids = {name: str(index) * 64 for index, name in enumerate(sorted(MODULE.NETWORKS), 1)}
        container_ids = {name: format(index, "x") * 64 for index, name in enumerate(sorted(MODULE.SERVICES), 1)}
        containers = []
        for name in sorted(MODULE.SERVICES - {"client-workload"}):
            endpoints = {key: {"NetworkID": network_ids[key], "IPAddress": "172.30.23.2"} for key in MODULE.MEMBERSHIPS.get(name, set())}
            mode = "default"
            if name == "federation-preflight":
                mode = "none"
                endpoints = {
                    "none": {
                        "NetworkID": "f" * 64,
                        "IPAddress": "",
                        "Gateway": "",
                        "GlobalIPv6Address": "",
                        "IPv6Gateway": "",
                        "MacAddress": "",
                    }
                }
            elif name.endswith("adapter"):
                mode = "container:" + container_ids[name.replace("adapter", "runtime")]
            containers.append(
                {
                    "Id": container_ids[name],
                    "Config": {"Labels": {"com.docker.compose.service": name}, "User": "65532:65532"},
                    "HostConfig": {"NetworkMode": mode, "ReadonlyRootfs": True, "CapDrop": ["ALL"]},
                    "Image": images["adapter" if name.endswith("adapter") else "runtime"],
                    "NetworkSettings": {"Networks": endpoints, "Ports": {}},
                    "State": {"ExitCode": 0, "Health": {"Status": "healthy"}},
                }
            )
        networks = [
            {
                "Id": network_ids[name],
                "Labels": {"com.docker.compose.network": name},
                "Internal": True,
                "IPAM": {"Config": [{"Subnet": "172.30.23.0/24"}]},
                "Containers": {
                    container_ids[service]: {}
                    for service in container_ids
                    if service != "client-workload" and name in MODULE.MEMBERSHIPS.get(service, set())
                },
            }
            for name in sorted(MODULE.NETWORKS)
        ]
        return {"container": containers, "network": networks, "volume": []}, images

    def test_moby_none_endpoint_and_shared_namespace_shapes_are_accepted(self):
        resources, images = self.inspected_topology()
        origin, _ = MODULE.validate_live_topology(resources, images, "172.30.23.0/24")
        self.assertEqual(origin, "172.30.23.2")

    def test_none_mode_cannot_hide_address_or_another_network(self):
        for endpoint in (
            {"none": {"NetworkID": "f" * 64, "IPAddress": "172.30.23.8"}},
            {"bridge": {"NetworkID": "f" * 64, "IPAddress": ""}},
        ):
            resources, images = self.inspected_topology()
            preflight = next(
                item for item in resources["container"] if item["Config"]["Labels"]["com.docker.compose.service"] == "federation-preflight"
            )
            preflight["NetworkSettings"]["Networks"] = endpoint
            with self.assertRaises(ValueError):
                MODULE.validate_live_topology(resources, images, "172.30.23.0/24")

    def test_reachable_origin_fails_with_fake_command_backend(self):
        backend = FakeBackend([(0, json.dumps({"connected": True, "resolved": True, "reason": "connected"}), "")])
        with self.assertRaisesRegex(ValueError, "reachable"):
            MODULE.execute_probe(backend, ["docker", "exec", "owned"], "private-origin", by_name=True)

    def test_name_resolution_alone_does_not_prove_isolation(self):
        backend = FakeBackend([(0, json.dumps({"connected": False, "resolved": True, "reason": "connect_failed"}), "")])
        with self.assertRaises(ValueError):
            MODULE.execute_probe(backend, ["docker", "exec", "owned"], "private-origin", by_name=True)

    def test_missing_or_boolean_origin_counter_fails(self):
        for value in ({}, {"connections": True, "accepted_requests": 0, "rejected_requests": 0}):
            backend = FakeBackend([(0, json.dumps(value), "")])
            with self.assertRaises(ValueError):
                MODULE.read_counters(backend, ["docker", "compose"])

    def test_failed_workload_cannot_become_pass(self):
        for result in ((1, "NBSR_ISP_POC_WORKLOAD status=PASS_BODY_ONLY\n", ""), (0, "other\n", "")):
            backend = FakeBackend([result])
            with self.assertRaises((RuntimeError, ValueError)):
                MODULE.run_workload(backend, ["docker", "compose"])

    def test_cleanup_mismatched_label_is_not_deleted(self):
        backend = FakeBackend([(0, json.dumps([{"Id": "a" * 64, "Config": {"Labels": {"com.docker.compose.project": "unrelated"}}}]), "")])
        with self.assertRaises(ValueError):
            MODULE.validate_owned_inspection(backend.run(["docker", "inspect", "a" * 64])[1], "nbsr-isp-poc-run", "container")
        self.assertEqual(len(backend.commands), 1)

    def test_unsafe_compose_topology_fails(self):
        images = {"runtime": "sha256:" + "a" * 64, "adapter": "sha256:" + "b" * 64}
        services = {}
        for name in MODULE.SERVICES:
            services[name] = {
                "image": images["adapter" if name.endswith("adapter") else "runtime"],
                "user": "65532:65532",
                "pull_policy": "never",
                "read_only": True,
                "cap_drop": ["ALL"],
            }
            if name in MODULE.MEMBERSHIPS:
                services[name]["networks"] = {network: {} for network in MODULE.MEMBERSHIPS[name]}
            else:
                services[name]["network_mode"] = (
                    "none" if name == "federation-preflight" else "service:" + name.replace("adapter", "runtime")
                )
        configuration = {
            "services": services,
            "networks": {name: {"internal": True} for name in MODULE.NETWORKS},
            "volumes": {name: {} for name in MODULE.VOLUMES},
        }
        MODULE.validate_compose(configuration, images)
        configuration["services"]["private-origin"]["ports"] = ["8080:8080"]
        with self.assertRaisesRegex(ValueError, "exposure"):
            MODULE.validate_compose(configuration, images)

    def test_cleanup_requires_empty_final_inventory(self):
        owned = {
            "Id": "a" * 64,
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "nbsr-isp-poc-run",
                    "com.docker.compose.service": "private-origin",
                    "nbsr.isp-poc.scope": "logical-isolation",
                }
            },
        }
        backend = FakeBackend(
            [(0, "", ""), (0, "", ""), (0, "", ""), (0, "a" * 64, ""), (0, json.dumps([owned]), ""), (0, "", ""), (0, "", "")]
        )
        with self.assertRaisesRegex(ValueError, "left project-owned"):
            MODULE.cleanup(backend, "nbsr-isp-poc-run")

    def test_counter_delta_requires_exactly_one_authorized_operation(self):
        baseline = {"connections": 0, "accepted_requests": 0, "rejected_requests": 0}
        MODULE.check_authorized_delta(baseline, {"connections": 1, "accepted_requests": 1, "rejected_requests": 0})
        with self.assertRaises(ValueError):
            MODULE.check_authorized_delta(baseline, {"connections": 2, "accepted_requests": 1, "rejected_requests": 0})


if __name__ == "__main__":
    unittest.main()
