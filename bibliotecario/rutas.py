"""Rutas de la carpeta portable.

Todo lo que el programa guarda vive en la subcarpeta ``datos`` que está junto
al ejecutable (o junto al código fuente cuando se ejecuta sin empaquetar).
La variable de entorno ``BV_DATOS`` permite usar otra carpeta (se usa en las pruebas).
"""

import os
import sys
from pathlib import Path


def carpeta_programa() -> Path:
    """Carpeta donde está el .exe (empaquetado) o la raíz del proyecto (desarrollo)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def carpeta_datos() -> Path:
    alternativa = os.environ.get("BV_DATOS")
    carpeta = Path(alternativa) if alternativa else carpeta_programa() / "datos"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def ruta_base_datos() -> Path:
    return carpeta_datos() / "biblioteca.db"


def carpeta_portadas() -> Path:
    carpeta = carpeta_datos() / "portadas"
    carpeta.mkdir(exist_ok=True)
    return carpeta


def carpeta_copias() -> Path:
    carpeta = carpeta_datos() / "copias"
    carpeta.mkdir(exist_ok=True)
    return carpeta


def ruta_configuracion() -> Path:
    return carpeta_datos() / "config.json"


def se_puede_escribir(carpeta: Path) -> bool:
    """Comprueba de verdad que se puede crear un archivo en la carpeta."""
    prueba = carpeta / ".prueba_escritura"
    try:
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return True
    except OSError:
        return False
