import unittest
from test_draining import run
from draining_owner import DrainingOwner
class ProposedGraceTests(unittest.TestCase):
    def test_one_second_descendant_passes_only_after_observed_empty(self):
        result,owner,backend,clock=run(1)
        self.assertEqual(DrainingOwner.GRACE_SECONDS,2.0)
        self.assertEqual(result['status'],'LOCAL_WORKER_COMPLETED');self.assertGreaterEqual(clock(),1)
        self.assertFalse(backend.terminated);self.assertFalse(owner.owned)
        empty=[x for x in owner.drain_events if x['event']=='empty_observed'];self.assertTrue(empty)
        self.assertLess(empty[0]['monotonic'],owner.drain_until)
    def test_two_second_tolerance_cannot_extend_original_half_second_remainder(self):
        result,owner,backend,clock=run(1,remaining=.5)
        self.assertEqual(result['status'],'INVALID_PARTIAL');self.assertTrue(backend.terminated)
        self.assertFalse(owner.owned);self.assertLess(clock(),.7)
if __name__=='__main__':unittest.main(verbosity=2)
