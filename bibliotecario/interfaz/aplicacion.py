"""Arranque de la interfaz gráfica."""

import sys

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
    ventana.show()
    codigo = app.exec()
    con.close()
    return codigo


if __name__ == "__main__":
    sys.exit(ejecutar(sys.argv))
