"""Fail closed before retaining an unbounded import plan (standard-library only)."""
import os
import sys

MAX_RSS_BYTES = 1024 * 1024 * 1024


def check_memory_budget():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise RuntimeError('Cannot enforce import memory budget')
        rss = counters.WorkingSetSize
    elif os.path.exists('/proc/self/statm'):
        with open('/proc/self/statm', encoding='ascii') as handle:
            rss = int(handle.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    else:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = peak if sys.platform == 'darwin' else peak * 1024
    if rss > MAX_RSS_BYTES:
        raise MemoryError('Import RSS exceeds 1 GiB; use narrower categories/limits')
    return rss
