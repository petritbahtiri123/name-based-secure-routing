import unittest, pathlib, sys, json, copy, subprocess

from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).parent))

import plan, remote_ops



class SystemRevisionTests(unittest.TestCase):

    def test_system_manager_never_root_workload(self):

        a=plan.service('source',['true'],smoke=True)

        self.assertEqual(a[:4],['sudo','-i','--','/usr/bin/systemd-run'])

        for x in ['--system','--uid=1001','--gid=1001','--property=PrivateUsers=yes','--property=PrivateMounts=yes','--property=NoNewPrivileges=yes','--property=CapabilityBoundingSet=','--property=AmbientCapabilities=']:

            self.assertIn(x,a)

        self.assertNotIn('--user',a)

    def test_new_unit_does_not_reuse_failed_unit(self):

        self.assertEqual(plan.UNIT['source'],'nbsr-sphere-20261016-07-source')

        self.assertEqual(plan.ROOT,'/home/benchmark-user/nbsr-sphere-20261016-01')

    def test_preventive_mounts_remain(self):

        a=plan.service('destination',['true'])

        for suffix in [':/input','/vectors:/vectors','']:

            self.assertIn('--property=BindReadOnlyPaths='+plan.ROOT+'/repo'+suffix,a)

        for x in ['MemoryMax=536870912','MemorySwapMax=0','TasksMax=128','CPUQuota=100%','RuntimeMaxSec=65','TimeoutStopSec=5','KillMode=control-group','SendSIGKILL=yes']:

            self.assertIn('--property='+x,a)

    def test_external_cleanup_targets_system_manager(self):

        # Regression: the old finalizer uses --user and /user.slice, so it cannot stop the new endpoint.

        import inspect

        self.assertIn("system_stop(role,deadline=deadline)",inspect.getsource(remote_ops.finalize))

        self.assertNotIn("group.startswith('/user.slice/')",inspect.getsource(remote_ops.finalize))

    def test_security_snapshot_validator_exists(self):

        self.assertTrue(callable(getattr(remote_ops,'validate_security_snapshot',None)))



    def snapshot(self):

        return dict(uid=1001,gid=1001,cgroup='/system.slice/nbsr-sphere-20261016-07-source-smoke.service',

                    status=dict(NoNewPrivs='1',CapInh='0',CapPrm='0',CapEff='0',CapBnd='0',CapAmb='0'),

                    namespaces=dict(mnt='mnt:[2]',user='user:[2]'),host_namespaces=dict(mnt='mnt:[1]',user='user:[1]'))

    def test_valid_nonroot_private_snapshot(self):

        row=self.snapshot();self.assertEqual(remote_ops.validate_security_snapshot(row,'source',True),row)

    def test_root_wrong_group_and_wrong_cgroup_rejected(self):

        for key,value in [('uid',0),('gid',0),('cgroup','/user.slice/nbsr-sphere-20261016-07-source-smoke.service'),('cgroup','/system.slice/other.service')]:

            with self.subTest(key=key,value=value):

                row=self.snapshot();row[key]=value

                with self.assertRaises(ValueError):remote_ops.validate_security_snapshot(row,'source',True)

    def test_any_capability_or_nnp_failure_rejected(self):

        for key in ['NoNewPrivs','CapInh','CapPrm','CapEff','CapBnd','CapAmb']:

            with self.subTest(key=key):

                row=self.snapshot();row['status'][key]='0' if key=='NoNewPrivs' else '0000000000200000'

                with self.assertRaises(ValueError):remote_ops.validate_security_snapshot(row,'source',True)

    def test_namespace_fallback_rejected(self):

        for n in ['mnt','user']:

            row=self.snapshot();row['namespaces'][n]=row['host_namespaces'][n]

            with self.assertRaises(ValueError):remote_ops.validate_security_snapshot(row,'source',True)

    def test_stop_uses_exact_system_unit_and_propagates_failure(self):

        with patch.object(remote_ops.subprocess,'run') as run:

            remote_ops.system_stop('source')

            self.assertEqual(run.call_args.args[0],['sudo','-i','--','/usr/bin/systemctl','--system','stop','nbsr-sphere-20261016-07-source.service'])

            run.side_effect=subprocess.CalledProcessError(1,['sudo'])

            with self.assertRaises(subprocess.CalledProcessError):remote_ops.system_stop('source')

        with self.assertRaises(ValueError):remote_ops.system_stop('other')

    def test_absence_rejects_active_wrong_identity_and_cgroup(self):

        base={'Id':plan.UNIT['source']+'.service','LoadState':'loaded','ActiveState':'inactive','ControlGroup':''}

        for key,value in [('Id','other.service'),('ActiveState','active'),('ControlGroup','/system.slice/left.service')]:

            row={**base,key:value};result=subprocess.CompletedProcess([],0,'\n'.join(k+'='+v for k,v in row.items()),'')

            with patch.object(remote_ops.subprocess,'run',return_value=result):

                with self.assertRaises(ValueError):remote_ops.verify_system_absence('source')

    def test_absence_requires_filesystem_cgroup_gone(self):

        row={'Id':plan.UNIT['source']+'.service','LoadState':'not-found','ActiveState':'inactive','ControlGroup':''}

        result=subprocess.CompletedProcess([],0,'\n'.join(k+'='+v for k,v in row.items()),'')

        with patch.object(remote_ops.subprocess,'run',return_value=result),patch.object(pathlib.Path,'exists',return_value=True):

            with self.assertRaises(ValueError):remote_ops.verify_system_absence('source')

    def test_cleanup_failure_retains_error_and_system_holder_scope(self):

        with patch.object(remote_ops,'verify_system_absence',side_effect=ValueError('live')),patch.object(remote_ops,'system_stop',side_effect=RuntimeError('no auth')),patch.object(remote_ops,'remove_tls'),patch.object(remote_ops,'absence'),patch.object(remote_ops.tls_lifetime,'stop') as stop:

            with self.assertRaises(RuntimeError):remote_ops.finalize('source')

            self.assertEqual(stop.call_args.args,('source',));self.assertIn('deadline',stop.call_args.kwargs)

    def test_no_reaper_stop_after_tls_removal_failure(self):

        with patch.object(remote_ops,'verify_system_absence'),patch.object(remote_ops,'remove_tls',side_effect=ValueError('unexpected')),patch.object(remote_ops,'absence'),patch.object(remote_ops.subprocess,'run') as run:

            with self.assertRaises(RuntimeError):remote_ops.finalize('source')

            run.assert_not_called()

    def test_finalization_deadline_is_not_renewed(self):

        with patch.object(remote_ops.time,'monotonic',return_value=10):

            self.assertEqual(remote_ops.remaining(11,4),1)

            with self.assertRaises(TimeoutError):remote_ops.remaining(10,4)



if __name__=='__main__':unittest.main()
