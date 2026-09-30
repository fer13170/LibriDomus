"""Dibuja el icono del programa (una estantería con libros) y lo guarda como
build/icono.ico (para el .exe) y bibliotecario/recursos/icono.png (para las ventanas).

Uso:  .venv\\Scripts\\python build\\generar_icono.py
"""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

RAIZ = Path(__file__).resolve().parent.parent


def dibujar(lado: int) -> QImage:
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = lado / 64.0
    # Fondo redondeado
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2f4858"))
    p.drawRoundedRect(QRectF(2 * u, 2 * u, 60 * u, 60 * u), 10 * u, 10 * u)
    # Balda
    p.setBrush(QColor("#c89b6d"))
    p.drawRect(QRectF(8 * u, 48 * u, 48 * u, 5 * u))
    # Lomos de libros
    libros = [(10, 18, 7, "#e4572e"), (18, 12, 8, "#f3a712"), (27, 20, 6, "#29335c"),
              (34, 14, 7, "#76b041"), (42, 24, 5, "#e4e4e4")]
    for x, y, ancho, color in libros:
        p.setBrush(QColor(color))
        p.drawRect(QRectF(x * u, y * u, ancho * u, (48 - y) * u))
    # Libro inclinado
    p.save()
    p.translate(52 * u, 48 * u)
    p.rotate(-18)
    p.setBrush(QColor("#a23b72"))
    p.drawRect(QRectF(-6 * u, -26 * u, 6 * u, 26 * u))
    p.restore()
    p.end()
    return imagen


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - necesario para pintar
    recursos = RAIZ / "bibliotecario" / "recursos"
    recursos.mkdir(exist_ok=True)
    dibujar(256).save(str(recursos / "icono.png"))
    # El formato ICO de Qt guarda una sola resolución: 256 px, que Windows escala.
    if not dibujar(256).save(str(RAIZ / "build" / "icono.ico"), "ICO"):
        print("No se pudo guardar el .ico")
        return 1
    print("Iconos generados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
