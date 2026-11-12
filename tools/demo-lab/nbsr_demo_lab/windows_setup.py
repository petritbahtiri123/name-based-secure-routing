"""Windows prerequisite inventory, plus explicit build-time staging write probe."""
import os
import uuid
from pathlib import Path


def inspect_paths(installations, sdk_root):
    msvc = sdk = None
    for installation in installations[:16]:
        root = Path(installation) / 'VC/Tools/MSVC'
        if not root.is_dir():
            continue
        for version in sorted(root.iterdir(), reverse=True)[:32]:
            required = ('bin/Hostx64/x64/cl.exe', 'bin/Hostx64/x64/link.exe',
                        'lib/x64/libcmt.lib', 'include/vcruntime.h')
            if all((version / name).is_file() for name in required):
                msvc = str(version)
                break
        if msvc:
            break
    sdk_root = Path(sdk_root)
    libs = sdk_root / 'Lib'
    if libs.is_dir():
        for version in sorted(libs.iterdir(), reverse=True)[:32]:
            required = (version / 'um/x64/kernel32.lib', version / 'ucrt/x64/ucrt.lib',
                        sdk_root / 'Include' / version.name / 'um/Windows.h',
                        sdk_root / 'Include' / version.name / 'ucrt/stdio.h')
            if all(path.is_file() for path in required):
                sdk = str(version)
                break
    return {'complete': bool(msvc and sdk), 'msvc': msvc, 'sdk': sdk,
            'scope': 'File inventory only; compiler/linker execution and cache completeness not proven'}


def discover(repo, command):
    import winreg
    base = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))
    vswhere = base / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installations = []
    if vswhere.is_file():
        installations = command(str(vswhere), ['-all', '-products', '*', '-property', 'installationPath'], repo).splitlines()
    sdk_root = base / 'Windows Kits/10'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
            sdk_root = Path(winreg.QueryValueEx(key, 'KitsRoot10')[0])
    except OSError:
        pass
    return inspect_paths(installations, sdk_root)


def probe_staging(root=Path('C:/NBSR-build/nbsr-demo')):
    from .setup import private_path
    root = private_path(root)
    root.mkdir(parents=True, exist_ok=True)
    owned = root / ('.write-probe-' + uuid.uuid4().hex)
    owned.mkdir(exist_ok=False)
    path = owned / 'probe'
    try:
        with path.open('xb') as file:
            file.write(b'NBSR staging permission probe')
        if path.read_bytes() != b'NBSR staging permission probe':
            raise ValueError('Staging write/read probe mismatch')
    finally:
        path.unlink(missing_ok=True)
        owned.rmdir()
    return {'write_read_delete_verified': True, 'root': str(root),
            'scope': 'Current user file access only; executable launch remains a live-run check'}
