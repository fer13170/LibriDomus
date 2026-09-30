"""¿Se interpreta como HTML lo que escribe el usuario (título, personas, etiquetas, notas)?"""

import os
import shutil

from comun_robustez import carpeta_datos

datos = carpeta_datos("html")
shutil.rmtree(datos, ignore_errors=True)
datos.mkdir(parents=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import Qt as QtGui_Qt  # noqa: E402  (mightBeRichText vive aquí en PySide6)
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication([])
from libridomus.datos import conexion, elementos, tipos  # noqa: E402
from libridomus.datos.elementos import Elemento  # noqa: E402
from libridomus.interfaz.panel_detalle import PanelDetalle  # noqa: E402

try:
    rico = QtGui_Qt.mightBeRichText
except AttributeError:
    from PySide6.QtGui import QTextDocumentFragment  # noqa: F401
    rico = lambda t: "<" in t and ">" in t  # noqa: E731

con = conexion.abrir()
titulo = "<h1 style='font-size:60px;color:red'>ENORME</h1>"
id_ = elementos.guardar(con, Elemento(
    tipo_id=tipos.por_nombre(con, "Libro").id, titulo=titulo, subtitulo="<u>sub</u>",
    personas=[("<b>Negrita</b>", "Autor")], etiquetas=["<i>x</i>"],
    notas="<img src='file:///C:/Windows/Web/Wallpaper/Windows/img0.jpg' width=400>"))
panel = PanelDetalle(con)
panel.mostrar([id_])
for etiqueta in panel.findChildren(QLabel):
    t = etiqueta.text()
    if any(m in t for m in ("ENORME", "sub", "Negrita", "<i>x", "img0")):
        interpretado = etiqueta.textFormat() != Qt.TextFormat.PlainText and rico(t)
        print(f"{'SE INTERPRETA' if interpretado else 'texto plano  '}  {t[:70]!r}")
