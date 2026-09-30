"""Validación de ISBN y consulta opcional de datos por Internet.

Fuentes (ver docs/Fase0_informe.md):
  1. Open Library: https://openlibrary.org/isbn/{isbn}.json (registro de la edición)
     y /authors/{clave}.json para los nombres de los autores. No requiere clave.
  2. Google Books, solo si se ha configurado una clave propia (sin clave la cuota
     compartida suele estar agotada y responde 429).
Si no hay conexión se lanza ErrorConsulta y el usuario sigue rellenando a mano.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .. import VERSION

AGENTE = f"LibriDomus/{VERSION} (catalogo domestico)"
TIEMPO_MAXIMO = 12  # segundos por petición

IDIOMAS_OPEN_LIBRARY = {
    "spa": "Español", "eng": "Inglés", "cat": "Catalán", "glg": "Gallego", "baq": "Euskera",
    "eus": "Euskera", "fre": "Francés", "fra": "Francés", "ger": "Alemán", "deu": "Alemán",
    "ita": "Italiano", "por": "Portugués", "lat": "Latín",
}
IDIOMAS_ISO2 = {"es": "Español", "en": "Inglés", "ca": "Catalán", "gl": "Gallego", "eu": "Euskera",
                "fr": "Francés", "de": "Alemán", "it": "Italiano", "pt": "Portugués", "la": "Latín"}


class ErrorConsulta(Exception):
    """No se ha podido consultar (sin conexión, servicio caído...)."""


@dataclass
class DatosLibro:
    isbn: str
    titulo: str = ""
    subtitulo: str = ""
    autores: list[str] = field(default_factory=list)
    editorial: str = ""
    anio: int | None = None
    paginas: int | None = None
    idioma: str = ""
    portada: bytes | None = None
    fuente: str = ""


# ---------------------------------------------------------------- validación

def normalizar(texto: str) -> str:
    return re.sub(r"[^0-9Xx]", "", texto or "").upper()


def es_isbn10(codigo: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", codigo):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(codigo))
    return total % 11 == 0


def es_isbn13(codigo: str) -> bool:
    if not re.fullmatch(r"\d{13}", codigo):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(codigo))
    return total % 10 == 0


def isbn10_a_13(codigo: str) -> str:
    base = "978" + codigo[:9]
    control = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base)) % 10) % 10
    return base + str(control)


def validar(texto: str) -> str | None:
    """Devuelve el ISBN-13 si el texto es un ISBN válido (10 o 13 cifras); si no, None."""
    codigo = normalizar(texto)
    if es_isbn13(codigo) and codigo.startswith(("978", "979")):
        return codigo
    if es_isbn10(codigo):
        return isbn10_a_13(codigo)
    return None


# ---------------------------------------------------------------- red

TAMANO_MAXIMO = 5 * 2**20  # bytes: ninguna respuesta legítima (JSON o portada) se acerca a esto


class _SoloHttps(urllib.request.HTTPRedirectHandler):
    """urllib sigue por defecto redirecciones a http:// (sin cifrar). Aquí se rechazan."""

    def redirect_request(self, req, fp, code, msg, headers, nueva_url):
        if urllib.parse.urlparse(nueva_url).scheme != "https":
            raise ErrorConsulta("El servicio ha intentado redirigir a una dirección no segura; se ha cancelado.")
        return super().redirect_request(req, fp, code, msg, headers, nueva_url)


_ABRIDOR = urllib.request.build_opener(_SoloHttps)


def descargar(url: str, limite: int = TAMANO_MAXIMO) -> bytes | None:
    """GET de una URL HTTPS. Devuelve None si el recurso no existe (404).

    Rechaza direcciones y redirecciones que no sean HTTPS y respuestas de más de ``limite`` bytes.
    Las pruebas sustituyen esta función para no depender de Internet.
    """
    if urllib.parse.urlparse(url).scheme != "https":
        raise ErrorConsulta("Solo se consultan direcciones seguras (https).")
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with _ABRIDOR.open(peticion, timeout=TIEMPO_MAXIMO) as respuesta:
            datos = respuesta.read(limite + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code == 429:
            raise ErrorConsulta("El servicio está recibiendo demasiadas consultas; inténtalo más tarde.") from error
        raise ErrorConsulta(f"El servicio ha respondido con un error ({error.code}).") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ErrorConsulta("No hay conexión a Internet o el servicio no responde.") from error
    if len(datos) > limite:
        raise ErrorConsulta("La respuesta del servicio es demasiado grande; se ha descartado.")
    return datos


def _json(url: str) -> dict | None:
    datos = descargar(url)
    if datos is None:
        return None
    try:
        contenido = json.loads(datos.decode("utf-8"))
    except ValueError as error:
        raise ErrorConsulta("Respuesta no válida del servicio.") from error
    if not isinstance(contenido, dict):
        raise ErrorConsulta("Respuesta no válida del servicio.")
    return contenido


# Lectura defensiva: el servicio podría devolver tipos inesperados (una lista donde se espera
# un texto, un objeto donde se espera una lista...). Nunca debe provocar un error del programa.

def _texto(valor) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _dic(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _anio(texto: str) -> int | None:
    encontrado = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", texto if isinstance(texto, str) else "")
    return int(encontrado.group(1)) if encontrado else None


_CLAVE_AUTOR = re.compile(r"^/authors/OL\d+A$")
_CLAVE_OBRA = re.compile(r"^/works/OL\d+W$")


def consultar_open_library(isbn: str) -> DatosLibro | None:
    edicion = _json(f"https://openlibrary.org/isbn/{isbn}.json")
    if not edicion or not _texto(edicion.get("title")):
        return None
    datos = DatosLibro(isbn=isbn, fuente="Open Library")
    datos.titulo = _texto(edicion.get("title"))
    datos.subtitulo = _texto(edicion.get("subtitle"))
    editoriales = [_texto(e) for e in _lista(edicion.get("publishers")) if _texto(e)]
    datos.editorial = editoriales[0] if editoriales else ""
    datos.anio = _anio(edicion.get("publish_date"))
    paginas = edicion.get("number_of_pages")
    datos.paginas = paginas if isinstance(paginas, int) and not isinstance(paginas, bool) and paginas > 0 else None
    idiomas = _lista(edicion.get("languages"))
    if idiomas:
        clave = _texto(_dic(idiomas[0]).get("key")).rsplit("/", 1)[-1]
        datos.idioma = IDIOMAS_OPEN_LIBRARY.get(clave, "")

    # Solo claves con la forma esperada: así nunca se construye una dirección extraña.
    claves = [_texto(_dic(a).get("key")) for a in _lista(edicion.get("authors"))]
    claves = [c for c in claves if _CLAVE_AUTOR.match(c)]
    obras = [_texto(_dic(o).get("key")) for o in _lista(edicion.get("works"))]
    obras = [o for o in obras if _CLAVE_OBRA.match(o)]
    if not claves and obras:
        obra = _json(f"https://openlibrary.org{obras[0]}.json") or {}
        claves = [_texto(_dic(_dic(a).get("author")).get("key")) for a in _lista(obra.get("authors"))]
        claves = [c for c in claves if _CLAVE_AUTOR.match(c)]
    for clave in claves[:6]:
        nombre = _texto((_json(f"https://openlibrary.org{clave}.json") or {}).get("name"))
        if nombre:
            datos.autores.append(nombre)

    portadas = [c for c in _lista(edicion.get("covers")) if isinstance(c, int) and not isinstance(c, bool) and c > 0]
    # Si la edición no trae portada se prueba la API de portadas por ISBN
    # (con default=false responde 404 en lugar de una imagen vacía).
    url = (f"https://covers.openlibrary.org/b/id/{portadas[0]}-L.jpg" if portadas
           else f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false")
    try:
        datos.portada = descargar(url)
    except ErrorConsulta:
        datos.portada = None  # sin portada no es motivo para perder el resto
    return datos


def consultar_google_books(isbn: str, clave: str) -> DatosLibro | None:
    parametros = urllib.parse.urlencode({"q": f"isbn:{isbn}", "key": clave})
    respuesta = _json(f"https://www.googleapis.com/books/v1/volumes?{parametros}") or {}
    elementos = _lista(respuesta.get("items"))
    if not elementos:
        return None
    info = _dic(_dic(elementos[0]).get("volumeInfo"))
    datos = DatosLibro(isbn=isbn, fuente="Google Books")
    datos.titulo = _texto(info.get("title"))
    datos.subtitulo = _texto(info.get("subtitle"))
    datos.autores = [_texto(a) for a in _lista(info.get("authors")) if _texto(a)]
    datos.editorial = _texto(info.get("publisher"))
    datos.anio = _anio(info.get("publishedDate"))
    paginas = info.get("pageCount")
    datos.paginas = paginas if isinstance(paginas, int) and not isinstance(paginas, bool) and paginas > 0 else None
    datos.idioma = IDIOMAS_ISO2.get(_texto(info.get("language")), "")
    imagen = _texto(_dic(info.get("imageLinks")).get("thumbnail"))
    if imagen:
        try:
            datos.portada = descargar(imagen.replace("http://", "https://", 1))
        except ErrorConsulta:
            datos.portada = None
    return datos if datos.titulo else None


def consultar(texto_isbn: str, clave_google: str = "") -> DatosLibro | None:
    """Busca los datos de un ISBN. None si no se encuentra; ErrorConsulta si no se pudo consultar."""
    isbn = validar(texto_isbn)
    if isbn is None:
        raise ValueError("El ISBN no es válido (revisa las cifras).")
    try:
        datos = consultar_open_library(isbn)
        if datos is None and clave_google.strip():
            datos = consultar_google_books(isbn, clave_google.strip())
    except (TypeError, AttributeError, KeyError, IndexError, ValueError) as error:
        # Última red de seguridad ante una respuesta con una forma que no se ha previsto.
        raise ErrorConsulta("El servicio ha devuelto datos no válidos.") from error
    return datos
