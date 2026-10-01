"""Consultas por ISBN a catálogos nacionales (gratuitos y sin clave).

- Agencia Española del ISBN (Ministerio de Cultura): todos los libros con ISBN español desde
  1972, incluidos los recién publicados, porque los datos los da la editorial al pedir el ISBN.
  Es una página web con formulario (no una API): búsqueda con sesión + ficha en HTML.
  https://www.cultura.gob.es/webISBN/tituloSimpleFilter.do
- Biblioteca Nacional de España (BNE): catálogo en MARC21 por SRU.
  https://catalogo.bne.es/view/sru/34BNE_INST
- Bibliothèque nationale de France (BnF): catálogo en UNIMARC por SRU.
  https://api.bnf.fr/fr/api-sru-catalogue-general

Cada función devuelve un DatosLibro (sin portada: estos catálogos no las ofrecen) o None si
el ISBN no está. Los fallos de red se propagan como isbn.ErrorConsulta.
Todas las descargas pasan por isbn.descargar (solo HTTPS, tamaño limitado).
"""

import codecs
import html
import http.cookiejar
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import isbn
from .isbn import DatosLibro

# ---------------------------------------------------------------- utilidades comunes

# Lenguas tal como las escriben los catálogos -> como las guarda LibriDomus
IDIOMAS_TEXTO = {"castellano": "Español", "español": "Español", "catalán": "Catalán", "catala": "Catalán",
                 "gallego": "Gallego", "euskera": "Euskera", "vasco": "Euskera", "valenciano": "Catalán",
                 "inglés": "Inglés", "francés": "Francés", "alemán": "Alemán", "italiano": "Italiano",
                 "portugués": "Portugués", "latín": "Latín"}

PARTICULAS = {"de", "del", "la", "las", "los", "y", "e", "i", "da", "das", "do", "dos", "van", "von", "der",
              "di", "du", "le", "les"}

# Códigos de función de MARC/UNIMARC que indican autoría (el resto: traductor, prologuista...)
ROLES_AUTOR = {"", "aut", "autor", "autora", "070", "author"}
ROLES_TRADUCTOR = {"trl", "tr", "tr.", "trad", "trad.", "traductor", "traductora", "730", "translator"}


def limpiar(texto: str) -> str:
    """Quita la puntuación final de los catálogos ('Edebé,' -> 'Edebé', 'Título :' -> 'Título')."""
    return re.sub(r"[\s/:;,=.]+$", "", re.sub(r"\s+", " ", texto or "")).strip()


def _capitalizar(palabra: str, primera: bool) -> str:
    if not primera and palabra.lower() in PARTICULAS:
        return palabra.lower()
    return "-".join(p[:1].upper() + p[1:].lower() for p in palabra.split("-"))


def nombre_natural(texto: str) -> str:
    """'MARCO, EDUARDO' -> 'Eduardo Marco'; 'Mallorquí, César' -> 'César Mallorquí'."""
    texto = limpiar(re.sub(r"\(.*?\)|\d{4}-(\d{4})?", "", texto or ""))  # sin fechas ni aclaraciones
    if "," in texto:
        apellidos, nombre = (p.strip() for p in texto.split(",", 1))
        texto = f"{nombre} {apellidos}".strip()
    if texto.isupper() or texto.islower():
        texto = " ".join(_capitalizar(p, i == 0) for i, p in enumerate(texto.split()))
    return texto


def _numero(patron: str, texto: str) -> int | None:
    m = re.search(patron, texto or "")
    return int(m.group(1)) if m else None


def _paginas(texto: str) -> int | None:
    n = _numero(r"(\d+)\s*(?:p\b|págs?|pp)", texto)
    return n if n and 0 < n < 20000 else None


def _nombre_unico(lista: list[str], nombre: str) -> None:
    if nombre and nombre.casefold() not in (x.casefold() for x in lista):
        lista.append(nombre)


# ---------------------------------------------------------------- Agencia Española del ISBN

AGENCIA = "https://www.cultura.gob.es/webISBN/"


def _byte_suelto_como_cp1252(error: UnicodeDecodeError):
    """Las páginas de la Agencia mezclan codificaciones: la plantilla va en UTF-8 y los datos
    del libro en Latin-1 / Windows-1252. Lo que no es UTF-8 válido se lee como Windows-1252."""
    trozo = error.object[error.start:error.end]
    return trozo.decode("cp1252", "replace"), error.end


codecs.register_error("libridomus_cp1252", _byte_suelto_como_cp1252)


def _decodificar(datos: bytes | None) -> str:
    return (datos or b"").decode("utf-8", "libridomus_cp1252")


def consultar_agencia(codigo: str) -> DatosLibro | None:
    sesion = http.cookiejar.CookieJar()  # la búsqueda solo funciona dentro de una sesión
    isbn.descargar(AGENCIA + "tituloSimpleFilter.do?cache=init&prev_layout=busquedaisbn&layout=busquedaisbn"
                   "&language=es", sesion=sesion)
    campos = {"params.forzaQuery": "N", "params.cdispo": "A", "params.cisbnExt": codigo,
              "params.liConceptosExt[0].texto": "", "params.orderByFormId": "1", "action": "Buscar",
              "language": "es", "prev_layout": "busquedaisbn", "layout": "busquedaisbn"}
    resultados = isbn.descargar(AGENCIA + "tituloSimpleDispatch.do", sesion=sesion,
                                datos=urllib.parse.urlencode(campos).encode("ascii"))
    enlaces = re.findall(r'href="(/webISBN/tituloDetalle\.do\?[^"]+)"', _decodificar(resultados))
    if not enlaces:
        return None
    ficha = isbn.descargar(urllib.parse.urljoin(AGENCIA, html.unescape(enlaces[0])), sesion=sesion)
    return leer_ficha_agencia(_decodificar(ficha), codigo)


def _texto_html(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def leer_ficha_agencia(pagina: str, codigo: str) -> DatosLibro | None:
    """Lee la tabla <th>Campo:</th><td>valor</td> de la ficha de un título."""
    inicio = pagina.find('class="fichaISBN"')
    if inicio < 0:
        return None
    filas = {}
    for th, td in re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", pagina[inicio:], re.S):
        filas.setdefault(_texto_html(th).rstrip(":").casefold(), td)
    titulo = limpiar(_texto_html(filas.get("título", "")))
    if not titulo:
        return None
    titulo, _, subtitulo = titulo.partition(" : ")  # 'El canto del cisne : Diana, mi hermana'
    datos = DatosLibro(isbn=codigo, titulo=titulo.strip(), subtitulo=subtitulo.strip(), fuente="Agencia del ISBN")
    for span in re.findall(r"<span[^>]*>(.*?)</span>", filas.get("autor/es", ""), re.S):
        partes = [p.strip() for p in _texto_html(re.sub(r"<a .*?</a>", "", span, flags=re.S)).split(";")]
        nombre, rol = nombre_natural(partes[0]), (partes[1] if len(partes) > 1 else "").casefold()
        if rol in ROLES_TRADUCTOR:
            _nombre_unico(datos.traductores, nombre)
        elif rol in ROLES_AUTOR:
            _nombre_unico(datos.autores, nombre)
    editorial = re.findall(r"<span[^>]*>(.*?)</span>", filas.get("publicación", ""), re.S)
    datos.editorial = limpiar(_texto_html(editorial[0])) if editorial else ""
    datos.anio = _numero(r"\b(1[5-9]\d\d|20\d\d)\b", _texto_html(filas.get("fecha edición", "")))
    datos.paginas = _paginas(_texto_html(filas.get("descripción", "")))
    lengua = _texto_html(filas.get("lengua de publicación", "")).split(",")[0].strip().casefold()
    datos.idioma = IDIOMAS_TEXTO.get(lengua, "")
    # Materias con código Thema / BIC: 'FH - Obra De Misterio Y Suspense'
    datos.materias = [_texto_html(m) for m in re.findall(r"<span[^>]*>(.*?)</span>", filas.get("materia/s", ""), re.S)]
    return datos


# ---------------------------------------------------------------- MARC21 (BNE) y UNIMARC (BnF)

def _registros(xml: bytes) -> list[ET.Element]:
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as error:
        raise isbn.ErrorConsulta("Respuesta no válida del catálogo.") from error
    return [e for e in raiz.iter() if e.tag.rsplit("}", 1)[-1] == "record"
            and any(c.tag.rsplit("}", 1)[-1] == "datafield" for c in e)]


class _Marc:
    """Acceso sencillo a los campos de un registro MARCXML (vale para MARC21 y UNIMARC)."""

    def __init__(self, registro: ET.Element):
        self.campos = [c for c in registro if c.tag.rsplit("}", 1)[-1] in ("datafield", "controlfield")]

    def control(self, etiqueta: str) -> str:
        return next((c.text or "" for c in self.campos if c.get("tag") == etiqueta and c.tag.endswith("controlfield")), "")

    def todos(self, etiqueta: str) -> list[dict[str, list[str]]]:
        resultado = []
        for c in self.campos:
            if c.get("tag") == etiqueta and c.tag.endswith("datafield"):
                subcampos: dict[str, list[str]] = {}
                for s in c:
                    subcampos.setdefault(s.get("code", ""), []).append((s.text or "").strip())
                resultado.append(subcampos)
        return resultado

    def uno(self, etiqueta: str, codigo: str) -> str:
        for campo in self.todos(etiqueta):
            if campo.get(codigo):
                return campo[codigo][0]
        return ""


def consultar_bne(codigo: str) -> DatosLibro | None:
    url = "https://catalogo.bne.es/view/sru/34BNE_INST?" + urllib.parse.urlencode({
        "version": "1.2", "operation": "searchRetrieve", "query": f'alma.isbn="{codigo}"',
        "recordSchema": "marcxml", "maximumRecords": "1"})
    respuesta = isbn.descargar(url)
    registros = _registros(respuesta) if respuesta else []
    return leer_marc21(registros[0], codigo) if registros else None


def leer_marc21(registro: ET.Element, codigo: str) -> DatosLibro | None:
    m = _Marc(registro)
    titulo = limpiar(m.uno("245", "a"))
    if not titulo:
        return None
    datos = DatosLibro(isbn=codigo, titulo=titulo, subtitulo=limpiar(m.uno("245", "b")), fuente="BNE")
    _nombre_unico(datos.autores, nombre_natural(m.uno("100", "a")))
    for campo in m.todos("700"):
        rol = " ".join(campo.get("e", []) + campo.get("4", [])).casefold().strip(" .,")
        nombre = nombre_natural((campo.get("a") or [""])[0])
        if any(r in rol for r in ("trad", "trl")):
            _nombre_unico(datos.traductores, nombre)
        elif "aut" in rol.split() or rol in ROLES_AUTOR - {""}:
            # Sin función indicada no se da por autor: en los registros antiguos de la BNE así
            # aparecen también ilustradores y editores (p. ej. el ilustrador de 9788423675104).
            _nombre_unico(datos.autores, nombre)
    datos.editorial = limpiar(m.uno("264", "b") or m.uno("260", "b"))
    fijo = m.control("008")
    datos.anio = (_numero(r"\b(1[5-9]\d\d|20\d\d)\b", m.uno("264", "c") or m.uno("260", "c"))
                  or _numero(r"^(1[5-9]\d\d|20\d\d)$", fijo[7:11]))
    datos.paginas = _paginas(m.uno("300", "a"))
    lengua = (m.uno("041", "a") or fijo[35:38]).lower()
    datos.idioma = isbn.IDIOMAS_OPEN_LIBRARY.get(lengua, "")
    # Género/forma (655: 'Novelas rosas') y materias (650: 'Historia')
    datos.materias = [limpiar(a) for etiqueta in ("655", "650") for campo in m.todos(etiqueta)
                      for a in campo.get("a", []) if limpiar(a)]
    return datos


def consultar_bnf(codigo: str) -> DatosLibro | None:
    url = "https://catalogue.bnf.fr/api/SRU?" + urllib.parse.urlencode({
        "version": "1.2", "operation": "searchRetrieve", "query": f'bib.isbn all "{codigo}"',
        "recordSchema": "unimarcxchange", "maximumRecords": "1"})
    respuesta = isbn.descargar(url)
    registros = _registros(respuesta) if respuesta else []
    return leer_unimarc(registros[0], codigo) if registros else None


def leer_unimarc(registro: ET.Element, codigo: str) -> DatosLibro | None:
    m = _Marc(registro)
    titulo = limpiar(m.uno("200", "a"))
    if not titulo:
        return None
    datos = DatosLibro(isbn=codigo, titulo=titulo, subtitulo=limpiar(m.uno("200", "e")), fuente="BnF")
    for etiqueta in ("700", "701", "702"):
        for campo in m.todos(etiqueta):
            apellido, nombre = (campo.get("a") or [""])[0], (campo.get("b") or [""])[0]
            completo = nombre_natural(f"{apellido}, {nombre}" if nombre else apellido)
            funcion = (campo.get("4") or [""])[0]
            if funcion in ROLES_TRADUCTOR:
                _nombre_unico(datos.traductores, completo)
            elif funcion in ROLES_AUTOR:
                _nombre_unico(datos.autores, completo)
    datos.editorial = limpiar(m.uno("214", "c") or m.uno("210", "c"))
    datos.anio = _numero(r"\b(1[5-9]\d\d|20\d\d)\b", m.uno("214", "d") or m.uno("210", "d"))
    datos.paginas = _paginas(m.uno("215", "a"))
    datos.idioma = isbn.IDIOMAS_OPEN_LIBRARY.get(m.uno("101", "a").lower(), "")
    datos.materias = [limpiar(a) for etiqueta in ("608", "606") for campo in m.todos(etiqueta)
                      for a in campo.get("a", []) if limpiar(a)]
    return datos
