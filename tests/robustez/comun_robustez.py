"""Utilidades compartidas por los scripts de robustez (no son pruebas de pytest)."""

import ctypes
import ctypes.wintypes
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))


class _Memoria(ctypes.Structure):
    _fields_ = [("cb", ctypes.wintypes.DWORD), ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def memoria_mb() -> tuple[float, float]:
    """(memoria actual, pico) del proceso en MB."""
    m = _Memoria()
    m.cb = ctypes.sizeof(m)
    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE  # pseudo-handle -1: sin esto se trunca
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(_Memoria), ctypes.wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(m), m.cb)
    return m.WorkingSetSize / 2**20, m.PeakWorkingSetSize / 2**20


def medir(nombre: str, funcion, resultados: list | None = None):
    inicio = time.perf_counter()
    valor = funcion()
    segundos = time.perf_counter() - inicio
    actual, pico = memoria_mb()
    linea = f"{nombre:<58} {segundos:8.2f} s   mem {actual:7.0f} MB (pico {pico:.0f})"
    print(linea, flush=True)
    if resultados is not None:
        resultados.append((nombre, segundos, actual))
    return valor


def carpeta_datos(nombre: str) -> Path:
    carpeta = Path(os.environ.get("TEMP", ".")) / "libridomus_robustez" / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    os.environ["LIBRIDOMUS_DATOS"] = str(carpeta)
    return carpeta
