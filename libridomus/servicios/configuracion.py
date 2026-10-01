"""Preferencias del programa, guardadas en datos/config.json.

Cada valor leído se valida (tipo y rango). Si alguien edita el archivo a mano y pone algo
inválido, se usa el valor por defecto de ese ajuste en lugar de impedir que el programa arranque.
"""

import json
import os

from .. import rutas

ESCALAS_VALIDAS = (0.9, 1.0, 1.15, 1.3, 1.5)
NUM_COLUMNAS = 7  # columnas de la lista de la ventana principal
MODOS = ("sencillo", "avanzado")

POR_DEFECTO = {
    "consultar_isbn": True,          # permitir consultas por Internet al autocompletar
    "clave_google_books": "",        # opcional: clave propia de la API de Google Books
    "copias_a_conservar": 10,        # copias automáticas que se guardan al cerrar
    "copia_al_cerrar": True,
    "etiquetas_titulos": 6,          # títulos que se listan en cada etiqueta
    "ventana": "",                   # tamaño y posición de la ventana principal (base64)
    "tema": "claro",                 # 'claro', 'oscuro' o 'sistema'
    "escala": 1.0,                   # tamaño de la interfaz y de la letra (0.9 a 1.5)
    "fuente": "Segoe UI",            # tipo de letra de la interfaz
    "panel_detalle": True,           # mostrar el panel de detalle a la derecha
    "columnas_ocultas": [5],         # columnas de la lista ocultas (5 = Estado)
    "modo": "sencillo",              # 'sencillo' (menos campos y opciones) o 'avanzado' (todo)
}


def _booleano(valor):
    return valor if isinstance(valor, bool) else None


def _entero(minimo, maximo):
    def validar(valor):
        if isinstance(valor, bool) or not isinstance(valor, int):
            return None
        return min(max(valor, minimo), maximo)
    return validar


def _texto(maximo):
    def validar(valor):
        return valor[:maximo] if isinstance(valor, str) else None
    return validar


def _escala(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return min(ESCALAS_VALIDAS, key=lambda e: abs(e - float(valor)))  # la más cercana de las permitidas


def _tema(valor):
    return valor if valor in ("claro", "oscuro", "sistema") else None


def _modo(valor):
    return valor if valor in MODOS else None


def _fuente(valor):
    return valor.strip()[:80] if isinstance(valor, str) and valor.strip() else None


def _columnas(valor):
    if not isinstance(valor, list):
        return None
    return sorted({c for c in valor if isinstance(c, int) and not isinstance(c, bool) and 0 <= c < NUM_COLUMNAS and c != 1})


VALIDADORES = {
    "consultar_isbn": _booleano,
    "clave_google_books": _texto(200),
    "copias_a_conservar": _entero(1, 100),
    "copia_al_cerrar": _booleano,
    "etiquetas_titulos": _entero(0, 12),
    "ventana": _texto(4000),
    "tema": _tema,
    "escala": _escala,
    "fuente": _fuente,
    "panel_detalle": _booleano,
    "columnas_ocultas": _columnas,
    "modo": _modo,
}


def validar(datos: dict) -> dict:
    """Devuelve una copia con solo claves conocidas y valores válidos (el resto, por defecto)."""
    resultado = {}
    for clave, por_defecto in POR_DEFECTO.items():
        valor = VALIDADORES[clave](datos.get(clave)) if clave in datos else None
        resultado[clave] = valor if valor is not None else (list(por_defecto) if isinstance(por_defecto, list)
                                                             else por_defecto)
    return resultado


def cargar() -> dict:
    ruta = rutas.ruta_configuracion()
    leidos = {}
    if ruta.exists():
        try:
            contenido = json.loads(ruta.read_text(encoding="utf-8"))
            if isinstance(contenido, dict):
                leidos = contenido
        except (OSError, ValueError):
            pass  # un config.json dañado no debe impedir arrancar: se usan los valores por defecto
    return validar(leidos)


def guardar(datos: dict) -> None:
    """Escritura atómica: se escribe a un archivo provisional y se sustituye de golpe."""
    ruta = rutas.ruta_configuracion()
    provisional = ruta.with_suffix(".json.tmp")
    provisional.write_text(json.dumps(validar(datos), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(provisional, ruta)


def obtener(clave: str):
    return cargar()[clave]


def modo_avanzado() -> bool:
    """True si el usuario ha elegido el modo avanzado (por defecto se usa el sencillo)."""
    return obtener("modo") == "avanzado"
