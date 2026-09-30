"""Arranque de la interfaz gráfica."""

import sqlite3
import sys

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import NOMBRE, VERSION, rutas
from ..datos import conexion
from . import comun


def ejecutar(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationVersion(VERSION)
    comun.preparar_aplicacion(app)

    carpeta = rutas.carpeta_datos()
    if not rutas.se_puede_escribir(carpeta):
        QMessageBox.critical(
            None, NOMBRE,
            f"No se puede escribir en la carpeta de datos:\n{carpeta}\n\n"
            "Copia la carpeta del programa a Documentos, al Escritorio o a un USB.",
        )
        return 1
    try:
        con = conexion.abrir()
    except conexion.ErrorBaseDatos as error:
        QMessageBox.critical(None, NOMBRE, str(error))
        return 1

    from ..servicios import portadas
    from .ventana_principal import VentanaPrincipal

    portadas.limpiar_huerfanas(con)  # imágenes que quedaron sin uso (p. ej. por un cierre inesperado)

    ventana = VentanaPrincipal(con)
    restaurar_geometria(ventana)
    ventana.show()
    codigo = app.exec()
    guardar_geometria(ventana)
    if not ventana.restaurado:  # tras restaurar, la conexión ya está cerrada
        copia_al_salir(con)
        con.close()
    return codigo


def restaurar_geometria(ventana) -> None:
    from ..servicios import configuracion

    guardada = configuracion.obtener("ventana")
    if guardada:
        try:
            ventana.restoreGeometry(QByteArray.fromBase64(guardada.encode("ascii")))
        except (UnicodeEncodeError, ValueError):
            pass  # una preferencia dañada no impide arrancar


def guardar_geometria(ventana) -> None:
    from ..servicios import configuracion

    ajustes = configuracion.cargar()
    ajustes["ventana"] = bytes(ventana.saveGeometry().toBase64()).decode("ascii")
    try:
        configuracion.guardar(ajustes)
    except OSError:
        pass


def copia_al_salir(con) -> None:
    """Copia automática de la base de datos al cerrar (si está activada en Preferencias)."""
    from ..servicios import configuracion, copias

    ajustes = configuracion.cargar()
    if not ajustes["copia_al_cerrar"]:
        return
    try:
        copias.copia_automatica(con, int(ajustes["copias_a_conservar"]))
    except (OSError, sqlite3.Error) as error:
        QMessageBox.warning(None, NOMBRE, f"No se ha podido hacer la copia automática:\n{error}")


if __name__ == "__main__":
    sys.exit(ejecutar(sys.argv))
