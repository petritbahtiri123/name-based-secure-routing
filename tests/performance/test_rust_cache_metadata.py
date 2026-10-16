"""Offline fixtures only; never call Docker or the Rust toolchain."""
import ctypes
import hashlib
import os
from pathlib import Path
import subprocess

import pytest

from scripts.performance.rust_cache_metadata import probe_arguments, registry_packages
from scripts.performance.windows_docker_provisioning import windows_argv_units


def fixture():
    return ('version = 4\n[[package]]\nname = "local"\nversion = "0.1.0"\n'
            '[[package]]\nname = "example"\nversion = "1.2.3"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            'checksum = "' + 'a' * 64 + '"\n').encode()


def test_registry_parser_and_rejected_sources():
    assert registry_packages(fixture()) == [('example', '1.2.3', 'a' * 64)]
    with pytest.raises(ValueError):
        registry_packages(fixture().replace(b'registry+', b'git+'))
    with pytest.raises(ValueError):
        registry_packages(fixture().replace(b'example', b'bad;command'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows argv API')
def test_current_lock_inventory_and_windows_roundtrip():
    wire = Path('crates/nbsr-transport/Cargo.lock').read_bytes()
    assert len(registry_packages(wire)) == 130
    args = ['C:/Program Files/Docker/docker.exe', *probe_arguments(wire)]
    assert windows_argv_units(args) < 4000
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(subprocess.list2cmdline(args), ctypes.byref(count))
    assert pointer
    try:
        assert [pointer[i] for i in range(count.value)] == args
    finally:
        kernel.LocalFree(pointer)


@pytest.mark.skipif(os.name != 'nt', reason='provisioned Windows Git shell fixture')
def test_shell_fixture_parsing_and_missing_tools(tmp_path):
    bash = Path('C:/Program Files/Git/bin/bash.exe')
    if not bash.is_file():
        pytest.skip('provisioned Git shell unavailable')
    lock = tmp_path / 'Cargo.lock'
    lock.write_bytes(fixture())
    args = probe_arguments(fixture(), lock.as_posix())
    env = dict(os.environ, MSYS_NO_PATHCONV='1', PATH='C:/Program Files/Git/usr/bin')
    result = subprocess.run([str(bash), *args[2:]], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'PACKAGE example 1.2.3 ' + 'a' * 64 in result.stdout
    assert 'COUNT 1' in result.stdout and 'COMPLETE' in result.stdout
    assert hashlib.sha256(fixture()).hexdigest() in result.stdout
    current = Path('crates/nbsr-transport/Cargo.lock').read_bytes()
    lock.write_bytes(current)
    current_args = probe_arguments(current, lock.as_posix())
    result = subprocess.run([str(bash), *current_args[2:]], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    actual = {tuple(line.split()[1:]) for line in result.stdout.splitlines() if line.startswith('PACKAGE ')}
    assert actual == set(registry_packages(current))
    assert 'COUNT 130' in result.stdout
    args[3] = 'PATH=/nonexistent; export PATH; ' + args[3]
    result = subprocess.run([str(bash), *args[2:]], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'MISSING_TOOL awk' in result.stdout
