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

def descargar(url: str) -> bytes | None:
    """GET de una URL. Devuelve None si el recurso no existe (404).

    Las pruebas sustituyen esta función para no depender de Internet.
    """
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_MAXIMO) as respuesta:
            return respuesta.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code == 429:
            raise ErrorConsulta("El servicio está recibiendo demasiadas consultas; inténtalo más tarde.") from error
        raise ErrorConsulta(f"El servicio ha respondido con un error ({error.code}).") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ErrorConsulta("No hay conexión a Internet o el servicio no responde.") from error


def _json(url: str) -> dict | None:
    datos = descargar(url)
    if datos is None:
        return None
    try:
        return json.loads(datos.decode("utf-8"))
    except ValueError as error:
        raise ErrorConsulta("Respuesta no válida del servicio.") from error


def _anio(texto: str) -> int | None:
    encontrado = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", texto or "")
    return int(encontrado.group(1)) if encontrado else None


def consultar_open_library(isbn: str) -> DatosLibro | None:
    edicion = _json(f"https://openlibrary.org/isbn/{isbn}.json")
    if not edicion or not edicion.get("title"):
        return None
    datos = DatosLibro(isbn=isbn, fuente="Open Library")
    datos.titulo = edicion.get("title", "").strip()
    datos.subtitulo = edicion.get("subtitle", "").strip()
    editoriales = edicion.get("publishers") or []
    datos.editorial = editoriales[0].strip() if editoriales else ""
    datos.anio = _anio(edicion.get("publish_date", ""))
    paginas = edicion.get("number_of_pages")
    datos.paginas = paginas if isinstance(paginas, int) and paginas > 0 else None
    idiomas = edicion.get("languages") or []
    if idiomas:
        clave = idiomas[0].get("key", "").rsplit("/", 1)[-1]
        datos.idioma = IDIOMAS_OPEN_LIBRARY.get(clave, "")

    claves = [a.get("key") for a in edicion.get("authors", []) if a.get("key")]
    if not claves and edicion.get("works"):
        obra = _json(f"https://openlibrary.org{edicion['works'][0]['key']}.json") or {}
        claves = [a.get("author", {}).get("key") for a in obra.get("authors", []) if a.get("author")]
    for clave in claves[:6]:
        autor = _json(f"https://openlibrary.org{clave}.json") or {}
        if autor.get("name"):
            datos.autores.append(autor["name"].strip())

    portadas = [c for c in edicion.get("covers", []) if isinstance(c, int) and c > 0]
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
    if not respuesta.get("items"):
        return None
    info = respuesta["items"][0].get("volumeInfo", {})
    datos = DatosLibro(isbn=isbn, fuente="Google Books")
    datos.titulo = info.get("title", "").strip()
    datos.subtitulo = info.get("subtitle", "").strip()
    datos.autores = [a.strip() for a in info.get("authors", [])]
    datos.editorial = info.get("publisher", "").strip()
    datos.anio = _anio(info.get("publishedDate", ""))
    datos.paginas = info.get("pageCount") or None
    datos.idioma = IDIOMAS_ISO2.get(info.get("language", ""), "")
    imagen = (info.get("imageLinks") or {}).get("thumbnail", "")
    if imagen:
        try:
            datos.portada = descargar(imagen.replace("http://", "https://"))
        except ErrorConsulta:
            datos.portada = None
    return datos if datos.titulo else None


def consultar(texto_isbn: str, clave_google: str = "") -> DatosLibro | None:
    """Busca los datos de un ISBN. None si no se encuentra; ErrorConsulta si no se pudo consultar."""
    isbn = validar(texto_isbn)
    if isbn is None:
        raise ValueError("El ISBN no es válido (revisa las cifras).")
    datos = consultar_open_library(isbn)
    if datos is None and clave_google.strip():
        datos = consultar_google_books(isbn, clave_google.strip())
    return datos
