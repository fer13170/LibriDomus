"""Genera los iconos de LibriDomus a partir de res/LibriDomus---Icono.png:

- build/icono.ico                       icono del .exe (16, 24, 32, 48, 64, 128 y 256 px)
- libridomus/recursos/icono.png         icono cuadrado de las ventanas (256 px)
- libridomus/recursos/logo.png          el dibujo original, para «Acerca de» y la pantalla de bienvenida

Uso:  .venv\\Scripts\\python build\\generar_icono.py
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "res" / "LibriDomus---Icono.png"
TAMANOS_ICO = [16, 24, 32, 48, 64, 128, 256]


def cuadrado(imagen: QImage, lado: int) -> QImage:
    """Centra la imagen (sin deformarla) en un lienzo cuadrado transparente."""
    lienzo = QImage(lado, lado, QImage.Format.Format_ARGB32)
    lienzo.fill(Qt.GlobalColor.transparent)
    margen = max(1, lado // 32)
    escalada = imagen.scaled(lado - 2 * margen, lado - 2 * margen, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    p = QPainter(lienzo)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QPoint((lado - escalada.width()) // 2, (lado - escalada.height()) // 2), escalada)
    p.end()
    return lienzo


def png_bytes(imagen: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    imagen.save(buffer, "PNG")
    return bytes(buffer.data())


def escribir_ico(imagenes: list[QImage], destino: Path) -> None:
    """Formato ICO con imágenes PNG dentro (admitido desde Windows Vista)."""
    datos = [png_bytes(i) for i in imagenes]
    cabecera = struct.pack("<HHH", 0, 1, len(datos))
    desplazamiento = 6 + 16 * len(datos)
    directorio = b""
    for imagen, contenido in zip(imagenes, datos):
        lado = imagen.width()
        directorio += struct.pack("<BBBBHHII", lado % 256, lado % 256, 0, 0, 1, 32,
                                  len(contenido), desplazamiento)
        desplazamiento += len(contenido)
    destino.write_bytes(cabecera + directorio + b"".join(datos))


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - necesario para pintar
    original = QImage(str(ORIGEN))
    if original.isNull():
        print(f"No se puede leer {ORIGEN}")
        return 1
    recursos = RAIZ / "libridomus" / "recursos"
    recursos.mkdir(exist_ok=True)
    cuadrado(original, 256).save(str(recursos / "icono.png"))
    original.save(str(recursos / "logo.png"))
    escribir_ico([cuadrado(original, t) for t in TAMANOS_ICO], RAIZ / "build" / "icono.ico")
    print("Iconos generados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
