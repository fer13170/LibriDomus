"""Lanzador: ejecutar con ``python LibriDomus.py``. PyInstaller lo usa como entrada."""

import sys

from libridomus.main import main

if __name__ == "__main__":
    sys.exit(main())
