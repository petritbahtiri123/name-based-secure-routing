import unittest,sys,pathlib,copy,subprocess,tempfile,json
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import remote_ops
import mountpoints
class MountpointTests(unittest.TestCase):
    def test_mountpoint_policy_exists(self):
        self.assertTrue(callable(getattr(remote_ops,'validate_mountpoint',None)))
    def test_removal_policy_exists(self):
        self.assertTrue(callable(getattr(remote_ops,'may_remove_mountpoint',None)))
    def safe(self):
        return dict(exists=True,directory=True,uid=0,gid=0,mode=0o755,device=1,inode=3,empty=True,mounted=False)
    def test_absent_and_safe_preexisting_accepted(self):
        mountpoints.validate_mountpoint({'exists':False});mountpoints.validate_mountpoint(self.safe())
    def test_symlink_wrong_owner_writable_populated_mount_rejected(self):
        for key,value in [('directory',False),('uid',1001),('gid',1001),('mode',0o777),('empty',False),('mounted',True)]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):mountpoints.validate_mountpoint({**self.safe(),key:value})
    def test_only_exact_confirmed_created_inode_removable(self):
        row=self.safe();record=dict(state='created',created_by_task=True,identity=row)
        self.assertTrue(mountpoints.may_remove_mountpoint(record,row))
        for other in [dict(state='preexisting',created_by_task=False,identity=row),dict(state='creation_intent',created_by_task=False)]:
            with self.assertRaises(ValueError):mountpoints.may_remove_mountpoint(other,row)
        with self.assertRaises(ValueError):mountpoints.may_remove_mountpoint(record,{**row,'inode':4})
    def test_uncertain_mkdir_never_adopted(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            e=pathlib.Path(d);(e/'host-source.json').write_text(json.dumps({'mountpoints':{n:{'exists':False} for n in mountpoints.PATHS}}))
            with patch.object(mountpoints,'snapshot',return_value={'exists':False}),patch.object(mountpoints.subprocess,'run',side_effect=subprocess.TimeoutExpired('mkdir',4)):
                with self.assertRaises(subprocess.TimeoutExpired):mountpoints.prepare('source',e)
            row=json.loads((e/'mountpoints-source.json').read_text())['records']['/input']
            self.assertEqual(row,{'state':'creation_intent','created_by_task':False})
    def test_preexisting_never_removed(self):
        row=self.safe()
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            e=pathlib.Path(d);(e/'mountpoints-source.json').write_text(json.dumps({'role':'source','records':{n:dict(state='preexisting',created_by_task=False,identity=row) for n in mountpoints.PATHS}}))
            with patch.object(mountpoints,'snapshot',return_value=row),patch.object(mountpoints.subprocess,'run') as run:
                mountpoints.cleanup('source',e,100)
            run.assert_not_called()
    def test_created_removes_exact_empty_path_only(self):
        row=self.safe()
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            e=pathlib.Path(d);(e/'mountpoints-source.json').write_text(json.dumps({'role':'source','records':{n:dict(state='created',created_by_task=True,identity=row) for n in mountpoints.PATHS}}))
            with patch.object(mountpoints,'snapshot',return_value=row),patch.object(mountpoints.os.path,'lexists',return_value=False),patch.object(mountpoints.time,'monotonic',return_value=1),patch.object(mountpoints.subprocess,'run') as run:
                mountpoints.cleanup('source',e,100)
                self.assertEqual([c.args[0] for c in run.call_args_list],[['sudo','-i','--','/usr/bin/rmdir','--',n] for n in mountpoints.PATHS])
            self.assertTrue(all(x['state']=='removed' for x in json.loads((e/'mountpoints-source.json').read_text())['records'].values()))
if __name__=='__main__':unittest.main()
