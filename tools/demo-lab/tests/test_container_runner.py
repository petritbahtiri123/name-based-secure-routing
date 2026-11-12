"""Fake Docker contracts. These tests never invoke an engine."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import container_runner as c

RUN = 'demo-' + 'a' * 32
IMAGE = 'sha256:' + 'b' * 64
CID = 'c' * 64


class ContainerTests(unittest.TestCase):
    def test_rosetta_is_not_native_acceptance(self):
        with patch.object(c, '_rosetta_status', return_value=1), patch.object(c.platform, 'machine', return_value='x86_64'):
            with self.assertRaisesRegex(ValueError, 'Rosetta'):
                c.native_architecture()
        for machine, expected in [('arm64', 'arm64'), ('x86_64', 'amd64')]:
            with patch.object(c, '_rosetta_status', return_value=0), patch.object(c.platform, 'machine', return_value=machine):
                self.assertEqual(c.native_architecture(), expected)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('source', 'artifacts', 'logs'):
            (self.root/name).mkdir()
        self.spec = dict(run_id=RUN, image_id=IMAGE, architecture='arm64',
                         mounts={k: str(self.root/k) for k in ('source', 'artifacts')},
                         command=['allowed_service_a'], logdir=str(self.root/'logs'))
        self.calls = []

    def fake(self, args):
        self.calls.append(args)
        if args[:2] == ['image', 'inspect']:
            return 0, json.dumps([dict(Id=IMAGE, Os='linux', Architecture='arm64')])
        if args[0] == 'create':
            return 0, CID
        if args[:2] == ['container', 'inspect']:
            return 0, json.dumps([dict(Id=CID, Image=IMAGE,
                Config={'Labels': {c.OWNER: RUN}}, State={'Running': False, 'ExitCode': 0})])
        return 0, ''

    def test_remote_docker_configuration_rejected(self):
        for environment in ({'DOCKER_HOST': 'tcp://remote:2375'},
                            {'DOCKER_HOST': 'ssh://remote'},
                            {'DOCKER_CONTEXT': 'production'}):
            with self.assertRaises(ValueError):
                c.local_docker_host(environment)
        with patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFSOCK)):
            self.assertTrue(c.local_docker_host({}).startswith('unix://'))

    def test_nonroot_uid_and_owned_tmpfs(self):
        args = c.create_args(IMAGE, RUN, self.spec['mounts'], ['allowed_service_a'], 'arm64', 501, 20)
        self.assertIn('--user=501:20', args)
        self.assertIn('--env=NBSR_DEMO_RUN_ID=' + RUN, args)
        self.assertIn('--env=NBSR_DEMO_CONTAINER=1', args)
        self.assertTrue(any('/opt/nbsr-build/nbsr-demo/' + RUN in a and 'uid=501,gid=20,mode=700' in a for a in args))
        with self.assertRaises(ValueError):
            c.create_args(IMAGE, RUN, self.spec['mounts'], ['allowed_service_a'], 'arm64', 0, 20)

    def test_fixed_security_policy(self):
        args = c.create_args(IMAGE, RUN, self.spec['mounts'], ['allowed_service_a'], 'arm64')
        for flag in ('--pull=never', '--network=none', '--read-only', '--cap-drop=ALL',
                     '--security-opt=no-new-privileges', '--pids-limit=128', '--memory=1g',
                     '--cpus=2', '--platform=linux/arm64', '--user=65532:65532'):
            self.assertIn(flag, args)
        with self.assertRaises(ValueError):
            c.create_args(IMAGE, RUN, self.spec['mounts'], ['sh', '-c', 'x'], 'arm64')
        with self.assertRaises(ValueError):
            c.create_args('latest', RUN, self.spec['mounts'], ['allowed_service_a'], 'arm64')

    def test_success_requires_remove_and_absence_observation(self):
        result = c.lifecycle(self.spec, self.fake)
        self.assertEqual(result['cleanup'], 'CLEAN')
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual((self.root/'logs/container-id').read_text(), CID)
        self.assertIn(['container', 'rm', CID], self.calls)
        self.assertEqual(self.calls[-1][:2], ['container', 'ls'])

    def test_identity_mismatch_never_mutates_container(self):
        def fake(args):
            code, raw = self.fake(args)
            if args[:2] == ['container', 'inspect']:
                raw = raw.replace(IMAGE, 'sha256:' + 'd'*64)
            return code, raw
        result = c.lifecycle(self.spec, fake)
        self.assertEqual(result['cleanup'], 'UNCONFIRMED')
        self.assertFalse(any(a[:2] in (['container', 'kill'], ['container', 'rm'],
                                      ['container', 'start']) for a in self.calls))

    def test_remove_failure_is_unconfirmed(self):
        def fake(args):
            if args[:2] == ['container', 'rm']:
                return 1, ''
            return self.fake(args)
        self.assertEqual(c.lifecycle(self.spec, fake)['cleanup'], 'UNCONFIRMED')

    def test_cancel_kills_only_exact_owned_id(self):
        (self.root/'logs/cancel').touch()
        killed = [False]
        def fake(args):
            if args[:2] == ['container', 'kill']:
                killed[0] = True
            code, raw = self.fake(args)
            if args[:2] == ['container', 'inspect'] and not killed[0]:
                raw = raw.replace('"Running": false', '"Running": true')
            return code, raw
        result = c.lifecycle(self.spec, fake)
        self.assertEqual(result['reason'], 'cancelled')
        self.assertEqual(result['cleanup'], 'CLEAN')
        self.assertIn(['container', 'kill', '--signal=KILL', CID], self.calls)

    def test_work_deadline_kills_owned_container(self):
        now = [0]
        killed = [False]
        def clock():
            return now[0]
        def sleep(_):
            now[0] = 71
        def fake(args):
            if args[:2] == ['container', 'kill']:
                killed[0] = True
            code, raw = self.fake(args)
            if args[:2] == ['container', 'inspect'] and not killed[0]:
                raw = raw.replace('"Running": false', '"Running": true')
            return code, raw
        result = c.lifecycle(self.spec, fake, clock=clock, sleep=sleep)
        self.assertEqual(result['reason'], 'timeout')
        self.assertEqual(result['cleanup'], 'CLEAN')
        self.assertTrue(killed[0])

    def test_lost_create_response_recovers_exact_name_then_validates(self):
        def fake(args):
            if args[0] == 'create':
                return 1, ''
            return self.fake(args)
        result = c.lifecycle(self.spec, fake)
        self.assertEqual(result['cleanup'], 'CLEAN')
        self.assertEqual(result['reason'], 'launch_error')
        self.assertIn(['container', 'inspect', RUN], self.calls)


if __name__ == '__main__':
    unittest.main()
