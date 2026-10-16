"""Run only fake/filesystem regressions; reject unmocked process and network use."""
import pathlib
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))

def forbidden(*args, **kwargs):
    raise AssertionError('offline suite attempted external process or network access')

if __name__ == '__main__':
    with patch.object(subprocess, 'Popen', side_effect=forbidden), patch.object(socket, 'socket', side_effect=forbidden):
        suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
