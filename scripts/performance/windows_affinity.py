"""Verified Windows process-affinity control for benchmark orchestration."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def affinity_mask(processors: int, logical_processors: int) -> int:
    if processors < 1 or logical_processors < 1 or processors > logical_processors:
        raise ValueError("invalid affinity processor count")
    return (1 << processors) - 1


def set_and_verify_affinity(pid: int, processors: int) -> dict[str, int | bool]:
    if os.name != "nt":
        raise RuntimeError("verified affinity is supported only on Windows")
    logical = os.cpu_count() or 1
    requested = affinity_mask(processors, logical)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.SetProcessAffinityMask.argtypes = (wintypes.HANDLE, ctypes.c_size_t)
    kernel32.SetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.GetProcessAffinityMask.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    )
    kernel32.GetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_SET_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        if not kernel32.SetProcessAffinityMask(handle, requested):
            raise OSError(ctypes.get_last_error(), "SetProcessAffinityMask failed")
        observed = ctypes.c_size_t()
        system = ctypes.c_size_t()
        if not kernel32.GetProcessAffinityMask(handle, ctypes.byref(observed), ctypes.byref(system)):
            raise OSError(ctypes.get_last_error(), "GetProcessAffinityMask failed")
        return {
            "requested_processors": processors,
            "requested_mask": requested,
            "observed_mask": observed.value,
            "system_mask": system.value,
            "verified": observed.value == requested and requested & system.value == requested,
        }
    finally:
        kernel32.CloseHandle(handle)
