"""Lanzador: ejecutar con ``python BibliotecarioVirtual.py``. PyInstaller lo usa como entrada."""

import sys

from bibliotecario.main import main

if __name__ == "__main__":
    sys.exit(main())
