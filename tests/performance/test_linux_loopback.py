import tempfile
import unittest
import json
from unittest.mock import patch
from pathlib import Path

from scripts.performance.linux_loopback import (
    build_commands, expand_matrix, parse_cpu_list, parse_proc_stat,
    physical_cpu_sets, repeat_target, validate_matrix,
    sample_process,
    run_cell,
)


class LinuxLoopbackTests(unittest.TestCase):
    def test_server_scale_matrix_preserves_physical_core_selection_and_worker_symmetry(self):
        matrix = {'schema': 'nbsr-linux-loopback-v1', 'cores': [8, 16, 32],
                  'workloads': [{'payload_bytes': 16384, 'streams': 8, 'outstanding': 1}],
                  'warmup_seconds': 3, 'duration_seconds': 20}
        validate_matrix(matrix)
        topology = {'cpus': [dict(cpu=n, core=n // 2, socket=0, node=0, online=True)
                             for n in range(64)]}
        selected = physical_cpu_sets(topology, set(range(64)), matrix['cores'])
        assert selected[32] == list(range(0, 64, 2))
        for cell in expand_matrix(matrix):
            server, client, _ = build_commands(cell, Path('/bin'), Path('/authority'),
                Path('/raw'), '127.0.0.1:1234', 3, 20)
            for command in (server, client):
                assert command[command.index('--p2a-runtime-workers') + 1] == str(cell['cores'])
        with self.assertRaises(ValueError):
            physical_cpu_sets(topology, set(range(32)), [32])

    def test_physical_selection_ignores_smt_and_uses_one_numa_node(self):
        topology = {"cpus": [
            {"cpu": "0", "core": "0", "socket": "0", "node": "0", "online": "yes"},
            {"cpu": "1", "core": "0", "socket": "0", "node": "0", "online": "yes"},
            {"cpu": "2", "core": "1", "socket": "0", "node": "0", "online": "yes"},
            {"cpu": "3", "core": "2", "socket": "0", "node": "1", "online": "yes"},
        ]}
        self.assertEqual(physical_cpu_sets(topology, {0, 1, 2, 3}, [1, 2]), {1: [0], 2: [0, 2]})
        with self.assertRaises(ValueError):
            physical_cpu_sets(topology, {0, 1, 2, 3}, [4])

    def test_cpu_list_and_proc_stat_with_spaces_and_parentheses(self):
        self.assertEqual(parse_cpu_list("0-2,5"), {0, 1, 2, 5})
        fields = ["S"] + ["0"] * 49
        fields[11], fields[12], fields[19], fields[21] = "10", "20", "99", "7"
        sample = parse_proc_stat("123 (a ) name) " + " ".join(fields), 100, 4096)
        self.assertEqual(sample["cpu_ns"], 300_000_000)
        self.assertEqual(sample["start_ticks"], 99)
        self.assertEqual(sample["rss_bytes"], 7 * 4096)

    def test_repeats_require_three_valid_then_five_on_dispersion(self):
        self.assertEqual(repeat_target([1, 1]), 3)
        self.assertEqual(repeat_target([1, 1, 1]), 3)
        self.assertEqual(repeat_target([1, 2, 3]), 5)
        self.assertEqual(repeat_target([1, 2, 3, 4, 5]), 5)

    def test_matrix_closed_and_matched(self):
        matrix = {"schema": "nbsr-linux-loopback-v1", "cores": [1, 2, 4],
                  "workloads": [{"payload_bytes": 1024, "streams": 64, "outstanding": 1}],
                  "warmup_seconds": 3, "duration_seconds": 20}
        validate_matrix(matrix)
        cells = expand_matrix(matrix)
        self.assertEqual(len(cells), 6)
        self.assertEqual({c["path"] for c in cells}, {"direct", "nbsr"})
        with self.assertRaises(ValueError):
            validate_matrix({**matrix, "unknown": True})
        with self.assertRaises(ValueError):
            validate_matrix({**matrix, "cores": [3]})
        with self.assertRaises(ValueError):
            validate_matrix({**matrix, "duration_seconds": float("nan")})

    def test_commands_match_existing_p2a_cli(self):
        cell = {"path": "nbsr", "cores": 2, "payload_bytes": 1024,
                "streams": 64, "outstanding": 4}
        server, client, env = build_commands(cell, Path("/binroot"), Path("/authority"),
                                            Path("/raw"), "127.0.0.1:123", 3, 20)
        self.assertEqual(server[0], str(Path("/binroot/wp8_interop_server")))
        self.assertEqual(client[0], str(Path("/binroot/perf_rust_source")))
        self.assertEqual(env, {"NBSR_P2A_STREAMS": "64"})
        self.assertIn("--completion-ack", server)
        self.assertEqual(client[client.index("--p2a-outstanding-per-stream") + 1], "4")
        direct, _, env = build_commands({**cell, "path": "direct"}, Path("/binroot"),
                                       Path("/authority"), Path("/raw"), "127.0.0.1:123", 3, 20)
        self.assertIn("--requests-per-connection", direct)
        self.assertEqual(env, {})

    def test_sampler_rejects_wrong_affinity_and_untracked_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = root / "123"
            task = process / "task" / "123"
            task.mkdir(parents=True)
            (process / "fd").mkdir()
            (process / "stat").write_text("123 (peer) S " + "0 " * 49)
            (task / "status").write_text("Cpus_allowed_list:\t0-1\n")
            (task / "children").write_text("")
            with self.assertRaisesRegex(RuntimeError, "affinity mismatch"):
                sample_process(123, [0], root, 100, 4096)
            (task / "status").write_text("Cpus_allowed_list:\t0\n")
            (task / "children").write_text("456")
            with self.assertRaisesRegex(RuntimeError, "untracked child"):
                sample_process(123, [0], root, 100, 4096)
            (task / "children").write_text("")
            self.assertEqual(sample_process(123, [0], root, 100, 4096)["thread_ids"], [123])
            (task / "status").unlink()
            with self.assertRaises(FileNotFoundError):
                sample_process(123, [0], root, 100, 4096)

    def test_run_cell_ack_follows_source_final_sample_and_exit(self):
        for path in ("direct", "nbsr"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                raw = root / "raw"
                binaries = root / "bin"
                events = []
                cell = {"path": path, "cores": 1, "payload_bytes": 1024,
                        "streams": 1, "outstanding": 1}
                record = {"completed_operations": 10, "measured_ns": 20_000_000_000,
                          **{key: 0 for key in ("errors", "missing", "duplicates", "corrupt", "wrong_request",
                             "transport_sessions_created_delta", "service_channels_created_delta",
                             "application_streams_created_delta", "replay_entries_delta")}}

                class FakeProcess:
                    def __init__(self, argv, **kwargs):
                        self.pid = 2 if "--endpoint" in argv else 1
                        self.returncode = None
                        if self.pid == 1:
                            (raw / "ready.json").write_text(json.dumps({"endpoint": "127.0.0.1:123"}))
                        else:
                            kwargs["stdout"].write(json.dumps(record) + "\n")
                    def wait(self, timeout):
                        events.append("source_exit" if self.pid == 2 else "server_exit")
                        self.returncode = 0
                        return 0
                    def kill(self):
                        self.returncode = -9

                def sample(pid, cpus):
                    state = "S"
                    if pid == 2:
                        self.assertFalse((raw / "completion.ack").exists(), "ACK preceded final source sample")
                        events.append("source_final")
                        state = "Z"
                    elif "source_exit" in events:
                        self.assertTrue((raw / "completion.ack").exists(), "destination waited without ACK")
                        events.append("server_final")
                        state = "Z"
                    return {"state": state, "cpu_ns": 100, "start_ticks": pid, "pid": pid}

                original_resolve, original_touch = Path.resolve, Path.touch
                def resolve(value, *args, **kwargs):
                    if value == Path("/proc/2/exe"):
                        return original_resolve(binaries / ("perf_direct_peer" if path == "direct" else "perf_rust_source"))
                    return original_resolve(value, *args, **kwargs)
                def touch(value, *args, **kwargs):
                    if value.name == "completion.ack":
                        self.assertIn("source_exit", events)
                        events.append("ack")
                    return original_touch(value, *args, **kwargs)

                with patch("scripts.performance.linux_loopback.subprocess.Popen", FakeProcess), \
                     patch("scripts.performance.linux_loopback.sample_process", side_effect=sample), \
                     patch("scripts.performance.linux_loopback.time.sleep"), \
                     patch.object(Path, "resolve", resolve), patch.object(Path, "touch", touch):
                    result = run_cell(cell, 1, binaries, root / "authority", raw, [0],
                                      {"warmup_seconds": 3, "duration_seconds": 20}, "taskset")
                self.assertTrue(result["valid"])
                self.assertLess(events.index("source_final"), events.index("source_exit"))
                self.assertLess(events.index("source_exit"), events.index("ack"))
                self.assertLess(events.index("ack"), events.index("server_final"))


if __name__ == "__main__":
    unittest.main()
