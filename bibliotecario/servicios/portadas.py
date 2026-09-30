"""Imágenes de portada: se reducen y se guardan como JPEG en datos/portadas."""

import sqlite3
import uuid
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter

from .. import rutas

LADO_MAXIMO = 800   # píxeles del lado más largo
CALIDAD_JPEG = 85


class ErrorPortada(Exception):
    """La imagen no se puede leer o guardar (mensaje para el usuario)."""


def _reducir(imagen: QImage) -> QImage:
    if imagen.isNull():
        raise ErrorPortada("El archivo no es una imagen válida.")
    if max(imagen.width(), imagen.height()) > LADO_MAXIMO:
        imagen = imagen.scaled(LADO_MAXIMO, LADO_MAXIMO, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    return imagen


def guardar_imagen(imagen: QImage) -> str:
    """Guarda la imagen reducida y devuelve el nombre del archivo creado."""
    imagen = _reducir(imagen)
    if imagen.hasAlphaChannel():  # JPEG no admite transparencia: fondo blanco
        fondo = QImage(imagen.size(), QImage.Format.Format_RGB32)
        fondo.fill(Qt.GlobalColor.white)
        pintor = QPainter(fondo)
        pintor.drawImage(0, 0, imagen)
        pintor.end()
        imagen = fondo
    nombre = f"{uuid.uuid4().hex}.jpg"
    if not imagen.save(str(rutas.carpeta_portadas() / nombre), "JPG", CALIDAD_JPEG):
        raise ErrorPortada("No se ha podido guardar la imagen.")
    return nombre


def guardar_desde_archivo(ruta: Path | str) -> str:
    return guardar_imagen(QImage(str(ruta)))


def guardar_desde_bytes(datos: bytes) -> str:
    imagen = QImage()
    imagen.loadFromData(QByteArray(datos))
    return guardar_imagen(imagen)


def ruta(nombre: str) -> Path | None:
    if not nombre:
        return None
    archivo = rutas.carpeta_portadas() / nombre
    return archivo if archivo.exists() else None


def borrar(nombre: str) -> None:
    if nombre:
        (rutas.carpeta_portadas() / Path(nombre).name).unlink(missing_ok=True)


def limpiar_huerfanas(con: sqlite3.Connection) -> int:
    """Borra imágenes que ya no usa ningún elemento (p. ej. si se canceló una ficha)."""
    en_uso = {f[0] for f in con.execute("SELECT portada FROM elemento WHERE portada <> ''")}
    borradas = 0
    for archivo in rutas.carpeta_portadas().glob("*.jpg"):
        if archivo.name not in en_uso:
            archivo.unlink(missing_ok=True)
            borradas += 1
    return borradas


def a_png_bytes(imagen: QImage) -> bytes:
    """Utilidad para pruebas: imagen en memoria como PNG."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    imagen.save(buffer, "PNG")
    return bytes(buffer.data())
