import unittest
from runtime_preflight import PINS,gate
class Gate(unittest.TestCase):
    def facts(self):return dict(python=[3,14,6],implementation='cpython',platform='linux',machine='x86_64',versions=dict(PINS),git='/usr/bin/git')
    def test_old_python_prevents_imports_and_integrity(self):
        f=self.facts();f['python']=[3,11,9];calls=[]
        with self.assertRaisesRegex(ValueError,'Python outside'):gate(f,lambda:calls.append('import'),lambda:calls.append('integrity'))
        self.assertEqual(calls,[])
    def test_range_boundaries(self):
        for version,valid in [([3,12,0],True),([3,14,6],True),([3,15,0],False)]:
            f=self.facts();f['python']=version
            if valid:self.assertEqual(gate(f,lambda:None,lambda:'checked'),'checked')
            else:
                with self.assertRaises(ValueError):gate(f,lambda:None,lambda:None)
    def test_missing_and_mismatched_pins_fail_before_import(self):
        for name,value in [('cryptography',None),('cffi','2.1.1')]:
            f=self.facts();f['versions'][name]=value;calls=[]
            with self.assertRaisesRegex(ValueError,name):gate(f,lambda:calls.append(1),lambda:calls.append(2))
            self.assertEqual(calls,[])
    def test_native_failure_blocks_integrity(self):
        calls=[]
        def fail():raise ImportError('native library unavailable')
        with self.assertRaises(ImportError):gate(self.facts(),fail,lambda:calls.append(1))
        self.assertEqual(calls,[])
    def test_original_integrity_rejection_preserved(self):
        def fail():raise ValueError('dirty source')
        with self.assertRaisesRegex(ValueError,'dirty source'):gate(self.facts(),lambda:None,fail)
    def test_unknown_requirement_and_platform_git_rejected(self):
        for field,value in [('machine','aarch64'),('git',None),('implementation','pypy')]:
            f=self.facts();f[field]=value
            with self.assertRaises(ValueError):gate(f,lambda:None,lambda:None)
        with self.assertRaisesRegex(ValueError,'unreviewed'):gate(self.facts(),lambda:None,lambda:None,requirement='>=3.11')
if __name__=='__main__':unittest.main()
