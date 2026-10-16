import unittest,tempfile,pathlib,json,hashlib,sys
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import execute_step,plan,make_commands

class ExecutionGateTests(unittest.TestCase):
    def fixture(self,root):
        (root/'bundle-manifest.json').write_text('{"files":{}}')
        (root/'source-inventory.json').write_text('{"files":{}}')
        (root/'external-inputs.json').write_text('[]')
        (root/'approval-status.json').write_text('{"execution_ready":true}')
        (root/'commands.json').write_text(json.dumps({'source':{'capability_smoke':['smoke'],'smoke_absence':['absence'],'verify_mountpoints':['mountcheck']},'trial':['strict.conf']}))
        return hashlib.sha256((root/'bundle-manifest.json').read_bytes()).hexdigest()
    def test_tls_and_trial_require_both_gates(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d,patch.object(execute_step.bounded,'run') as run:
            root=pathlib.Path(d);pin=self.fixture(root)
            with patch.object(execute_step,'HERE',root):
                for step in ['start_key_reaper','public_csr_only','transfer_public_certificates','sign_public_csrs','trial']:
                    with self.subTest(step=step):
                        with self.assertRaises(RuntimeError):execute_step.execute('source',step,pin)
                (root/'source-smoke-PASS.json').write_text('{}')
                with self.assertRaises(RuntimeError):execute_step.execute('source','trial',pin)
            run.assert_not_called()
    def test_no_pass_marker_if_smoke_absence_fails(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            root=pathlib.Path(d);pin=self.fixture(root)
            def run(argv,out,work):
                if argv==['absence']:raise RuntimeError('still active')
                out.mkdir();(out/'stdout.log').write_text('{"status":"PASS_CAPABILITY_ONLY","role":"source"}')
            with patch.object(execute_step,'HERE',root),patch.object(execute_step.bounded,'run',side_effect=run):
                with self.assertRaises(RuntimeError):execute_step.execute('source','capability_smoke',pin)
            self.assertFalse((root/'source-smoke-PASS.json').exists())
    def test_referenced_file_drift_rejected_before_command(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d,patch.object(execute_step.bounded,'run') as run:
            root=pathlib.Path(d);pin=self.fixture(root);p=root/'support';p.write_bytes(b'x')
            (root/'external-inputs.json').write_text(json.dumps([{'path':str(p),'bytes':1,'sha256':'0'*64}]))
            with patch.object(execute_step,'HERE',root):
                with self.assertRaises(ValueError):execute_step.execute('source','capability_smoke',pin)
            run.assert_not_called()
    def test_commands_have_no_source_reinstall_and_exact_trials(self):
        c=make_commands.commands()
        self.assertNotIn('install',c['source']);self.assertNotIn('setup',c['source'])
        for n in ['create_fresh_root','transfer_existing_zip','transfer_public_support','setup','install']:self.assertIn(n,c['destination'])
        for r in plan.HOSTS:
            a=c['exact_trial_endpoints'][r][-1]
            self.assertIn('sudo -i -- /usr/bin/systemd-run --system',a)
            self.assertIn('--role '+r,a)
            self.assertIn(plan.CONTROL+'/peer_guard.py',a)
            self.assertIn('--unit='+plan.UNIT[r],a)
    def test_blocked_review_cannot_execute_any_step(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d,patch.object(execute_step.bounded,'run') as run:
            root=pathlib.Path(d);pin=self.fixture(root)
            (root/'approval-status.json').write_text('{"execution_ready":false}')
            with patch.object(execute_step,'HERE',root):
                for step in ['capability_smoke','create_fresh_root','trial']:
                    with self.assertRaisesRegex(RuntimeError,'BLOCKED'):execute_step.execute('source',step,pin)
            run.assert_not_called()

    def test_public_hash_mismatch_blocks_coordinator(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            root=pathlib.Path(d);pin=self.fixture(root)
            (root/'commands.json').write_text(json.dumps({r:{'verify_mountpoints':['mount'],'verify_tls':['tls']} for r in plan.HOSTS}|{'trial':['strict.conf']}))
            cert=root/'tls-public/certificates';cert.mkdir(parents=True)
            (cert/'public-hashes.json').write_text(json.dumps({'ca.der':'expected','source.der':'expected','destination.der':'expected'}))
            for r in plan.HOSTS:
                (root/(r+'-smoke-PASS.json')).write_text('{}')
                out=root/('step-'+r+'-transfer_public_certificates');out.mkdir()
                (out/'supervision.json').write_text(json.dumps({'status':'LOCAL_WORKER_COMPLETED','owned_handles':False}))
            calls=[]
            def run(argv,out,work):
                calls.append(argv);out.mkdir()
                if argv==['tls']:(out/'stdout.log').write_text(json.dumps({'public_hashes':{'ca.der':'wrong','source.der':'expected'}}))
            with patch.object(execute_step,'HERE',root),patch.object(execute_step.bounded,'run',side_effect=run):
                with self.assertRaisesRegex(ValueError,'public certificate receipt mismatch'):execute_step.execute('local','trial',pin)
            self.assertEqual(calls,[['mount'],['tls']])

if __name__=='__main__':unittest.main()
