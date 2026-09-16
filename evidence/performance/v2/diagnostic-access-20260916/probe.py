"""Own-process profiling permission probe; no sysctl/capability modifications."""
import ctypes
import errno
import json
import os
import platform
from pathlib import Path

assert platform.machine() == 'x86_64', 'syscall number is architecture-specific'
libc = ctypes.CDLL(None, use_errno=True)
attr = ctypes.create_string_buffer(128)
# perf_event_attr: software CPU clock, disabled, exclude kernel and hypervisor.
ctypes.c_uint32.from_buffer(attr, 0).value = 1
ctypes.c_uint32.from_buffer(attr, 4).value = 128
ctypes.c_uint64.from_buffer(attr, 8).value = 0
ctypes.c_uint64.from_buffer(attr, 40).value = 1 | (1 << 5) | (1 << 6)
libc.syscall.restype = ctypes.c_long
fd = libc.syscall(ctypes.c_long(298), ctypes.byref(attr), ctypes.c_int(0),
                  ctypes.c_int(-1), ctypes.c_int(-1), ctypes.c_ulong(0))
error = ctypes.get_errno() if fd < 0 else 0
if fd >= 0:
    os.close(fd)
report = dict(kernel=platform.release(), machine=platform.machine(), uid=os.getuid(),
              perf_event_paranoid=Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip(),
              own_process_software_cpu_clock_opened=fd >= 0,
              errno=error, error=errno.errorcode.get(error),
              process_security=[line for line in Path('/proc/self/status').read_text().splitlines()
                                if line.startswith(('CapEff:', 'Seccomp:', 'NoNewPrivs:'))],
              limitations=['A denied syscall does not distinguish seccomp from other permission restrictions.',
                           'No conclusion about native Windows or externally configured Linux permissions.'])
print(json.dumps(report, indent=2))
