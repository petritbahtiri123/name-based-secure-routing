import importlib
import struct
import subprocess
import sys

import pytest


def module():
    return importlib.import_module("scripts.performance.handshake_timeline")


def test_bounded_allocation_and_parent_retains_child_bytes():
    m = module()
    with pytest.raises(ValueError):
        m.Timeline(1025, 1)
    with m.Timeline(2, 1) as owner:
        script = "import mmap,sys,struct; m=mmap.mmap(-1,int(sys.argv[2]),tagname=sys.argv[1]); struct.pack_into('<Q',m,64,123); m.close()"
        subprocess.run([sys.executable,"-c",script,owner.name,str(owner.size)],check=True)
        assert struct.unpack_from("<Q",owner.mapping,64)[0] == 123
        assert struct.unpack_from("<Q",owner.mapping,64+256)[0] == 0
    assert owner.closed
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenFileMappingW.restype=ctypes.c_void_p
    kernel.OpenFileMappingW.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_wchar_p]
    assert not kernel.OpenFileMappingW(4,False,owner.name)


def test_corrupt_or_incomplete_records_rejected():
    m = module()
    with m.Timeline(1, 1) as owner:
        with pytest.raises(ValueError):
            owner.snapshot()
        owner.mapping[0:8] = b"corrupt!"
        with pytest.raises(ValueError):
            owner.snapshot()


def test_complete_failure_preserved_and_order_checked():
    m = module()
    with m.Timeline(1, 1) as owner:
        words = [0]*32
        words[0:3] = [100,101,102]
        words[9] = 105
        words[11] = 106
        words[13] = 1
        words[20] = 1
        words[31] = m.GUARD
        owner.mapping[64:320] = struct.pack('<32Q',*words)
        result = owner.snapshot()
        assert result['records'][0]['events']['timed_out'] == 105
        assert result['records'][0]['events']['connected'] is None
        words[1] = 99
        owner.mapping[64:320] = struct.pack('<32Q',*words)
        with pytest.raises(ValueError):
            owner.snapshot()


def test_timeline_failure_invalidates_otherwise_complete_measurement():
    from scripts.run_b4b_v2 import valid_record
    record=dict(successful_admissions=1,failed_admissions=0,
        established_goodput_bytes_per_second=1,established_p99_latency_ns=1,
        admission_elapsed_seconds=1,resources={},cleanup={'processes_exited':True},
        timeline_capture={'valid':False})
    assert not valid_record(record)


def test_child_cannot_complete_another_slot_or_duplicate_stage():
    m=module()
    with m.Timeline(2,1) as owner:
        words=[0]*32
        words[:2]=[100,101]
        words[9]=102
        words[11]=103
        words[13]=words[20]=1
        words[31]=m.GUARD
        owner.mapping[64:320]=struct.pack('<32Q',*words)
        with pytest.raises(ValueError,match='slot 1'):
            owner.snapshot()
        owner.mapping[320:576]=struct.pack('<32Q',*words)
        assert len(owner.snapshot()['records'])==2
        words[12]=1  # Writer's sticky duplicate/overflow flag.
        owner.mapping[64:320]=struct.pack('<32Q',*words)
        with pytest.raises(ValueError):
            owner.snapshot()


def test_timeline_read_does_not_replace_source_exit_endpoint():
    import inspect
    from scripts.run_b4b_mixed_connections import run_cell
    source=inspect.getsource(run_cell)
    assert 'pending = clients * connections_per_client if admission_client is not None and admission_client.poll() is None else 0' in source
    assert 'admission_finished = remember_completion(admission_finished, pending=pending, now=time.monotonic())' in source
    assert source.index('admission_finished = remember_completion') < source.index('source_timeline.snapshot()')
    assert 'if not process_exit:' in source


def test_close_error_still_records_local_return_cleanup():
    from pathlib import Path
    source=Path('crates/nbsr-transport/src/bin/perf_rust_source.rs').read_text()
    assert 'if matches!(terminal, TerminalKind::Completed) {\n            handshake_timeline::mark(handshake_timeline::Event::Cleaned);' not in source
