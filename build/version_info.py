"""Crea el archivo de versión de Windows para PyInstaller (--version-file).

Son los datos que se ven en el .exe con clic derecho › Propiedades › Detalles: nombre,
descripción, versión y copyright. Un ejecutable sin estos datos parece más sospechoso
a los antivirus, así que conviene incluirlos siempre.

Uso:  .venv\\Scripts\\python build\\version_info.py <archivo_de_salida>
"""

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from libridomus import NOMBRE, VERSION  # noqa: E402

PLANTILLA = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={tupla}, prodvers={tupla}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('0C0A04B0', [
      StringStruct('CompanyName', '{nombre}'),
      StringStruct('FileDescription', '{nombre}: dónde está cada libro, disco o álbum de tu casa'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{nombre}'),
      StringStruct('LegalCopyright', '© {anio} {nombre}'),
      StringStruct('OriginalFilename', '{nombre}.exe'),
      StringStruct('ProductName', '{nombre}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])])
  ]
)
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    numeros = [int(n) for n in VERSION.split(".")][:4]
    tupla = tuple(numeros + [0] * (4 - len(numeros)))
    texto = PLANTILLA.format(tupla=tupla, nombre=NOMBRE, version=VERSION, anio=date.today().year)
    destino = Path(sys.argv[1])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
