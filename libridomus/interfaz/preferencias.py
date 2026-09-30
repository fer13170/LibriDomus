"""Diálogo de preferencias (datos/config.json). Los cambios de apariencia se ven al momento."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox,
                               QFormLayout, QLabel, QLineEdit, QSlider, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)
from PySide6.QtCore import Qt

from .. import rutas
from ..servicios import configuracion
from . import tema


class Preferencias(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferencias")
        self.resize(tema.px(560), tema.px(440))
        self.ajustes = configuracion.cargar()
        self.original = dict(self.ajustes)
        pestanas = QTabWidget()
        pestanas.addTab(self._apariencia(), tema.icono("palette"), "Apariencia")
        pestanas.addTab(self._isbn(), tema.icono("scan-barcode"), "ISBN")
        pestanas.addTab(self._copias(), tema.icono("archive"), "Copias y etiquetas")
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addWidget(pestanas)
        capa.addWidget(botones)

    # ------------------------------------------------------------ pestañas

    def _apariencia(self) -> QWidget:
        self.tema = QComboBox()
        for clave, nombre in tema.TEMAS:
            self.tema.addItem(nombre, clave)
        self.tema.setCurrentIndex(max(0, self.tema.findData(self.ajustes["tema"])))
        self.escala = QSlider(Qt.Orientation.Horizontal)
        self.escala.setRange(0, len(tema.ESCALAS) - 1)
        self.escala.setPageStep(1)
        self.escala.setTickPosition(QSlider.TickPosition.TicksBelow)
        valores = [v for _, v in tema.ESCALAS]
        self.escala.setValue(valores.index(min(valores, key=lambda v: abs(v - float(self.ajustes["escala"])))))
        self.nombre_escala = QLabel(objectName="suave")
        self.fuente = QFontComboBox()
        self.fuente.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.fuente.setCurrentFont(QFont(self.ajustes["fuente"] or tema.FUENTE_POR_DEFECTO))
        ayuda = QLabel("Los cambios se ven al momento. También puedes cambiar el tamaño con Ctrl + y Ctrl − "
                       "desde la ventana principal.", objectName="suave", wordWrap=True)
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.addRow("Tema:", self.tema)
        formulario.addRow("Tamaño de la interfaz:", self.escala)
        formulario.addRow("", self.nombre_escala)
        formulario.addRow("Tipo de letra:", self.fuente)
        formulario.addRow(ayuda)
        self.tema.currentIndexChanged.connect(lambda _i: self._vista_previa())
        self.escala.valueChanged.connect(lambda _v: self._vista_previa())
        self.fuente.currentFontChanged.connect(lambda _f: self._vista_previa())
        self._rotular_escala()
        return pagina

    def _isbn(self) -> QWidget:
        self.consultar_isbn = QCheckBox("Permitir consultar datos por ISBN en Internet (Open Library)")
        self.consultar_isbn.setChecked(self.ajustes["consultar_isbn"])
        self.clave_google = QLineEdit(self.ajustes["clave_google_books"])
        self.clave_google.setPlaceholderText("Opcional")
        self.clave_google.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        ayuda = QLabel("Con una clave propia de Google Books se consulta también esa fuente cuando "
                       "Open Library no encuentra el libro. Sin clave, Google suele rechazar las consultas.",
                       objectName="suave", wordWrap=True)
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.addRow(self.consultar_isbn)
        formulario.addRow("Clave de Google Books:", self.clave_google)
        formulario.addRow(ayuda)
        return pagina

    def _copias(self) -> QWidget:
        self.copia_al_cerrar = QCheckBox("Hacer una copia de seguridad automática al cerrar")
        self.copia_al_cerrar.setChecked(self.ajustes["copia_al_cerrar"])
        self.copias_a_conservar = QSpinBox()
        self.copias_a_conservar.setRange(1, 100)
        self.copias_a_conservar.setValue(int(self.ajustes["copias_a_conservar"]))
        self.etiquetas_titulos = QSpinBox()
        self.etiquetas_titulos.setRange(0, 12)
        self.etiquetas_titulos.setValue(int(self.ajustes["etiquetas_titulos"]))
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.addRow(self.copia_al_cerrar)
        formulario.addRow("Copias automáticas a conservar:", self.copias_a_conservar)
        formulario.addRow(QLabel(f"Carpeta de copias: {rutas.carpeta_copias()}", objectName="suave",
                                 wordWrap=True))
        formulario.addRow("Títulos listados en cada etiqueta:", self.etiquetas_titulos)
        return pagina

    # ------------------------------------------------------------ apariencia en vivo

    def _valores_apariencia(self) -> tuple[str, float, str]:
        return (self.tema.currentData(), tema.ESCALAS[self.escala.value()][1], self.fuente.currentFont().family())

    def _rotular_escala(self):
        nombre, valor = tema.ESCALAS[self.escala.value()]
        self.nombre_escala.setText(f"{nombre} ({round(valor * 100)} %)")

    def _vista_previa(self):
        self._rotular_escala()
        tema.aplicar(QApplication.instance(), *self._valores_apariencia())

    def reject(self):
        # Se deshace la vista previa si se cancela.
        tema.aplicar(QApplication.instance(), self.original["tema"], self.original["escala"],
                     self.original["fuente"])
        super().reject()

    def guardar(self) -> None:
        tema_, escala, fuente = self._valores_apariencia()
        ajustes = configuracion.cargar()
        ajustes.update({
            "tema": tema_, "escala": escala, "fuente": fuente,
            "consultar_isbn": self.consultar_isbn.isChecked(),
            "clave_google_books": self.clave_google.text().strip(),
            "copia_al_cerrar": self.copia_al_cerrar.isChecked(),
            "copias_a_conservar": self.copias_a_conservar.value(),
            "etiquetas_titulos": self.etiquetas_titulos.value(),
        })
        configuracion.guardar(ajustes)
        self.accept()
