import unittest,pathlib,sys

sys.path.insert(0,str(pathlib.Path(__file__).parent))

import bounded,plan,make_commands

class TlsContract(unittest.TestCase):

 def test_authority_not_logout_ipc(self):

  for r,c in plan.config().items():

   if r in plan.HOSTS:self.assertTrue(c['authority'].startswith('/run/'))

 def test_expiry_owned_by_system_not_login_manager(self):

  for r in plan.HOSTS:

   import shlex

   c=shlex.join(make_commands.commands()['exact_tls_lifetime_administration'][r])

   self.assertIn('sudo -i -- /usr/bin/systemd-run --system',c)

   self.assertIn('--uid=1001',c);self.assertNotIn('--user',c)

   self.assertIn('RuntimeDirectoryPreserve=no',c);self.assertIn('RuntimeDirectoryMode=0700',c)

   self.assertIn('Restart=no',c);self.assertIn('RuntimeMaxSec=300',c)

   self.assertNotIn('--wait',c);self.assertNotIn('--pipe',c)

 def test_fresh_output_preserves_run04(self):

  for r in plan.HOSTS:self.assertEqual(plan.config()[r]['output'],plan.ROOT+'/evidence/run07/'+r)

if __name__=='__main__':unittest.main()
