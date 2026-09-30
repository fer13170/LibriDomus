"""Restaurar una copia de seguridad."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from ..servicios import copias
from . import tema


class DialogoRestaurar(QDialog):
    """Elige la copia: una de las guardadas en datos/copias o un archivo .zip/.db."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restaurar copia de seguridad")
        self.resize(tema.px(520), tema.px(440))
        self.elegida: str | None = None
        aviso = QLabel("Al restaurar, los datos actuales se sustituyen por los de la copia. Antes se "
                       "guarda automáticamente una copia del estado actual. El programa se reiniciará.")
        aviso.setWordWrap(True)
        self.lista = QListWidget()
        for c in copias.listar():
            tipo = "automática" if c.automatica else "previa a un cambio"
            item = QListWidgetItem(f"{c.fecha:%d/%m/%Y %H:%M}   ·   {tipo}   ·   {c.tamano / 1024:.0f} KB")
            item.setData(Qt.ItemDataRole.UserRole, str(c.ruta))
            self.lista.addItem(item)
        if not self.lista.count():
            self.lista.addItem("(no hay copias en la carpeta de copias)")
            self.lista.setEnabled(False)
        b_archivo = QPushButton("Elegir un archivo de copia (.zip o .db)…")
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_restaurar = botones.addButton("Restaurar la seleccionada", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_restaurar.setEnabled(False)
        botones.accepted.connect(self._aceptar_lista)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addWidget(aviso)
        capa.addWidget(self.lista)
        capa.addWidget(b_archivo)
        capa.addWidget(botones)
        self.lista.currentItemChanged.connect(lambda i, _a: self.b_restaurar.setEnabled(
            i is not None and i.data(Qt.ItemDataRole.UserRole) is not None))
        b_archivo.clicked.connect(self._elegir_archivo)

    def _aceptar_lista(self):
        item = self.lista.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.elegida = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _elegir_archivo(self):
        archivo, _ = QFileDialog.getOpenFileName(self, "Elegir copia", "",
                                                 "Copias de LibriDomus (*.zip *.db)")
        if archivo:
            self.elegida = archivo
            self.accept()
