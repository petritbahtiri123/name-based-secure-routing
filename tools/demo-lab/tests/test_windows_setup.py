import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab.windows_setup import inspect_paths, probe_staging

def test_missing_sdk_blocks_inventory(tmp_path):
    result = inspect_paths([tmp_path / 'vs'], tmp_path / 'sdk')
    assert not result['complete']
    assert result['msvc'] is None and result['sdk'] is None

def test_complete_inventory_requires_headers_linker_and_libraries(tmp_path):
    vs, sdk = tmp_path/'vs', tmp_path/'sdk'
    files = ['VC/Tools/MSVC/14.44/bin/Hostx64/x64/cl.exe', 'VC/Tools/MSVC/14.44/bin/Hostx64/x64/link.exe', 'VC/Tools/MSVC/14.44/lib/x64/libcmt.lib', 'VC/Tools/MSVC/14.44/include/vcruntime.h']
    sdkfiles = ['Lib/10.0/um/x64/kernel32.lib', 'Lib/10.0/ucrt/x64/ucrt.lib', 'Include/10.0/um/Windows.h', 'Include/10.0/ucrt/stdio.h']
    for root, names in ((vs,files),(sdk,sdkfiles)):
        for name in names:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
    assert inspect_paths([vs],sdk)['complete']
    (sdk/sdkfiles[0]).unlink()
    assert not inspect_paths([vs],sdk)['complete']

def test_probe_preserves_existing_files_and_cleans_only_own_directory(tmp_path):
    root=tmp_path/'staging';root.mkdir();sentinel=root/'keep';sentinel.write_bytes(b'existing')
    assert probe_staging(root)['write_read_delete_verified']
    assert list(root.iterdir())==[sentinel]
    assert sentinel.read_bytes()==b'existing'

def test_probe_rejects_file_as_root(tmp_path):
    root=tmp_path/'file';root.write_bytes(b'keep')
    with pytest.raises((ValueError,OSError)):
        probe_staging(root)
    assert root.read_bytes()==b'keep'


def test_staging_denial_stops_build_before_compiler(tmp_path, monkeypatch):
    from nbsr_demo_lab import setup, windows_setup
    monkeypatch.setattr(setup.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(setup, 'check', lambda repo: {'ready_for_build': True})
    def denied():
        raise PermissionError('fixture staging denial')
    monkeypatch.setattr(windows_setup, 'probe_staging', denied)
    invoked = []
    monkeypatch.setattr(setup, 'guarded', lambda *args: invoked.append(args))
    with pytest.raises(PermissionError):
        setup.build(tmp_path, tmp_path/'state')
    assert invoked == [] and not (tmp_path/'state').exists()
