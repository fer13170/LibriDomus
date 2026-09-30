"""Preferencias del programa, guardadas en datos/config.json."""

import json

from .. import rutas

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
}


def cargar() -> dict:
    datos = dict(POR_DEFECTO)
    ruta = rutas.ruta_configuracion()
    if ruta.exists():
        try:
            leidos = json.loads(ruta.read_text(encoding="utf-8"))
            if isinstance(leidos, dict):
                datos.update({k: v for k, v in leidos.items() if k in POR_DEFECTO})
        except (OSError, ValueError):
            pass  # un config.json dañado no debe impedir arrancar: se usan los valores por defecto
    return datos


def guardar(datos: dict) -> None:
    limpio = {k: datos.get(k, v) for k, v in POR_DEFECTO.items()}
    rutas.ruta_configuracion().write_text(json.dumps(limpio, ensure_ascii=False, indent=2), encoding="utf-8")


def obtener(clave: str):
    return cargar()[clave]
