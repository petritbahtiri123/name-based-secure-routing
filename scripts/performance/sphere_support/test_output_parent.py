import unittest,tempfile,pathlib,sys
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import remote_ops
class OutputParentTests(unittest.TestCase):
 def test_endpoint_parents_false_can_create_under_prepared_parent(self):
  self.assertTrue(callable(getattr(remote_ops,'prepare_output_parent',None)),'fresh endpoint output parent must be prepared')
  with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
   base=pathlib.Path(d);(base/'evidence').mkdir()
   with patch.object(remote_ops,'BASE',base):remote_ops.prepare_output_parent()
   out=base/'evidence/run07/source';out.mkdir(parents=False,exist_ok=False)
   self.assertTrue(out.is_dir())
 def test_existing_parent_is_never_adopted_or_overwritten(self):
  self.assertTrue(callable(getattr(remote_ops,'prepare_output_parent',None)))
  with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
   base=pathlib.Path(d);out=base/'evidence/run07';out.mkdir(parents=True);(out/'old-proof').write_text('keep')
   with patch.object(remote_ops,'BASE',base):
    with self.assertRaises(FileExistsError):remote_ops.prepare_output_parent()
   self.assertEqual((out/'old-proof').read_text(),'keep')
if __name__=='__main__':unittest.main()
