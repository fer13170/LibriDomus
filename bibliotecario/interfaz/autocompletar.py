"""Autocompletar por ISBN desde la interfaz (común a la ficha y al alta masiva)."""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget

from ..servicios import configuracion, isbn
from ..servicios.isbn import DatosLibro, ErrorConsulta
from . import comun


def consultar(padre: QWidget, texto: str, al_encontrar: Callable[[DatosLibro], None],
              al_acabar: Callable[[bool], None] = lambda _vigente: None,
              texto_actual: Callable[[], str] | None = None) -> bool:
    """Lanza la consulta en segundo plano. Devuelve False si ni siquiera se ha lanzado.

    ``texto_actual`` devuelve lo que hay escrito en el campo del ISBN cuando llega la respuesta:
    si ya no es el ISBN consultado (el usuario ha pasado a otro elemento), la respuesta se
    descarta en silencio. ``al_acabar(vigente)`` se llama siempre al terminar.
    """
    consultado = isbn.validar(texto)
    if consultado is None:
        comun.error(padre, "El ISBN no es válido. Revisa las cifras (10 o 13, la última puede ser X).")
        return False
    ajustes = configuracion.cargar()
    if not ajustes["consultar_isbn"]:
        comun.aviso(padre, "La consulta por Internet está desactivada en Archivo › Preferencias.")
        return False

    def vigente() -> bool:
        return texto_actual is None or isbn.validar(texto_actual()) == consultado

    def terminado(datos: DatosLibro | None):
        sigue = vigente()
        al_acabar(sigue)
        if not sigue:
            return
        if datos is None:
            comun.aviso(padre, "No se ha encontrado este ISBN en las fuentes consultadas.\n"
                               "Puedes rellenar los datos a mano.")
        else:
            al_encontrar(datos)

    def fallido(error: Exception):
        sigue = vigente()
        al_acabar(sigue)
        if not sigue:
            return
        if isinstance(error, (ErrorConsulta, ValueError)):
            comun.aviso(padre, f"{error}\nPuedes rellenar los datos a mano.")
        else:
            comun.error(padre, f"Error inesperado al consultar el ISBN: {error}")

    comun.en_segundo_plano(lambda: isbn.consultar(texto, ajustes["clave_google_books"]), terminado, fallido)
    return True
