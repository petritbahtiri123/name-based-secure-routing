import sys,pathlib,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]))
from scripts.performance.windows_native_management import WindowsOwner
from scripts.performance.linux_native_watchdog import supervise
from draining_owner import DrainingOwner
class Clock:
 def __init__(self):self.t=0.
 def __call__(self):return self.t
 def sleep(self,t):self.t+=t
class Backend:
 def __init__(self,clock,child_until=.2,fail=False):self.clock=clock;self.until=child_until;self.fail=fail;self.terminated=False;self.closed=[]
 def create_job(self):return 10
 def create_suspended(self,a):return 20,21
 def assign(self,j,p):pass
 def resume(self,t):pass
 def observe(self,j,p,a):
  if self.fail and not self.terminated:raise OSError('accounting failure')
  return 0,int(not self.terminated and self.clock()<self.until)
 def member_pids(self,j):return [123] if self.clock()<self.until else []
 def terminate(self,j,p,a):self.terminated=True
 def close(self,h):self.closed.append(h)
def run(child_until=.2,fail=False,remaining=120):
 c=Clock();b=Backend(c,child_until,fail)
 args=dict(backend=b,cancel=lambda:None)
 owner=(DrainingOwner(['C:/python.exe'],deadline=remaining,clock=c,**args) if DrainingOwner else WindowsOwner(['C:/python.exe'],**args))
 r=supervise(owner,clock=c,sleep=c.sleep,started_at=0)
 return r,owner,b,c
class Tests(unittest.TestCase):
 def test_child_exits_within_grace_passes_only_after_empty(self):
  r,o,b,c=run();self.assertEqual(r['status'],'LOCAL_WORKER_COMPLETED');self.assertGreaterEqual(c(),.2);self.assertFalse(o.owned);self.assertFalse(b.terminated)
 def test_parent_exit_with_no_children_passes_immediately(self):
  r,o,b,c=run(0);self.assertEqual(r['status'],'LOCAL_WORKER_COMPLETED');self.assertEqual(c(),0);self.assertFalse(o.owned)
 def test_stuck_child_killed_at_small_grace_and_still_fails(self):
  r,o,b,c=run(100);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertTrue(b.terminated);self.assertLess(c(),2.2);self.assertFalse(o.owned)
 def test_accounting_failure_kills_owned_job_and_fails(self):
  r,o,b,c=run(100,True);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertTrue(b.terminated);self.assertLess(c(),2.2);self.assertFalse(o.owned)
 def test_grace_is_capped_by_original_deadline(self):
  r,o,b,c=run(100,remaining=.1);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertLess(c(),.3);self.assertFalse(o.owned)
 def test_pid_query_failure_is_not_treated_as_empty(self):
  c=Clock();b=Backend(c,100)
  def fail(j):raise OSError('PID query')
  b.member_pids=fail;o=DrainingOwner(['C:/python.exe'],backend=b,cancel=lambda:None,deadline=120,clock=c)
  r=supervise(o,clock=c,sleep=c.sleep);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertTrue(b.terminated);self.assertFalse(o.owned)
 def test_never_empty_job_retains_handles_and_fails_at_original_timeout(self):
  c=Clock();b=Backend(c,1000);b.terminate=lambda *a:None
  o=DrainingOwner(['C:/python.exe'],backend=b,cancel=lambda:None,deadline=120,clock=c)
  r=supervise(o,clock=c,sleep=c.sleep);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertTrue(o.owned);self.assertLessEqual(c(),120.05)
 def test_nonzero_parent_never_receives_successful_drain(self):
  c=Clock();b=Backend(c,.2);orig=b.observe;b.observe=lambda *a:(7,orig(*a)[1])
  o=DrainingOwner(['C:/python.exe'],backend=b,cancel=lambda:None,deadline=120,clock=c)
  r=supervise(o,clock=c,sleep=c.sleep);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertEqual(r['exit_code'],7);self.assertFalse(o.drain_events)
 def test_clock_reversal_fails(self):
  c=Clock();b=Backend(c,100);o=DrainingOwner(['C:/python.exe'],backend=b,cancel=lambda:None,deadline=120,clock=c);o.start();o.observe();c.t=-1
  with self.assertRaises(RuntimeError):o.observe()
  self.assertTrue(b.terminated)
 def test_termination_failure_is_retained_and_never_passes(self):
  c=Clock();b=Backend(c,1000)
  def fail(*a):raise OSError('terminate failed')
  b.terminate=fail;o=DrainingOwner(['C:/python.exe'],backend=b,cancel=lambda:None,deadline=120,clock=c)
  r=supervise(o,clock=c,sleep=c.sleep);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertTrue(o.owned)
  self.assertTrue(any(x['event']=='termination_failed' for x in o.drain_events))
 def test_cancellation_remains_failure_even_when_child_exits(self):
  c=Clock();b=Backend(c,.2);o=DrainingOwner(['C:/python.exe'],backend=b,cancel=lambda:None,deadline=120,clock=c)
  def check():
   if c()>=.1:raise InterruptedError('cancel')
  r=supervise(o,clock=c,sleep=c.sleep,check_cancelled=check);self.assertEqual(r['status'],'INVALID_PARTIAL');self.assertEqual(r['reason'],'cancel');self.assertFalse(o.owned)
if __name__=='__main__':unittest.main(verbosity=2)
