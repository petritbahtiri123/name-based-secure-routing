"""Safe bounded PID-only snapshots of the exact owned Job; never signal by PID."""
import ctypes as C
from ctypes import wintypes as W
from coherent_backend import CoherentBackend

class ProcessIds(C.Structure):
    _fields_=[('NumberOfAssignedProcesses',W.DWORD),('NumberOfProcessIdsInList',W.DWORD),
              ('ProcessIdList',C.c_size_t*256)]

class DiagnosticBackend(CoherentBackend):
    def member_pids(self,job):
        info=ProcessIds()
        self._check(self.kernel.QueryInformationJobObject(job,3,C.byref(info),C.sizeof(info),None))
        if info.NumberOfProcessIdsInList>256 or info.NumberOfAssignedProcesses>256:
            raise RuntimeError('Job PID snapshot exceeds bound')
        pids=list(info.ProcessIdList[:info.NumberOfProcessIdsInList])
        if any(p<=0 for p in pids) or len(set(pids))!=len(pids):
            raise RuntimeError('invalid Job PID snapshot')
        return pids
