"""Comprueba que la carpeta empaquetada no depende de nada instalado en este equipo.

Recorre todos los .exe, .dll y .pyd del paquete, lee qué DLL importa cada uno (con pefile,
que viene con PyInstaller) y exige que cada una esté:
  - dentro del paquete, o
  - entre las DLL que trae el propio Windows 10/11 (System32), salvo las «redistribuibles»
    (runtime de Visual C++, Python, OpenSSL, SQLite, Qt...), que DEBEN venir en el paquete
    porque el equipo de destino puede no tenerlas.
Además comprueba que están los complementos de Qt imprescindibles.

Uso:  .venv\\Scripts\\python build\\verificar_dependencias.py build\\salida\\LibriDomus
Devuelve 0 si todo está bien.
"""

import os
import re
import sys
from pathlib import Path

import pefile

SISTEMA = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"

# DLL que NO se pueden dar por supuestas en otro equipo aunque estén en este.
REDISTRIBUIBLES = re.compile(
    r"^(vcruntime\d+(_\d)?|msvcp\d+(_\w+)?|concrt\d+|vccorlib\d+|python\d+|libssl.*|libcrypto.*|"
    r"sqlite3|qt6.*|pyside6.*|shiboken6.*|libffi.*|zlib.*)\.dll$", re.IGNORECASE)

# Complementos de Qt sin los que el programa no arranca o pierde funciones.
IMPRESCINDIBLES = [  # rutas relativas a la carpeta PySide6 del paquete
    "plugins/platforms/qwindows.dll",   # ventanas en Windows
    "plugins/imageformats/qjpeg.dll",   # portadas JPEG
    "translations/qtbase_es.qm",        # botones estándar en español
]


def importaciones(archivo: Path) -> list[str]:
    try:
        pe = pefile.PE(str(archivo), fast_load=True)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
    except pefile.PEFormatError:
        return []
    nombres = [e.dll.decode("ascii", "ignore") for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])]
    nombres += [e.dll.decode("ascii", "ignore") for e in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", [])]
    pe.close()
    return nombres


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/salida/LibriDomus")
    binarios = [p for p in carpeta.rglob("*") if p.suffix.lower() in (".exe", ".dll", ".pyd")]
    incluidas = {p.name.lower() for p in binarios}
    problemas: dict[str, set[str]] = {}
    for binario in binarios:
        for dll in importaciones(binario):
            nombre = dll.lower()
            if nombre in incluidas or nombre.startswith(("api-ms-win-", "ext-ms-")):
                continue  # dentro del paquete, o conjunto de API del propio Windows
            if (SISTEMA / dll).exists() and not REDISTRIBUIBLES.match(dll):
                continue  # DLL propia de Windows
            motivo = "no incluida (en este equipo está en System32)" if (SISTEMA / dll).exists() else "no encontrada"
            problemas.setdefault(f"{dll}: {motivo}", set()).add(binario.relative_to(carpeta).as_posix())

    raiz_qt = next((p for p in carpeta.rglob("PySide6") if p.is_dir()), carpeta)
    faltan = [r for r in IMPRESCINDIBLES if not (raiz_qt / r).exists()]

    print(f"Binarios revisados: {len(binarios)}")
    runtime = sorted(n for n in incluidas if REDISTRIBUIBLES.match(n) and n.startswith(("vcruntime", "msvcp", "python")))
    print("Runtime incluido en el paquete: " + ", ".join(runtime))
    if problemas or faltan:
        for problema, quien in sorted(problemas.items()):
            print(f"  [FALTA] {problema}  <- {', '.join(sorted(quien)[:3])}")
        for f in faltan:
            print(f"  [FALTA] complemento de Qt: {f}")
        return 1
    print("Todas las dependencias están dentro del paquete o forman parte de Windows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
