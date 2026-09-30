"""Diálogo de preferencias (datos/config.json)."""

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
                               QLineEdit, QSpinBox, QVBoxLayout)

from .. import rutas
from ..servicios import configuracion


class Preferencias(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferencias")
        self.resize(520, 380)
        ajustes = configuracion.cargar()

        self.consultar_isbn = QCheckBox("Permitir consultar datos por ISBN en Internet (Open Library)")
        self.consultar_isbn.setChecked(ajustes["consultar_isbn"])
        self.clave_google = QLineEdit(ajustes["clave_google_books"])
        self.clave_google.setPlaceholderText("Opcional")
        self.clave_google.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        ayuda = QLabel("Con una clave propia de Google Books se consulta también esa fuente cuando "
                       "Open Library no encuentra el libro. Sin clave, Google suele rechazar las consultas.")
        ayuda.setWordWrap(True)
        isbn = QFormLayout()
        isbn.addRow(self.consultar_isbn)
        isbn.addRow("Clave de Google Books:", self.clave_google)
        isbn.addRow(ayuda)
        grupo_isbn = QGroupBox("Autocompletar por ISBN")
        grupo_isbn.setLayout(isbn)

        self.copia_al_cerrar = QCheckBox("Hacer una copia de seguridad automática al cerrar")
        self.copia_al_cerrar.setChecked(ajustes["copia_al_cerrar"])
        self.copias_a_conservar = QSpinBox()
        self.copias_a_conservar.setRange(1, 100)
        self.copias_a_conservar.setValue(int(ajustes["copias_a_conservar"]))
        copias = QFormLayout()
        copias.addRow(self.copia_al_cerrar)
        copias.addRow("Copias automáticas a conservar:", self.copias_a_conservar)
        copias.addRow(QLabel(f"Carpeta de copias: {rutas.carpeta_copias()}", wordWrap=True))
        grupo_copias = QGroupBox("Copias de seguridad")
        grupo_copias.setLayout(copias)

        self.etiquetas_titulos = QSpinBox()
        self.etiquetas_titulos.setRange(0, 12)
        self.etiquetas_titulos.setValue(int(ajustes["etiquetas_titulos"]))
        etiquetas = QFormLayout()
        etiquetas.addRow("Títulos listados en cada etiqueta:", self.etiquetas_titulos)
        grupo_etiquetas = QGroupBox("Etiquetas")
        grupo_etiquetas.setLayout(etiquetas)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        for w in (grupo_isbn, grupo_copias, grupo_etiquetas):
            capa.addWidget(w)
        capa.addStretch()
        capa.addWidget(botones)

    def guardar(self) -> None:
        ajustes = configuracion.cargar()
        ajustes.update({
            "consultar_isbn": self.consultar_isbn.isChecked(),
            "clave_google_books": self.clave_google.text().strip(),
            "copia_al_cerrar": self.copia_al_cerrar.isChecked(),
            "copias_a_conservar": self.copias_a_conservar.value(),
            "etiquetas_titulos": self.etiquetas_titulos.value(),
        })
        configuracion.guardar(ajustes)
        self.accept()
