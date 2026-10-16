import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import plan
class LifetimeTests(unittest.TestCase):
 def validator(self):
  self.assertTrue((pathlib.Path(__file__).parent/'tls_lifetime.py').is_file(),'missing bounded lifetime validation')
  import tls_lifetime;return tls_lifetime
 def fixture(self):
  t=self.validator();r=dict(t.EXPECTED);r.update(Id=t.unit('source'),ActiveState='active',SubState='running',MainPID='123',ActiveEnterTimestampMonotonic='10000000',ControlGroup='/system.slice/'+t.unit('source'),RuntimeDirectory=t.dirname('source'),ExecStart='{ path=/usr/bin/sleep ; argv[]=/usr/bin/sleep 300 ; }');return t,r
 def test_valid_and_expired_lease(self):
  t,r=self.fixture();self.assertEqual(t.validate('source',r,100,120),210)
  with self.assertRaises(ValueError):t.validate('source',r,191,120)
 def test_wrong_unit_uid_directory_and_restart_rejected(self):
  t,r=self.fixture()
  for k,v in [('Id','other.service'),('User','0'),('Group','0'),('RuntimeDirectory','other'),('RuntimeDirectoryPreserve','yes'),('Restart','always'),('ControlGroup','/user.slice/other'),('ActiveState','inactive'),('MainPID','0'),('ExecStart','/bin/other'),('RuntimeMaxUSec','10min'),('CPUQuotaPerSecUSec','infinity')]:
   with self.subTest(k=k):
    x=dict(r);x[k]=v
    with self.assertRaises(ValueError):t.validate('source',x,100,120)
 def test_clock_uncertainty_rejected(self):
  t,r=self.fixture()
  with self.assertRaises(ValueError):t.validate('source',r,9,120)
 def test_cleanup_cannot_renew_deadline(self):
  from unittest.mock import patch
  t=self.validator()
  with patch.object(t.time,'monotonic',return_value=20),patch.object(t.subprocess,'run') as run:
   with self.assertRaises(TimeoutError):t.stop('source',deadline=20)
   run.assert_not_called()
if __name__=='__main__':unittest.main()
