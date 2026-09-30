"""Panel de portada de la ficha: vista previa, elegir archivo, pegar, arrastrar y quitar.

El panel guarda la imagen en datos/portadas en cuanto se elige, pero recuerda cuáles son
nuevas: si la ficha se cancela, ``descartar_nuevas`` las borra para no dejar basura.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..servicios import portadas
from ..servicios.portadas import ErrorPortada
from . import comun

ANCHO, ALTO = 150, 210
FILTRO_IMAGENES = "Imágenes (*.jpg *.jpeg *.png *.bmp *.gif *.webp)"


class PanelPortada(QWidget):
    cambiada = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nombre = ""                  # archivo actual en datos/portadas
        self.nuevas: set[str] = set()     # creadas en esta ficha (se borran si se cancela)
        self.vista = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.vista.setFixedSize(ANCHO, ALTO)
        self.vista.setStyleSheet("QLabel { border: 1px dashed palette(mid); color: palette(mid); }")
        self.vista.setWordWrap(True)
        self.b_elegir = QPushButton("Elegir…")
        self.b_pegar = QPushButton("Pegar")
        self.b_quitar = QPushButton("Quitar")
        for b in (self.b_elegir, self.b_pegar, self.b_quitar):
            b.setAutoDefault(False)
        botones = QHBoxLayout()
        botones.setSpacing(2)
        botones.addWidget(self.b_elegir)
        botones.addWidget(self.b_pegar)
        botones.addWidget(self.b_quitar)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.vista, alignment=Qt.AlignmentFlag.AlignHCenter)
        capa.addLayout(botones)
        capa.addStretch()
        self.setAcceptDrops(True)
        self.b_elegir.clicked.connect(self.elegir)
        self.b_pegar.clicked.connect(self.pegar)
        self.b_quitar.clicked.connect(lambda: self.establecer(""))
        self.establecer("")

    # ------------------------------------------------------------ estado

    def establecer(self, nombre: str) -> None:
        self.nombre = nombre
        ruta = portadas.ruta(nombre)
        if ruta:
            imagen = QPixmap(str(ruta)).scaled(ANCHO - 4, ALTO - 4, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            self.vista.setPixmap(imagen)
        else:
            self.vista.setPixmap(QPixmap())
            self.vista.setText("Sin portada\n\nArrastra aquí\nuna imagen")
        self.b_quitar.setEnabled(bool(ruta))
        self.cambiada.emit()

    def poner_imagen(self, imagen: QImage) -> bool:
        try:
            nombre = portadas.guardar_imagen(imagen)
        except ErrorPortada as e:
            comun.error(self, str(e))
            return False
        self.nuevas.add(nombre)
        self.establecer(nombre)
        return True

    def poner_bytes(self, datos: bytes) -> bool:
        imagen = QImage()
        imagen.loadFromData(datos)
        return self.poner_imagen(imagen)

    def descartar_nuevas(self, conservar: str = "") -> None:
        """Borra las imágenes creadas en esta ficha salvo ``conservar``."""
        for nombre in self.nuevas - {conservar}:
            portadas.borrar(nombre)
        self.nuevas.clear()

    # ------------------------------------------------------------ acciones

    def elegir(self) -> None:
        archivo, _ = QFileDialog.getOpenFileName(self, "Elegir imagen de portada", "", FILTRO_IMAGENES)
        if archivo:
            self.poner_imagen(QImage(archivo))

    def pegar(self) -> None:
        imagen = QGuiApplication.clipboard().image()
        if imagen.isNull():
            comun.aviso(self, "El portapapeles no contiene ninguna imagen.")
            return
        self.poner_imagen(imagen)

    def dragEnterEvent(self, event):  # noqa: N802 - nombre impuesto por Qt
        datos = event.mimeData()
        if datos.hasImage() or datos.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        datos = event.mimeData()
        if datos.hasImage():
            self.poner_imagen(QImage(datos.imageData()))
        elif datos.hasUrls() and datos.urls()[0].isLocalFile():
            self.poner_imagen(QImage(datos.urls()[0].toLocalFile()))
        event.acceptProposedAction()
