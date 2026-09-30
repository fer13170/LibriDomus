"""Utilidades de texto: quitar acentos, abreviar nombres y comparar sin acentos."""

import re
import unicodedata


def sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def clave_orden(texto: str) -> str:
    """Clave para ordenar alfabéticamente sin que importen acentos ni mayúsculas."""
    return sin_acentos(texto or "").casefold()


def comparar(a: str, b: str) -> int:
    """Función de ordenación 'ES' que se registra en SQLite."""
    ka, kb = clave_orden(a), clave_orden(b)
    return (ka > kb) - (ka < kb)


def abreviar(nombre: str) -> str:
    """Abreviatura corta y legible para códigos de ubicación.

    'Salón' -> 'SAL', 'Planta baja' -> 'PB', 'Estantería A' -> 'EA', 'Balda 3' -> 'B3'.
    """
    palabras = re.findall(r"[A-Z0-9]+", sin_acentos(nombre).upper())
    if not palabras:
        return "X"
    if len(palabras) == 1:
        return palabras[0][:3]
    ultima = palabras[-1]
    if len(ultima) <= 3 and (ultima.isdigit() or len(ultima) == 1):
        return palabras[0][0] + ultima
    return "".join(p[0] for p in palabras)[:4]
