"""Elegir las ubicaciones para imprimir sus etiquetas (PDF A4, 8 por hoja)."""

import sqlite3

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QPushButton,
                               QTreeWidgetItem, QVBoxLayout)

from ..servicios import configuracion, etiquetas
from . import comun, tema
from .arbol_ubicaciones import ROL_ID, ArbolUbicaciones


class DialogoEtiquetas(QDialog):
    def __init__(self, con: sqlite3.Connection, marcar: int | None = None, parent=None):
        super().__init__(parent)
        self.con = con
        self.setWindowTitle("Imprimir etiquetas")
        self.resize(tema.px(460), tema.px(600))
        explicacion = QLabel("Marca las cajas, baldas o muebles que quieres etiquetar. Se genera un PDF "
                             "A4 con 8 etiquetas por hoja (código, ruta, contenido y QR) para recortar.")
        explicacion.setWordWrap(True)
        self.arbol = ArbolUbicaciones(con, contar=True)
        for item in self.items():
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        self.resumen = QLabel()
        b_rama = QPushButton("Marcar con todo lo que contiene")
        b_ninguna = QPushButton("Desmarcar todas")
        fila = QHBoxLayout()
        fila.addWidget(b_rama)
        fila.addWidget(b_ninguna)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_generar = botones.addButton("Generar PDF…", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.accepted.connect(self.generar)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addWidget(explicacion)
        capa.addWidget(self.arbol)
        capa.addLayout(fila)
        capa.addWidget(self.resumen)
        capa.addWidget(botones)
        b_rama.clicked.connect(self.marcar_rama)
        b_ninguna.clicked.connect(lambda: [i.setCheckState(0, Qt.CheckState.Unchecked) for i in self.items()])
        self.arbol.itemChanged.connect(lambda *_: self._actualizar())
        if marcar is not None and self.arbol.seleccionar(marcar):
            self.arbol.currentItem().setCheckState(0, Qt.CheckState.Checked)
        self.ruta_generada = None
        self._actualizar()

    def items(self) -> list[QTreeWidgetItem]:
        return list(self.arbol.todos_los_items())

    def marcados(self) -> list[int]:
        return [i.data(0, ROL_ID) for i in self.items() if i.checkState(0) == Qt.CheckState.Checked]

    def marcar_rama(self) -> None:
        actual = self.arbol.currentItem()
        pila = [actual] if actual else []
        while pila:
            item = pila.pop()
            item.setCheckState(0, Qt.CheckState.Checked)
            pila.extend(item.child(i) for i in range(item.childCount()))

    def _actualizar(self) -> None:
        n = len(self.marcados())
        hojas = (n - 1) // (etiquetas.COLUMNAS * etiquetas.FILAS) + 1 if n else 0
        self.resumen.setText(f"{n} etiqueta(s) · {hojas} hoja(s)")
        self.b_generar.setEnabled(n > 0)

    def generar(self, destino: str | None = None, abrir: bool = True) -> bool:
        if destino is None:
            destino, _ = QFileDialog.getSaveFileName(self, "Guardar etiquetas", "etiquetas.pdf", "PDF (*.pdf)")
            if not destino:
                return False
        try:
            etiquetas.generar_pdf(self.con, self.marcados(), destino, configuracion.obtener("etiquetas_titulos"))
        except (OSError, ValueError) as e:
            comun.error(self, f"No se ha podido crear el PDF: {e}")
            return False
        self.ruta_generada = destino
        if abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(destino))
        self.accept()
        return True
