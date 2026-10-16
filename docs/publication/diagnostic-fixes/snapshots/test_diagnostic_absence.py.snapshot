import unittest
from diagnostic_absence import absence_confirmed
TARGET='nbsr-47d2ae4-public-diagnostic-02'
class Absence(unittest.TestCase):
    def check(self,stderr,**kw):
        args=dict(code=1,stdout='',stderr=stderr,target=TARGET,completed=True,handles_released=True);args.update(kw)
        return absence_confirmed(**args)
    def test_observed_lowercase(self):
        self.assertTrue(self.check('error: no such object: '+TARGET+'\n'))
    def test_observed_daemon_form(self):
        self.assertTrue(self.check('Error response from daemon: No such container: '+TARGET+'\n'))
    def test_wrong_target(self):
        self.assertFalse(self.check('Error: No such object: another-container'))
    def test_extra_error_lines(self):
        self.assertFalse(self.check('Error: No such object: '+TARGET+'\npermission denied'))
    def test_incomplete_or_owned_command(self):
        for kw in [dict(completed=False),dict(handles_released=False),dict(code=0),dict(code=2),dict(stdout='unexpected'),dict(code=True)]:
            with self.subTest(kw=kw):self.assertFalse(self.check('Error: No such object: '+TARGET,**kw))
    def test_other_failures(self):
        for err in ['permission denied','daemon unavailable','template parsing error','', 'No such object']:
            with self.subTest(err=err):self.assertFalse(self.check(err))
if __name__=='__main__':unittest.main()
