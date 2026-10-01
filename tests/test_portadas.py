"""Versión 1.4: portadas buscadas por título y autor (cuando el ISBN no trae portada)."""

import json

import pytest
from PySide6.QtWidgets import QApplication

from libridomus.datos import tipos
from libridomus.interfaz import comun
from libridomus.interfaz.ficha_elemento import FichaElemento
from libridomus.interfaz.panel_portada import PanelPortada
from libridomus.servicios import isbn


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mensajes(monkeypatch):
    registro = []
    monkeypatch.setattr(comun, "aviso", lambda _p, m: registro.append(("aviso", m)))
    monkeypatch.setattr(comun, "error", lambda _p, m: registro.append(("error", m)))
    return registro


@pytest.fixture
def en_el_acto(monkeypatch):
    """Las tareas en segundo plano se ejecutan al momento."""
    def ejecutar(funcion, ok, ko):
        try:
            resultado = funcion()
        except Exception as error:  # noqa: BLE001
            ko(error)
        else:
            ok(resultado)
    monkeypatch.setattr(comun, "en_segundo_plano", ejecutar)


def libro(con) -> int:
    return tipos.por_nombre(con, "Libro").id


@pytest.fixture
def internet(monkeypatch):
    respuestas: dict[str, object] = {}
    pedidas: list[str] = []

    def descargar(url, limite=None, datos=None, sesion=None):
        pedidas.append(url)
        for prefijo, contenido in respuestas.items():
            if url.startswith(prefijo):
                if isinstance(contenido, Exception):
                    raise contenido
                return contenido
        return None
    monkeypatch.setattr(isbn, "descargar", descargar)
    return respuestas, pedidas


def test_buscar_portada_por_titulo_prefiere_edicion_en_castellano(internet):
    respuestas, pedidas = internet
    respuestas["https://openlibrary.org/search.json"] = json.dumps({"docs": [
        {"cover_i": 11, "language": ["eng"]}, {"language": ["spa"]}, {"cover_i": 22, "language": ["spa"]}]}).encode()
    respuestas["https://covers.openlibrary.org/b/id/22-L.jpg"] = b"ES"
    assert isbn.buscar_portada("La inquilina", ["Freida McFadden"]) == b"ES"
    assert "author=Freida+McFadden" in pedidas[0]


def test_buscar_portada_con_google_primero_si_hay_clave(internet):
    respuestas, pedidas = internet
    respuestas["https://www.googleapis.com/books/v1/volumes"] = json.dumps({"items": [
        {"volumeInfo": {}}, {"volumeInfo": {"imageLinks": {"thumbnail": "http://books.google.com/x"}}}]}).encode()
    respuestas["https://books.google.com/x"] = b"G"
    assert isbn.buscar_portada("La inquilina", [], "CLAVE") == b"G"
    assert not any("openlibrary" in u for u in pedidas)


def test_buscar_portada_sin_resultados_y_sin_conexion(internet):
    respuestas, _ = internet
    assert isbn.buscar_portada("Nada", []) is None
    assert isbn.buscar_portada("   ", []) is None
    respuestas["https://"] = isbn.ErrorConsulta("sin red")
    with pytest.raises(isbn.ErrorConsulta):
        isbn.buscar_portada("Algo", [])


def test_consulta_por_isbn_busca_la_portada_por_titulo_al_final(internet):
    respuestas, _ = internet
    respuestas["https://openlibrary.org/isbn/9780306406157.json"] = json.dumps({"title": "Error coding"}).encode()
    respuestas["https://openlibrary.org/search.json"] = json.dumps({"docs": [{"cover_i": 5}]}).encode()
    respuestas["https://covers.openlibrary.org/b/id/5-L.jpg"] = b"P"
    d = isbn.consultar("0-306-40615-2")
    assert d.portada == b"P" and d.portada_por_titulo


def test_boton_buscar_portada_de_la_ficha(app, con, mensajes, en_el_acto, monkeypatch):
    monkeypatch.setattr(isbn, "buscar_portada", lambda t, a, c: b"" if t == "Nada" else None)
    f = FichaElemento(con, tipo_id=libro(con))
    assert f.portada.b_buscar.isVisibleTo(f)
    assert not f.portada.buscar()  # sin título
    assert "Escribe primero el título" in mensajes[-1][1]
    f.titulo.setText("Libro raro")
    assert f.portada.buscar()
    assert "No se ha encontrado ninguna portada" in mensajes[-1][1]
    assert f.portada.b_buscar.isEnabled()


def test_panel_portada_sin_busqueda_no_muestra_el_boton(app):
    p = PanelPortada()
    assert not p.b_buscar.isVisibleTo(p)
