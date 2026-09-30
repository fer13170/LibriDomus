"""Elegir una ubicación: diálogo con árbol y buscador, y un campo reutilizable con la ruta."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ..datos import ubicaciones
from .arbol_ubicaciones import ArbolUbicaciones
from . import tema


class SelectorUbicacion(QDialog):
    def __init__(self, con: sqlite3.Connection, actual: int | None = None, titulo: str = "Elegir ubicación",
                 excluir: set[int] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(tema.px(420), tema.px(520))
        self.excluir = excluir or set()
        self.filtro = QLineEdit(placeholderText="Filtrar ubicaciones…")
        self.arbol = ArbolUbicaciones(con, contar=True)
        self.ruta = QLabel(objectName="ruta", wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.boton_ok = botones.button(QDialogButtonBox.StandardButton.Ok)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        capa = QVBoxLayout(self)
        capa.addWidget(self.filtro)
        capa.addWidget(self.arbol)
        capa.addWidget(self.ruta)
        capa.addWidget(botones)

        self.con = con
        self.filtro.textChanged.connect(self.arbol.filtrar)
        self.arbol.ubicacion_cambiada.connect(self._actualizar)
        self.arbol.itemDoubleClicked.connect(lambda *_: self.boton_ok.isEnabled() and self.accept())
        if actual:
            self.arbol.seleccionar(actual)
        self._actualizar(self.arbol.id_actual())

    def _actualizar(self, ubicacion_id):
        valido = ubicacion_id is not None and ubicacion_id not in self.excluir
        self.boton_ok.setEnabled(valido)
        self.ruta.setText(ubicaciones.ruta_texto(self.con, ubicacion_id, incluir_raiz=True) if ubicacion_id else "")

    def ubicacion_id(self) -> int | None:
        return self.arbol.id_actual()


def elegir_ubicacion(con, padre=None, actual=None, titulo="Elegir ubicación", excluir=None) -> int | None:
    dialogo = SelectorUbicacion(con, actual, titulo, excluir, padre)
    return dialogo.ubicacion_id() if dialogo.exec() == QDialog.DialogCode.Accepted else None


class CampoUbicacion(QWidget):
    """Muestra la ruta de la ubicación elegida con botones para cambiarla o quitarla."""

    cambiada = Signal(object)

    def __init__(self, con: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.con = con
        self._id: int | None = None
        self.ruta = QLabel(objectName="ruta", wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        self.boton_elegir = QPushButton("Elegir…")
        self.boton_quitar = QPushButton("Quitar")
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.ruta, 1)
        capa.addWidget(self.boton_elegir)
        capa.addWidget(self.boton_quitar)
        self.boton_elegir.clicked.connect(self._elegir)
        self.boton_quitar.clicked.connect(lambda: self.establecer(None))
        self.establecer(None)

    def _elegir(self):
        elegido = elegir_ubicacion(self.con, self, self._id)
        if elegido is not None:
            self.establecer(elegido)

    def establecer(self, ubicacion_id: int | None) -> None:
        self._id = ubicacion_id
        self.ruta.setText(ubicaciones.ruta_texto(self.con, ubicacion_id) if ubicacion_id else "(sin ubicación)")
        self.boton_quitar.setEnabled(ubicacion_id is not None)
        self.cambiada.emit(ubicacion_id)

    def valor(self) -> int | None:
        return self._id
