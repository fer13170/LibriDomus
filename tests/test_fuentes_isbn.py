"""Fuentes de datos por ISBN: Agencia Española del ISBN, BNE, BnF y combinación con Open Library.

Las respuestas imitan la forma real de cada servicio (comprobada el 01/10/2026), sin Internet.
"""

import json

import pytest
from PySide6.QtWidgets import QApplication

from libridomus.datos import tipos
from libridomus.interfaz.ficha_elemento import FichaElemento
from libridomus.servicios import catalogos, isbn
from libridomus.servicios.isbn import DatosLibro

# ---------------------------------------------------------------- respuestas de ejemplo

FICHA_AGENCIA = """<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>
<p>Quiénes somos</p>
<div class="fichaISBN">
  <div class="cabecera"><span class="cabTitulo">ISBN 13: <strong>978-84-01-03992-8</strong></span></div>
  <table summary="Ficha">
    <tr><th scope="row">Título:</th><td><strong>El canto del cisne : Diana, mi hermana</strong></td></tr>
    <tr><th scope="row">Autor/es:</th><td>
      <span>	Spencer, Charles <a href="/webISBN/autoridadLista.do?x=1">[Ver títulos]</a></span>
      <span>	Canales Medina, Verónica ; tr. <a href="/webISBN/autoridadLista.do?x=2">[Ver títulos]</a></span>
      <span>	del Valle Peñamil, Efrén ; tr. <a href="/webISBN/autoridadLista.do?x=3">[Ver títulos]</a></span>
      <span>	GARCÍA DE LA TORRE, ANA ; il. <a href="/webISBN/autoridadLista.do?x=4">[Ver títulos]</a></span>
    </td></tr>
    <tr><th scope="row">Lengua de publicación:</th><td><span>Castellano</span></td></tr>
    <tr><th scope="row">Fecha Edición:</th><td>09/2026</td><!--<td>2026/09</td>--></tr>
    <tr><th scope="row">Publicación:</th><td><span><a href="/webISBN/editorialDetalle.do?x=5">Plaza &amp; Janés</a></span></td></tr>
    <tr><th scope="row">Descripción:</th><td>376 p.  24x15 cm </td></tr>
  </table>
</div></body></html>"""

RESULTADOS_AGENCIA = ('<a href="/webISBN/tituloDetalle.do?sidTitul=1&amp;action=busquedaInicial">'
                      '978-84-01-03992-8</a>')

MARC_BNE = """<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><numberOfRecords>1</numberOfRecords>
<records><record><recordData>
<record xmlns="http://www.loc.gov/MARC21/slim">
  <controlfield tag="008">250704s2025    sp a   | |||| 000 f spa  </controlfield>
  <datafield tag="100" ind1="1" ind2=" "><subfield code="a">Suárez, Gonzalo</subfield>
    <subfield code="d">1934-</subfield><subfield code="e">autor</subfield><subfield code="4">aut</subfield></datafield>
  <datafield tag="245" ind1="1" ind2="0"><subfield code="a">La suela de mis zapatos :</subfield>
    <subfield code="b">pasos y andanzas de Martín Girard</subfield></datafield>
  <datafield tag="264" ind1=" " ind2="1"><subfield code="b">Random House,</subfield><subfield code="c">[2025]</subfield></datafield>
  <datafield tag="300" ind1=" " ind2=" "><subfield code="a">271 páginas :</subfield></datafield>
  <datafield tag="700" ind1="1" ind2=" "><subfield code="a">Mendoza, Eduardo</subfield>
    <subfield code="e">prologuista</subfield><subfield code="4">aui</subfield></datafield>
  <datafield tag="700" ind1="1" ind2=" "><subfield code="a">Giménez, Paco</subfield></datafield>
</record></recordData></record></records></searchRetrieveResponse>"""

UNIMARC_BNF = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/"><srw:numberOfRecords>1</srw:numberOfRecords>
<srw:records><srw:record><srw:recordData>
<mxc:record xmlns:mxc="info:lc/xmlns/marcxchange-v2">
  <mxc:datafield tag="101"><mxc:subfield code="a">fre</mxc:subfield></mxc:datafield>
  <mxc:datafield tag="200"><mxc:subfield code="a">L'Étranger</mxc:subfield><mxc:subfield code="e">roman</mxc:subfield></mxc:datafield>
  <mxc:datafield tag="214"><mxc:subfield code="c">Gallimard</mxc:subfield><mxc:subfield code="d">1972</mxc:subfield></mxc:datafield>
  <mxc:datafield tag="215"><mxc:subfield code="a">1 vol. (186 p.)</mxc:subfield></mxc:datafield>
  <mxc:datafield tag="700"><mxc:subfield code="a">Camus</mxc:subfield><mxc:subfield code="b">Albert</mxc:subfield>
    <mxc:subfield code="4">070</mxc:subfield></mxc:datafield>
  <mxc:datafield tag="702"><mxc:subfield code="a">Dupont</mxc:subfield><mxc:subfield code="b">Jean</mxc:subfield>
    <mxc:subfield code="4">080</mxc:subfield></mxc:datafield>
</mxc:record></srw:recordData></srw:record></srw:records></srw:searchRetrieveResponse>"""

SIN_RESULTADOS_SRU = """<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
<numberOfRecords>0</numberOfRecords></searchRetrieveResponse>"""


@pytest.fixture
def internet(monkeypatch):
    """Simula Internet: cada prueba pone en ``respuestas`` lo que devuelve cada servicio."""
    respuestas: dict[str, bytes] = {}
    pedidas: list[str] = []

    def descargar(url, limite=None, datos=None, sesion=None):
        pedidas.append(url)
        for prefijo, contenido in respuestas.items():
            if url.startswith(prefijo):
                if isinstance(contenido, Exception):
                    raise contenido
                return contenido
        return None  # 404

    monkeypatch.setattr(isbn, "descargar", descargar)
    return respuestas, pedidas


def agencia(respuestas, ficha: str = FICHA_AGENCIA, resultados: str = RESULTADOS_AGENCIA):
    # La ficha mezcla codificaciones, como la web real: plantilla en UTF-8 y datos en Latin-1.
    plantilla, _, datos = ficha.partition('<div class="fichaISBN">')
    respuestas[catalogos.AGENCIA + "tituloSimpleFilter"] = b"<html></html>"
    respuestas[catalogos.AGENCIA + "tituloSimpleDispatch"] = resultados.encode("utf-8")
    respuestas[catalogos.AGENCIA + "tituloDetalle"] = (plantilla.encode("utf-8") + b'<div class="fichaISBN">'
                                                       + datos.encode("latin-1"))


# ---------------------------------------------------------------- lectura de cada fuente

def test_agencia_lee_la_ficha_con_codificacion_mezclada(internet):
    respuestas, _ = internet
    agencia(respuestas)
    d = catalogos.consultar_agencia("9788401039928")
    assert (d.titulo, d.subtitulo, d.autores) == ("El canto del cisne", "Diana, mi hermana", ["Charles Spencer"])
    assert d.traductores == ["Verónica Canales Medina", "Efrén del Valle Peñamil"]  # el ilustrador no
    assert (d.editorial, d.anio, d.paginas, d.idioma) == ("Plaza & Janés", 2026, 376, "Español")


def test_agencia_sin_resultados(internet):
    respuestas, _ = internet
    agencia(respuestas, resultados="<p>No se ha encontrado ningún resultado.</p>")
    assert catalogos.consultar_agencia("9791399016185") is None


def test_bne_marc21(internet):
    respuestas, _ = internet
    respuestas["https://catalogo.bne.es/"] = MARC_BNE.encode("utf-8")
    d = catalogos.consultar_bne("9788439745785")
    assert (d.titulo, d.subtitulo) == ("La suela de mis zapatos", "pasos y andanzas de Martín Girard")
    assert d.autores == ["Gonzalo Suárez"]  # ni el prologuista ni el 700 sin función
    assert (d.editorial, d.anio, d.paginas, d.idioma) == ("Random House", 2025, 271, "Español")


def test_bnf_unimarc(internet):
    respuestas, _ = internet
    respuestas["https://catalogue.bnf.fr/"] = UNIMARC_BNF.encode("utf-8")
    d = catalogos.consultar_bnf("9782070360024")
    assert (d.titulo, d.subtitulo, d.autores) == ("L'Étranger", "roman", ["Albert Camus"])
    assert (d.editorial, d.anio, d.paginas, d.idioma) == ("Gallimard", 1972, 186, "Francés")


def test_sru_sin_resultados_y_xml_roto(internet):
    respuestas, _ = internet
    respuestas["https://catalogo.bne.es/"] = SIN_RESULTADOS_SRU.encode()
    assert catalogos.consultar_bne("9788400000000") is None
    respuestas["https://catalogue.bnf.fr/"] = b"<esto no es xml"
    with pytest.raises(isbn.ErrorConsulta):
        catalogos.consultar_bnf("9782070360024")


@pytest.mark.parametrize("texto, esperado", [
    ("MARCO, EDUARDO", "Eduardo Marco"),
    ("Mallorquí, César", "César Mallorquí"),
    ("GARCÍA DE LA TORRE, ANA", "Ana García de la Torre"),
    ("del Valle Peñamil, Efrén", "Efrén del Valle Peñamil"),
    ("Suárez, Gonzalo, 1934-", "Gonzalo Suárez"),
    ("Charles Spencer", "Charles Spencer"),
])
def test_nombres_en_orden_natural(texto, esperado):
    assert catalogos.nombre_natural(texto) == esperado


# ---------------------------------------------------------------- orden y combinación

def nombres(codigo: str, clave: str = "") -> list[str]:
    return [n for n, _ in isbn.orden_fuentes(codigo, clave)]


def test_orden_de_fuentes_segun_el_pais_del_isbn():
    assert nombres("9788401039928") == ["Agencia del ISBN", "BNE", "Open Library", "BnF"]
    assert nombres("9791399124866")[0] == "Agencia del ISBN"            # 979-13: también España
    assert nombres("9782070360024") == ["BnF", "Open Library", "Agencia del ISBN", "BNE"]
    assert nombres("9791032100000")[0] == "BnF"                         # 979-10: Francia
    assert nombres("9780306406157") == ["Open Library", "Agencia del ISBN", "BNE", "BnF"]
    assert nombres("9780306406157", "CLAVE") == ["Open Library", "Google Books", "Agencia del ISBN", "BNE", "BnF"]


def test_se_completa_con_la_siguiente_fuente_y_se_busca_portada(internet):
    respuestas, pedidas = internet
    # La Agencia no tiene el libro; la BNE lo tiene sin autor (registro provisional); Open Library completa.
    agencia(respuestas, resultados="")
    respuestas["https://catalogo.bne.es/"] = MARC_BNE.replace(
        '<datafield tag="100"', '<datafield tag="999"').encode("utf-8")
    respuestas["https://openlibrary.org/isbn/9788439745785.json"] = json.dumps(
        {"title": "La suela", "authors": [{"key": "/authors/OL1A"}]}).encode()
    respuestas["https://openlibrary.org/authors/OL1A.json"] = json.dumps({"name": "Gonzalo Suárez"}).encode()
    respuestas["https://covers.openlibrary.org/b/isbn/9788439745785"] = b"JPEG"
    d = isbn.consultar("978-84-397-4578-5")
    assert d.titulo == "La suela de mis zapatos"  # el de la primera fuente que lo tiene
    assert d.autores == ["Gonzalo Suárez"] and d.editorial == "Random House"
    assert d.fuente == "BNE + Open Library" and d.portada == b"JPEG"
    assert not any("bnf.fr" in u for u in pedidas)  # ya estaba completo: no hace falta seguir


def test_con_clave_de_google_se_pide_la_portada_que_falta(internet):
    respuestas, pedidas = internet
    agencia(respuestas)  # la Agencia lo tiene completo, pero sin portada
    respuestas["https://www.googleapis.com/books/v1/volumes"] = json.dumps({"items": [{"volumeInfo": {
        "title": "El canto del cisne", "imageLinks": {"thumbnail": "http://books.google.com/portada"}}}]}).encode()
    respuestas["https://books.google.com/portada"] = b"JPEG"
    d = isbn.consultar("9788401039928", "CLAVE")
    assert (d.titulo, d.editorial, d.portada) == ("El canto del cisne", "Plaza & Janés", b"JPEG")
    assert d.fuente == "Agencia del ISBN + Google Books"
    assert not any("bne.es" in u for u in pedidas)  # los datos ya estaban completos
    respuestas.pop("https://www.googleapis.com/books/v1/volumes")
    assert isbn.consultar("9788401039928").portada is None  # sin clave no se pregunta a Google


def test_una_fuente_caida_no_impide_las_demas(internet):
    respuestas, _ = internet
    respuestas[catalogos.AGENCIA] = isbn.ErrorConsulta("caída")
    respuestas["https://catalogo.bne.es/"] = MARC_BNE.encode("utf-8")
    assert isbn.consultar("9788439745785").fuente == "BNE"


def test_sin_conexion_en_ninguna_fuente_da_error(internet):
    respuestas, _ = internet
    respuestas["https://"] = isbn.ErrorConsulta("No hay conexión a Internet o el servicio no responde.")
    with pytest.raises(isbn.ErrorConsulta):
        isbn.consultar("9788439745785")


def test_titulo_estropeado_en_open_library_se_corrige_con_la_obra(internet):
    respuestas, _ = internet
    respuestas["https://openlibrary.org/isbn/9781593276034.json"] = json.dumps(
        {"title": "lol", "works": [{"key": "/works/OL1W"}]}).encode()
    respuestas["https://openlibrary.org/works/OL1W.json"] = json.dumps(
        {"title": "Python crash course", "authors": [{"author": {"key": "/authors/OL2A"}}]}).encode()
    respuestas["https://openlibrary.org/authors/OL2A.json"] = json.dumps({"name": "Eric Matthes"}).encode()
    d = isbn.consultar("1-593-27603-6")
    assert (d.titulo, d.autores) == ("Python crash course", ["Eric Matthes"])


# ---------------------------------------------------------------- ficha

def test_la_ficha_anade_los_traductores_con_su_papel(con):
    QApplication.instance() or QApplication([])
    libro = next(t.id for t in tipos.listar(con, con_campos=False) if t.nombre == "Libro")
    f = FichaElemento(con, tipo_id=libro)
    f.aplicar_datos_isbn(DatosLibro(isbn="9788401039928", titulo="El canto del cisne", autores=["Charles Spencer"],
                                    traductores=["Verónica Canales Medina"]))
    assert f.personas.valor() == [("Charles Spencer", "Autor"), ("Verónica Canales Medina", "Traductor")]
