import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from test_draining import Clock,Backend
from scripts.performance.linux_native_watchdog import supervise
from draining_owner import DrainingOwner

class CadenceTests(unittest.TestCase):
    def replay(self,cost,child_after_first_observation=.3,owner_class=DrainingOwner):
        clock=Clock();backend=Backend(clock,100);original=backend.observe;first=[];checks=[]
        def observe(*args):
            if not first:first.append(clock());backend.until=clock()+child_after_first_observation
            return original(*args)
        backend.observe=observe
        def guard():checks.append(clock());clock.t+=cost
        owner=owner_class(['C:/python.exe'],backend=backend,cancel=lambda:None,deadline=5,clock=clock)
        result=supervise(owner,clock=clock,sleep=clock.sleep,guard=guard,started_at=0)
        return result,owner,checks,clock
    def test_slow_guard_reproduces_missed_empty_observation(self):
        class LegacyOwner(DrainingOwner):GRACE_SECONDS=.5
        result,owner,checks,clock=self.replay(.21,owner_class=LegacyOwner)
        self.assertEqual(result['status'],'INVALID_PARTIAL');self.assertEqual(owner.drain_failure,'TimeoutError')
        self.assertFalse(owner.owned);self.assertGreaterEqual(len(checks),4)
    def test_fast_fresh_guard_observes_actual_empty_before_same_deadline(self):
        result,owner,checks,clock=self.replay(.03)
        self.assertEqual(result['status'],'LOCAL_WORKER_COMPLETED');self.assertFalse(owner.owned)
        empty=[x for x in owner.drain_events if x['event']=='empty_observed'];self.assertTrue(empty)
        self.assertLess(empty[0]['monotonic'],owner.drain_until);self.assertGreaterEqual(len(checks),4)
    def test_fast_guard_does_not_pass_child_exceeding_two_seconds(self):
        result,owner,checks,clock=self.replay(.03,3)
        self.assertEqual(result['status'],'INVALID_PARTIAL');self.assertEqual(owner.drain_failure,'TimeoutError')
        self.assertFalse(owner.owned)
if __name__=='__main__':unittest.main(verbosity=2)
