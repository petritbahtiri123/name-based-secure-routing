from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from sched_observe import read_task

class TaskStats(unittest.TestCase):
    def test_counters_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            fields=['S']+['0']*49
            fields[19]='99'
            (p/'stat').write_text('123 (worker (a)) '+' '.join(fields))
            (p/'schedstat').write_text('1000 250 8\n')
            self.assertEqual(read_task(p),dict(tid=123,start_ticks=99,runtime_ns=1000,runqueue_ns=250,timeslices=8))
    def test_bad_counters_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            fields=['S']+['0']*49; fields[19]='99'
            (p/'stat').write_text('123 (worker) '+' '.join(fields))
            for value in ('1 2','1 -2 3','1 2 3 4','one 2 3'):
                (p/'schedstat').write_text(value)
                with self.assertRaises(ValueError): read_task(p)
    def test_reused_identity_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            fields=['S']+['0']*49; fields[19]='99'
            original='123 (worker) '+' '.join(fields)
            (p/'stat').write_text(original)
            (p/'schedstat').write_text('1000 250 8')
            read=Path.read_text
            def changing(path, *args, **kwargs):
                value=read(path,*args,**kwargs)
                if path.name=='schedstat':
                    fields[19]='100'
                    (p/'stat').write_text('123 (worker) '+' '.join(fields))
                return value
            with patch.object(Path,'read_text',changing):
                with self.assertRaisesRegex(ValueError,'identity changed'): read_task(p)
if __name__=='__main__': unittest.main()
