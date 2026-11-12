"""Offline supervisor contracts; no workloads or external services."""
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import supervision as s


class SupervisionTests(unittest.TestCase):
    def test_short_pipe_output_reaches_disk_before_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            read_fd, write_fd = os.pipe()
            target = Path(tmp) / 'progress.log'
            marker = b'Compiling dependency; process is still running\n'
            reader = threading.Thread(target=s._capture,
                args=(os.fdopen(read_fd, 'rb'), target, [0], threading.Lock(), threading.Event()),
                daemon=True)
            reader.start()
            observed = b''
            try:
                os.write(write_fd, marker)
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline:
                    if target.exists():
                        observed = target.read_bytes()
                    if observed == marker:
                        break
                    time.sleep(0.01)
                self.assertEqual(observed, marker, 'short progress must be retained while writer stays open')
            finally:
                os.close(write_fd)
                reader.join(1)
            self.assertFalse(reader.is_alive())

    def test_rejects_relative_and_nul_argv(self):
        for argv in ([], ['python'], [sys.executable, 'a\0b'], [1]):
            with self.assertRaises(ValueError):
                s._validate(argv, Path.cwd(), {}, 1)

    def test_rejects_unbounded_timeout_and_invalid_environment(self):
        for timeout in (0, 96, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                s._validate([sys.executable], Path.cwd(), {}, timeout)
        with self.assertRaises(ValueError):
            s._validate([sys.executable], Path.cwd(), {'BAD=KEY': 'x'}, 1)

    def test_shared_capture_budget_caps_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget, lock, exceeded = [0], threading.Lock(), threading.Event()
            with patch.object(s, 'OUTPUT_LIMIT', 7):
                s._capture(io.BytesIO(b'12345'), Path(tmp)/'out', budget, lock, exceeded)
                s._capture(io.BytesIO(b'67890'), Path(tmp)/'err', budget, lock, exceeded)
            self.assertEqual((Path(tmp)/'out').read_bytes(), b'12345')
            self.assertEqual((Path(tmp)/'err').read_bytes(), b'67')
            self.assertTrue(exceeded.is_set())

    def test_windows_assign_precedes_resume_and_cleanup_observed(self):
        events = []
        class Backend:
            def create_job(self, name):
                events.append('job'); return 1
            def create_suspended(self, argv):
                events.append('suspended'); return 2, 3
            def assign(self, job, process): events.append('assign')
            def resume(self, thread): events.append('resume')
            def terminate(self, *args): events.append('terminate')
            def observe(self, *args): return 1, 0
            def close(self, handle): events.append('close')
        with tempfile.TemporaryDirectory() as tmp:
            cancel = threading.Event(); cancel.set()
            with patch.object(s, 'IS_WINDOWS', True), patch.object(s, 'Win32Backend', Backend):
                result = s.run_owned([sys.executable], Path.cwd(), {}, Path(tmp)/'run', cancel=cancel)
            self.assertEqual(result['cleanup'], 'CLEAN')
            self.assertEqual(result['reason'], 'cancelled')
            self.assertEqual(events[:4], ['job', 'suspended', 'assign', 'resume'])
            self.assertFalse((Path(tmp)/'run'/'request.json').exists())

    def test_assignment_failure_never_resumes(self):
        events = []
        class Backend:
            def create_job(self, name): return 1
            def create_suspended(self, argv): return 2, 3
            def assign(self, *args): raise OSError('assignment failed')
            def resume(self, *args): self.fail('must not resume')
            def terminate(self, job, process, assigned): events.append(assigned)
            def observe(self, *args): return 1, 0
            def close(self, *args): pass
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(s, 'IS_WINDOWS', True), patch.object(s, 'Win32Backend', Backend):
                result = s.run_owned([sys.executable], Path.cwd(), {}, Path(tmp)/'run')
            self.assertEqual(result['reason'], 'ownership_error')
            self.assertEqual(events, [False])


if __name__ == '__main__':
    unittest.main()
