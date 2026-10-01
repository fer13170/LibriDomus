"""Genera los iconos de LibriDomus a partir de los dibujos vectoriales de la carpeta res/:

- res/LibriDomus-icono.svg           dibujo completo (casa, libros, balda y planta)
- res/LibriDomus-icono-pequeno.svg   versión simplificada para 16, 24 y 32 px

Resultado:
- build/icono.ico                    icono del .exe y del instalador (16 a 256 px)
- libridomus/recursos/icono.png      icono de las ventanas y de la barra (512 px)
- libridomus/recursos/logo.png       logotipo de la pantalla de bienvenida (512 px)
- res/LibriDomus-icono-1024.png      versión grande para usar fuera del programa

Uso:  .venv\\Scripts\\python build\\generar_icono.py
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

RAIZ = Path(__file__).resolve().parent.parent
SVG_GRANDE = RAIZ / "res" / "LibriDomus-icono.svg"
SVG_PEQUENO = RAIZ / "res" / "LibriDomus-icono-pequeno.svg"
TAMANOS_ICO = [16, 20, 24, 32, 40, 48, 64, 128, 256]
LIMITE_PEQUENO = 32  # hasta este tamaño se usa el dibujo simplificado


def pintar(svg: Path, lado: int) -> QImage:
    """Dibuja el SVG en un lienzo cuadrado transparente de ``lado`` píxeles."""
    renderizador = QSvgRenderer(str(svg))
    if not renderizador.isValid():
        raise ValueError(f"No se puede leer {svg}")
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.GlobalColor.transparent)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderizador.render(p, QRectF(0, 0, lado, lado))
    p.end()
    return imagen.convertToFormat(QImage.Format.Format_ARGB32)


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
    recursos = RAIZ / "libridomus" / "recursos"
    recursos.mkdir(exist_ok=True)
    grande = pintar(SVG_GRANDE, 512)
    grande.save(str(recursos / "icono.png"))
    grande.save(str(recursos / "logo.png"))
    pintar(SVG_GRANDE, 1024).save(str(RAIZ / "res" / "LibriDomus-icono-1024.png"))
    escribir_ico([pintar(SVG_PEQUENO if t <= LIMITE_PEQUENO else SVG_GRANDE, t) for t in TAMANOS_ICO],
                 RAIZ / "build" / "icono.ico")
    print("Iconos generados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
