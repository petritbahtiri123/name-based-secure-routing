import hashlib,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
HERE=Path(__file__).resolve().parent
class Metadata(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=HERE);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  (self.root/'src').mkdir();self.file=self.root/'src/a.py';self.file.write_bytes(b'public source')
  self.pins={'src/a.py':hashlib.sha256(b'public source').hexdigest()};self.calls=[]
  from dirty_source_metadata import dirty_metadata,require_clean_status
  self.ns=dict(dirty_metadata=dirty_metadata,require_clean_status=require_clean_status)
 def git(self,argv,**kw):
  self.calls.append((argv,kw));self.assertEqual(kw['timeout'],3);self.assertEqual(argv[-2:],['--','src/a.py'])
  if 'ls-files' in argv:return b'100644 '+b'a'*40+b' 0\tsrc/a.py\0'
  self.assertIn('--raw',argv);self.assertIn('--no-ext-diff',argv);self.assertIn('--no-textconv',argv)
  return b':100644 100755 '+b'a'*40+b' '+b'0'*40+b' M\0src/a.py\0'
 def run_metadata(self,git=None):
  with patch.object(subprocess,'check_output',side_effect=git or self.git):return self.ns['dirty_metadata'](self.root,self.pins,Path.read_bytes,{'PATH':'/usr/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
 def test_mode_only_evidence_keeps_hash(self):
  original=Path.lstat
  def st(path,*a,**kw):
   v=original(path,*a,**kw)
   return types.SimpleNamespace(st_mode=0o100755,st_size=v.st_size) if path==self.file else v
  with patch.object(Path,'lstat',st):r=self.run_metadata()
  row=r['files'][0];self.assertTrue(row['bytes_match']);self.assertEqual(row['index_mode'],'100644');self.assertEqual(row['git_worktree_mode'],'100755');self.assertEqual(r['errors'],[])
 def test_changed_bytes_are_visible_and_still_rejected(self):
  self.file.write_bytes(b'changed');r=self.run_metadata();self.assertFalse(r['files'][0]['bytes_match'])
  with self.assertRaisesRegex(AssertionError,'working tree not clean'):self.ns['require_clean_status'](b' M src/a.py',r)
 def test_parent_alias_rejected_before_git_or_read(self):
  original=Path.is_symlink
  with patch.object(Path,'is_symlink',lambda p:p==self.root/'src' or original(p)):
   with self.assertRaises(AssertionError):self.run_metadata()
  self.assertEqual(self.calls,[])
 def test_secret_path_rejected_before_read(self):
  self.pins={'private/key.pem':'0'*64}
  with self.assertRaises(AssertionError):self.run_metadata()
  self.assertEqual(self.calls,[])
 def test_unexpected_git_path_not_exposed(self):
  def bad(argv,**kw):return b'100644 '+b'a'*40+b' 0\tprivate/key.pem\0'
  r=self.run_metadata(bad);self.assertEqual(len(r['errors']),2);self.assertNotIn('private/key.pem',json.dumps(r))
 def test_git_timeout_still_reports_pinned_hash(self):
  def timeout(argv,**kw):raise subprocess.TimeoutExpired(argv,3)
  r=self.run_metadata(timeout);self.assertEqual(len(r['errors']),2);self.assertTrue(r['files'][0]['bytes_match'])
 def test_unknown_status_paths_never_exposed(self):
  with self.assertRaises(AssertionError) as e:self.ns['require_clean_status'](b'?? private/key.pem')
  self.assertNotIn('private/key.pem',str(e.exception));self.assertIn('sha256',str(e.exception))
 def test_clean_status_is_accepted(self):
  self.ns['require_clean_status'](b'')

if __name__=='__main__':unittest.main()
