"""Read-only, optional Windows OS-reported power state; no thermal inference."""
import ctypes as c
from functools import lru_cache
import time


class SystemInfo(c.Structure):
    _fields_ = [("dwOemId", c.c_uint32), ("dwPageSize", c.c_uint32),
                ("lpMinimumApplicationAddress", c.c_void_p), ("lpMaximumApplicationAddress", c.c_void_p),
                ("dwActiveProcessorMask", c.c_size_t), ("dwNumberOfProcessors", c.c_uint32),
                ("dwProcessorType", c.c_uint32), ("dwAllocationGranularity", c.c_uint32),
                ("wProcessorLevel", c.c_uint16), ("wProcessorRevision", c.c_uint16)]


class SystemPower(c.Structure):
    _fields_ = [("ACLineStatus", c.c_ubyte), ("BatteryFlag", c.c_ubyte),
                ("BatteryLifePercent", c.c_ubyte), ("SystemStatusFlag", c.c_ubyte),
                ("BatteryLifeTime", c.c_uint32), ("BatteryFullLifeTime", c.c_uint32)]


class ProcessorPower(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in ("Number", "MaxMhz", "CurrentMhz", "MhzLimit", "MaxIdleState", "CurrentIdleState")]


@lru_cache(maxsize=1)
def _apis():
    kernel = c.WinDLL("kernel32", use_last_error=True)
    power = c.WinDLL("powrprof", use_last_error=True)
    kernel.GetSystemInfo.argtypes = [c.POINTER(SystemInfo)]
    kernel.GetSystemInfo.restype = None
    info = SystemInfo()
    kernel.GetSystemInfo(c.byref(info))
    if not 1 <= info.dwNumberOfProcessors <= 64:
        raise OSError("unsupported processor group size")
    kernel.GetSystemPowerStatus.argtypes = [c.POINTER(SystemPower)]
    kernel.GetSystemPowerStatus.restype = c.c_int
    power.CallNtPowerInformation.argtypes = [c.c_int, c.c_void_p, c.c_uint32, c.c_void_p, c.c_uint32]
    power.CallNtPowerInformation.restype = c.c_int32
    return kernel.GetSystemPowerStatus, power.CallNtPowerInformation, info.dwNumberOfProcessors


def _unavailable(reason):
    return dict(available=False, return_code=None, error_code=None, call_cost_ns=None, fields=None, reason=reason)


def sample_host_power():
    result = dict(schema="nbsr-b5-host-power-v1", status="UNAVAILABLE", monotonic_timestamp_ns=time.perf_counter_ns(),
                  system_power_status=_unavailable("binding_unavailable"), processor_information=_unavailable("binding_unavailable"),
                  interpretation="OS-reported power status and processor MHz/limits; not effective clock, temperature, throttling attribution or watts")
    try:
        system_api, processor_api, count = _apis()
    except (OSError, AttributeError):
        return result
    system, processors = SystemPower(), (ProcessorPower * count)()
    for key, function, args in (
        ("system_power_status", system_api, (c.byref(system),)),
        ("processor_information", processor_api, (11, None, 0, c.byref(processors), c.sizeof(processors))),
    ):
        started = time.perf_counter_ns()
        try:
            code = function(*args)
            duration = time.perf_counter_ns() - started
            available = bool(code) if key == "system_power_status" else code == 0
            fields = None
            if available:
                fields = ({name: getattr(system, name) for name, _ in system._fields_} if key == "system_power_status"
                          else [{name: getattr(cpu, name) for name, _ in cpu._fields_} for cpu in processors])
            result[key] = dict(available=available, return_code=code if key == "system_power_status" else f"0x{code & 0xffffffff:08x}",
                               error_code=c.get_last_error() if key == "system_power_status" and not available else None,
                               call_cost_ns=duration, fields=fields, reason=None if available else "api_failure")
        except OSError:
            result[key] = {**_unavailable("call_exception"), "call_cost_ns": time.perf_counter_ns() - started}
    if result["system_power_status"]["available"] and result["processor_information"]["available"]:
        result["status"] = "AVAILABLE"
    return result
