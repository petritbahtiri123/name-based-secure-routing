import pathlib,tempfile,unittest,os
from unittest.mock import patch
from accounting import snapshot

class AccountingTests(unittest.TestCase):
    def test_fresh_totals_match_legacy_and_detect_growth(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            root=pathlib.Path(d);a=root/'bundle';a.mkdir();out=a/'output';out.mkdir()
            (root/'plain').write_bytes(b'123');(a/'x').write_bytes(b'12345');(out/'y').write_bytes(b'1234567')
            self.assertEqual(snapshot(root,{'bundle':[a],'output':[out]}),{'task':15,'bundle':12,'output':7})
            (out/'y').write_bytes(b'123456789')
            self.assertEqual(snapshot(root,{'bundle':[a],'output':[out]}),{'task':17,'bundle':14,'output':9})
    def test_each_directory_enumerated_once_including_nested_output(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            root=pathlib.Path(d);a=root/'bundle';a.mkdir();out=a/'output';out.mkdir();(out/'x').write_bytes(b'x')
            original=os.scandir;seen=[]
            def scan(path):seen.append(os.path.normcase(os.path.abspath(path)));return original(path)
            with patch('os.scandir',side_effect=scan):
                self.assertEqual(snapshot(root,{'bundle':[a],'output':[out]})['task'],1)
            self.assertEqual(len(seen),len(set(seen)))
    def test_unreadable_directory_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d,patch('os.scandir',side_effect=PermissionError('test')):
            with self.assertRaises(PermissionError):snapshot(pathlib.Path(d),{})
    def test_outside_group_rejected(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            with self.assertRaises(ValueError):snapshot(pathlib.Path(d),{'bad':[pathlib.Path(d).parent]})
    def test_file_links_count_but_directory_links_are_not_traversed(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as d:
            root=pathlib.Path(d);sub=root/'sub';sub.mkdir();file=sub/'data';file.write_bytes(b'123')
            try:
                (root/'file-link').symlink_to(file)
                (root/'dir-link').symlink_to(sub,target_is_directory=True)
            except OSError as e:self.skipTest(str(e))
            self.assertEqual(snapshot(root,{}),{'task':6})
if __name__=='__main__':unittest.main(verbosity=2)
