"""Local-only contracts. No SSH, SCP, sockets, keys or worker execution."""

import contextlib
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import vm_pair as vm
from vm_pair_overlay import GO, RUST, overlay, pinned_sources

REPO = Path(__file__).resolve().parents[3]


class VmPairTests(unittest.TestCase):
    def test_overlay_matches_pinned_source_and_keeps_lifecycle_checks(self):
        original = pinned_sources(REPO)
        go, rust = overlay(*original)
        self.assertIn("local := net.IPv4(10, 77, 0, 2)", go)
        self.assertIn('c.Case != "positive"', go)
        self.assertIn('host != "10.77.0.1"', go)
        self.assertIn('os.Getenv("NBSR_CONNECTOR_DOCKER_ENDPOINT") != ""', go)
        self.assertIn('endpoint_at(p, "10.77.0.1:0".parse().unwrap())', rust)
        for check in (
            '"child FIN after validated renewal"',
            "gateway.finish_cleanup(&t).unwrap()",
            "assert!(gateway.owner.is_none())",
            '"Rust UDP socket released"',
            '"CONNECTOR_EXIT_0_SOCKET_RELEASED"',
        ):
            self.assertIn(check, rust)
        self.assertNotIn('env!("CARGO_MANIFEST_DIR")', rust)
        self.assertNotIn("Command::new(binary)", rust)
        self.assertNotIn("child.0", rust)
        self.assertIn("pub mod docker;", rust)
        with self.assertRaises(ValueError):
            overlay(original[0].replace("local := net.IPv4(127, 0, 0, 1)", "changed"), original[1])

    def test_handoff_and_cleanup_reject_wrong_values(self):
        self.assertEqual(vm.validate_handoff({"Case": "positive", "Endpoint": "10.77.0.1:1234"}), "1234")
        for case, endpoint in [
            ("negative", "10.77.0.1:1234"),
            ("positive", "10.77.0.2:1234"),
            ("positive", "10.77.0.1:22"),
            ("positive", "10.77.0.1:65536"),
        ]:
            with self.assertRaises(ValueError):
                vm.validate_handoff({"Case": case, "Endpoint": endpoint})
        self.assertTrue(vm.valid_client_cleanup(b"loopback_socket_released=10.77.0.2:1234"))
        self.assertFalse(vm.valid_client_cleanup(b"loopback_socket_released=10.77.0.2:0"))
        for line in (
            b"SPHERE_GATEWAY_CLEANUP gateway_socket_released=false owner_count=0",
            b"SPHERE_GATEWAY_CLEANUP gateway_socket_released=true owner_count=1",
            b"SPHERE_CONNECTOR_PASS synthetic_authority=false",
            b"SPHERE_PEER 10.77.0.3:1234 -> 10.77.0.1:1234",
            b"test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 2 filtered out; finished in 0.00s",
        ):
            with self.assertRaises(ValueError):
                vm.validate_server_line(line, "1234")
        self.assertEqual(
            vm.validate_server_line(b"SPHERE_GATEWAY_CLEANUP gateway_socket_released=true owner_count=0", "1234"),
            "gateway_cleanup_verified",
        )
        self.assertIsNone(vm.validate_server_line(b"private fixture secret", "1234"))

    def test_shared_deadline_includes_cleanup(self):
        with (
            patch.object(vm.time, "monotonic", return_value=94),
            patch.object(vm, "WORK_END", 95),
            patch.object(vm, "TOTAL_END", 120),
            patch.object(vm, "CLEANING", False),
        ):
            self.assertEqual(vm.remaining(35), 1)
            with patch.object(vm, "CLEANING", True):
                self.assertEqual(vm.remaining(35), 26)
            with patch.object(vm.time, "monotonic", return_value=121):
                with self.assertRaises(TimeoutError):
                    vm.remaining(1)

    def test_output_overflow_fails_without_blocking(self):
        q = queue.Queue()
        q.overflow = threading.Event()
        q.overflow.set()
        with patch.object(vm, "remaining", return_value=1):
            with self.assertRaises(RuntimeError):
                list(vm.each(q, 1))

    def test_cleanup_requires_remote_exit_and_preserves_failure(self):
        with patch.object(vm, "started", {"client"}), patch.object(vm, "run") as run:
            run.return_value = Mock(returncode=5)
            with self.assertRaises(RuntimeError):
                vm.cleanup("client")
            self.assertIn("test -f worker.exit &&", run.call_args.args[0][-1])

    def test_output_failure_while_waiting_cannot_look_like_clean_eof(self):
        q = Mock(overflow=threading.Event())

        def failed_read(**unused):
            q.overflow.set()
            return None

        q.get.side_effect = failed_read
        with patch.object(vm, "remaining", return_value=1):
            with self.assertRaises(RuntimeError):
                list(vm.each(q, 1))

    def test_failed_trial_retains_safe_error_and_uncertain_cleanup(self):
        def failed_stage(role, hashes):
            vm.attempted.add(role)
            vm.created.add(role)
            raise ValueError("PRIVATE KEY MUST NOT APPEAR")

        with patch.object(vm, "stage", side_effect=failed_stage), patch.object(vm, "cleanup", side_effect=RuntimeError("PRIVATE ENDPOINT")):
            result = vm.execute({"artifacts": {}})
        self.assertFalse(result["pass"])
        self.assertFalse(result["cleanup_confirmed"])
        self.assertEqual(result["errors"], ["trial:ValueError", "client_cleanup:RuntimeError"])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_staging_pins_transfer_to_validated_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "go-connector"
            binary.write_bytes(b"validated")
            expected = {"go-connector": vm.hashlib.sha256(b"validated").hexdigest()}
            commands = []

            def local_fake_run(args, *unused):
                commands.append(args)
                if args[0] == "scp":
                    binary.write_bytes(b"replaced-during-transfer")
                return Mock(returncode=0)

            with (
                patch.object(vm, "HERE", root),
                patch.object(vm, "run", side_effect=local_fake_run),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                vm.stage("client", expected)
                self.assertIn(expected["go-connector"], commands[-1][-1])
                self.assertNotIn(vm.hashlib.sha256(binary.read_bytes()).hexdigest(), commands[-1][-1])
                commands.clear()
                with self.assertRaises(ValueError):
                    vm.stage("client", expected)
                self.assertEqual(commands, [])

    def test_stdin_close_failure_does_not_skip_reap(self):
        proc = Mock()
        proc.stdin.closed = False
        proc.stdin.close.side_effect = BrokenPipeError("private detail")
        proc.poll.side_effect = [None, -9]
        proc.wait.side_effect = [vm.subprocess.TimeoutExpired("ssh", 2), -9]

        def trial():
            vm.processes.append(proc)

        with patch.object(vm, "stage"), patch.object(vm, "test", side_effect=trial):
            result = vm.execute({"artifacts": {}})
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_count, 2)
        self.assertFalse(result["pass"])
        self.assertIn("local_stdin_close:BrokenPipeError", result["errors"])
        self.assertNotIn("private detail", json.dumps(result))

    def test_expired_cleanup_budget_still_attempts_kill(self):
        proc = Mock(stdin=None)
        proc.poll.return_value = None

        def trial():
            vm.processes.append(proc)

        with (
            patch.object(vm, "stage"),
            patch.object(vm, "test", side_effect=trial),
            patch.object(vm, "remaining", side_effect=TimeoutError),
        ):
            result = vm.execute({"artifacts": {}})
        proc.kill.assert_called_once()
        self.assertFalse(result["cleanup_confirmed"])
        self.assertFalse(result["pass"])

    def test_artifact_validation_rejects_tampering(self):
        originals = pinned_sources(REPO)
        patched = overlay(*originals)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("go-connector", "rust-gateway", "request.cbor"):
                (root / name).write_bytes(b"fixture")
            record = {
                "base_sha": vm.BASE,
                "synthetic_authority": True,
                "source_sha256": dict(zip((GO, RUST), map(vm.digest, originals))),
                "overlay_sha256": dict(zip((GO, RUST), map(vm.digest, patched))),
                "artifacts": {name: vm.hashlib.sha256(b"fixture").hexdigest() for name in ("go-connector", "rust-gateway", "request.cbor")},
            }
            (root / "manifest.json").write_text(json.dumps(record))
            with (
                patch.object(vm, "pinned_sources", return_value=originals),
                patch.object(vm.subprocess, "check_output", return_value=b"fixture"),
            ):
                self.assertEqual(vm.check_artifacts(REPO, root), record)
                record["private"] = "DO_NOT_LOG"
                (root / "manifest.json").write_text(json.dumps(record))
                self.assertNotIn("DO_NOT_LOG", json.dumps(vm.check_artifacts(REPO, root)))
                (root / "go-connector").write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    vm.check_artifacts(REPO, root)
                (root / "go-connector").write_bytes(b"fixture")
                record["base_sha"] = "old-sha"
                (root / "manifest.json").write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    vm.check_artifacts(REPO, root)

    def test_default_cli_is_local_only(self):
        with (
            patch("sys.argv", ["vm_pair.py", "--repo", str(REPO), "--artifacts", "unused"]),
            patch.object(vm, "check_artifacts", return_value={}),
            patch.object(vm, "execute") as execute,
            patch.object(vm.subprocess, "Popen") as popen,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            vm.main()
        execute.assert_not_called()
        popen.assert_not_called()

    def test_prepare_writes_only_new_local_overlay_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "overlay"
            with (
                patch("sys.argv", ["vm_pair.py", "--repo", str(REPO), "--prepare", str(destination)]),
                patch.object(vm, "execute") as execute,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                vm.main()
                self.assertEqual((destination / GO).read_text(), overlay(*pinned_sources(REPO))[0])
                self.assertEqual((destination / RUST).read_text(), overlay(*pinned_sources(REPO))[1])
                with self.assertRaises(FileExistsError):
                    vm.main()
            execute.assert_not_called()

    def test_positive_flow_uses_exact_test_and_redacts_private_handoff(self):
        def output(lines):
            q = queue.Queue()
            q.overflow = threading.Event()
            for line in lines:
                q.put(line)
            q.put(None)
            return q

        client = Mock(stdin=io.BytesIO())
        server = Mock(stdin=io.BytesIO())
        client.wait.return_value = server.wait.return_value = 0
        cq = output([b"CLIENT_READY", b"loopback_socket_released=10.77.0.2:4567"])
        sq = output(
            [
                b'SPHERE_HANDOFF {"Case":"positive","Endpoint":"10.77.0.1:1234","Key":"PRIVATE"}',
                b"SPHERE_PEER 10.77.0.2:4567 -> 10.77.0.1:1234",
                b"SPHERE_GATEWAY_CLEANUP gateway_socket_released=true owner_count=0",
                b"SPHERE_CONNECTOR_PASS synthetic_authority=true",
                b"test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 1.00s",
            ]
        )
        with (
            patch.object(vm, "start", side_effect=[(client, cq), (server, sq)]) as start,
            patch.object(vm, "remaining", return_value=30),
            patch.object(vm, "EVENTS", []),
            contextlib.redirect_stdout(io.StringIO()) as printed,
        ):
            vm.test()
            self.assertIn("--exact isolated_go_rust_control_registration", start.call_args.args[1])
            self.assertNotIn("PRIVATE", printed.getvalue())
            self.assertNotIn("10.77.", printed.getvalue())
            self.assertIn("one_test_passed", vm.EVENTS)


if __name__ == "__main__":
    unittest.main()
