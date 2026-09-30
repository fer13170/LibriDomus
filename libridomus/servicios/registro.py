"""Registro de errores (datos/registro.log) y mensajes comprensibles para el usuario.

Cualquier error inesperado queda anotado con su traza completa para poder diagnosticarlo,
y al usuario se le muestra una explicación en castellano sin tecnicismos.
"""

import logging
import sqlite3
from logging.handlers import RotatingFileHandler

from .. import NOMBRE, VERSION, rutas

registro = logging.getLogger("libridomus")
_configurado = False


def configurar() -> None:
    """Activa el archivo de registro (512 KB, se conservan 3 anteriores)."""
    global _configurado
    if _configurado:
        return
    try:
        manejador = RotatingFileHandler(rutas.carpeta_datos() / "registro.log", maxBytes=512 * 1024,
                                        backupCount=3, encoding="utf-8")
    except OSError:
        return  # sin permiso de escritura: el programa lo avisará por otra vía
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    registro.addHandler(manejador)
    registro.setLevel(logging.INFO)
    registro.propagate = False
    _configurado = True
    registro.info("Inicio de %s %s", NOMBRE, VERSION)


def mensaje_para_usuario(error: BaseException) -> str:
    """Explicación comprensible de un error (la traza técnica va al registro)."""
    from ..datos.conexion import ErrorBaseDatos, traducir_error

    if isinstance(error, ErrorBaseDatos):
        return str(error)
    if isinstance(error, sqlite3.DatabaseError):
        return str(traducir_error(error))
    if isinstance(error, PermissionError):
        return "Windows no ha permitido acceder a un archivo. Comprueba que no está abierto en otro programa."
    if isinstance(error, OSError) and (getattr(error, "winerror", None) == 112  # ERROR_DISK_FULL
                                       or "No space left" in str(error)):
        return "No queda espacio libre en el disco. Libera espacio e inténtalo de nuevo."
    if isinstance(error, MemoryError):
        return "No hay memoria suficiente para completar la operación."
    return "Ha ocurrido un error inesperado. Tus datos están a salvo; puedes seguir trabajando."
