"""Arranque de la interfaz gráfica."""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QLabel

from .. import NOMBRE, VERSION, rutas
from ..datos import conexion


def ejecutar(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName(NOMBRE)
    app.setApplicationVersion(VERSION)

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

    ventana = QMainWindow()
    ventana.setWindowTitle(f"{NOMBRE} {VERSION}")
    ventana.setCentralWidget(QLabel("Fase 0: base de datos lista."))
    ventana.resize(800, 500)
    ventana.show()
    codigo = app.exec()
    con.close()
    return codigo


if __name__ == "__main__":
    sys.exit(ejecutar(sys.argv))
