"""Validación de ISBN y consulta opcional de datos por Internet.

Fuentes, todas gratuitas (las de los catálogos nacionales están en catalogos.py):
  - Agencia Española del ISBN: todos los libros con ISBN español, también los recién salidos.
  - Biblioteca Nacional de España (BNE) y Bibliothèque nationale de France (BnF).
  - Open Library: https://openlibrary.org/isbn/{isbn}.json y /authors/{clave}.json.
    Es la que más libros en otros idiomas tiene y la única que da portadas.
  - Google Books, solo con una clave propia (sin clave responde 429: cuota agotada).
El orden depende del país del ISBN (ver ``orden_fuentes``). Los datos que le falten a una
fuente se completan con las siguientes. Si no hay conexión se lanza ErrorConsulta y el
usuario sigue rellenando a mano.
"""

import json
import re
import time
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
    traductores: list[str] = field(default_factory=list)
    materias: list[str] = field(default_factory=list)  # temas tal como los da la fuente (ver clasificar.py)
    portada_por_titulo: bool = False                   # la portada se buscó por título: puede ser otra edición


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


def descargar(url: str, limite: int = TAMANO_MAXIMO, datos: bytes | None = None,
              sesion=None) -> bytes | None:
    """GET (o POST si se pasan ``datos``) de una URL HTTPS. Devuelve None si no existe (404).

    ``sesion`` es un http.cookiejar.CookieJar para las webs que necesitan cookies.
    Rechaza direcciones y redirecciones que no sean HTTPS y respuestas de más de ``limite`` bytes.
    Las pruebas sustituyen esta función para no depender de Internet.
    """
    if urllib.parse.urlparse(url).scheme != "https":
        raise ErrorConsulta("Solo se consultan direcciones seguras (https).")
    cabeceras = {"User-Agent": AGENTE}
    if datos is not None:
        cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras)
    abridor = _ABRIDOR if sesion is None else urllib.request.build_opener(
        _SoloHttps, urllib.request.HTTPCookieProcessor(sesion))
    try:
        with abridor.open(peticion, timeout=TIEMPO_MAXIMO) as respuesta:
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
    obras = [_texto(_dic(o).get("key")) for o in _lista(edicion.get("works"))]
    obras = [o for o in obras if _CLAVE_OBRA.match(o)]
    obra = None
    if len(datos.titulo) < 4 and obras:
        # Open Library la edita cualquiera y hay fichas estropeadas (p. ej. el ISBN 9781593276034
        # tenía por título «lol»). Un título tan corto se contrasta con el de la obra.
        obra = _json(f"https://openlibrary.org{obras[0]}.json") or {}
        if len(_texto(obra.get("title"))) > len(datos.titulo):
            datos.titulo, datos.subtitulo = _texto(obra.get("title")), _texto(obra.get("subtitle"))
    editoriales = [_texto(e) for e in _lista(edicion.get("publishers")) if _texto(e)]
    datos.editorial = editoriales[0] if editoriales else ""
    datos.anio = _anio(edicion.get("publish_date"))
    paginas = edicion.get("number_of_pages")
    datos.paginas = paginas if isinstance(paginas, int) and not isinstance(paginas, bool) and paginas > 0 else None
    datos.materias = [_texto(m) for m in _lista(edicion.get("subjects")) if _texto(m)][:10]
    idiomas = _lista(edicion.get("languages"))
    if idiomas:
        clave = _texto(_dic(idiomas[0]).get("key")).rsplit("/", 1)[-1]
        datos.idioma = IDIOMAS_OPEN_LIBRARY.get(clave, "")

    # Solo claves con la forma esperada: así nunca se construye una dirección extraña.
    claves = [_texto(_dic(a).get("key")) for a in _lista(edicion.get("authors"))]
    claves = [c for c in claves if _CLAVE_AUTOR.match(c)]
    if not claves and obras:
        obra = obra if obra is not None else (_json(f"https://openlibrary.org{obras[0]}.json") or {})
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
    datos.materias = [_texto(c) for c in _lista(info.get("categories")) if _texto(c)]
    imagen = _texto(_dic(info.get("imageLinks")).get("thumbnail"))
    if imagen:
        try:
            datos.portada = descargar(imagen.replace("http://", "https://", 1))
        except ErrorConsulta:
            datos.portada = None
    return datos if datos.titulo else None


def portada_open_library(isbn: str) -> bytes | None:
    """Portada por ISBN aunque Open Library no tenga la ficha del libro (None si no hay)."""
    try:
        return descargar(f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false")
    except ErrorConsulta:
        return None


def _portada_google_por_titulo(titulo: str, autor: str, clave: str) -> bytes | None:
    consulta = f'intitle:"{titulo}"' + (f' inauthor:"{autor}"' if autor else "")
    parametros = urllib.parse.urlencode({"q": consulta, "key": clave, "maxResults": "5", "printType": "books"})
    respuesta = _json(f"https://www.googleapis.com/books/v1/volumes?{parametros}") or {}
    for elemento in _lista(respuesta.get("items")):
        imagen = _texto(_dic(_dic(_dic(elemento).get("volumeInfo")).get("imageLinks")).get("thumbnail"))
        if imagen.startswith(("http://", "https://")):
            return descargar(imagen.replace("http://", "https://", 1))
    return None


def _portada_open_library_por_titulo(titulo: str, autor: str) -> bytes | None:
    parametros = {"title": titulo, "fields": "cover_i,language", "limit": "10"}
    if autor:
        parametros["author"] = autor
    respuesta = _json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(parametros)) or {}
    documentos = [_dic(d) for d in _lista(respuesta.get("docs"))]
    con_portada = [d for d in documentos if isinstance(d.get("cover_i"), int) and d.get("cover_i") > 0]
    # Mejor una edición en castellano si la hay (la colección es sobre todo en español).
    con_portada.sort(key=lambda d: "spa" not in _lista(d.get("language")))
    if not con_portada:
        return None
    return descargar(f"https://covers.openlibrary.org/b/id/{con_portada[0]['cover_i']}-L.jpg")


def buscar_portada(titulo: str, autores: list[str] | None = None, clave_google: str = "") -> bytes | None:
    """Portada buscada por título y autor (cuando el ISBN no la trae o no hay ISBN).

    Puede ser la de otra edición del mismo libro. None si no se encuentra; ErrorConsulta si no
    hay conexión con ninguna de las fuentes.
    """
    titulo = " ".join((titulo or "").split())[:150]
    autor = " ".join((autores or [""])[0].split())[:100] if autores else ""
    if not titulo:
        return None
    busquedas = [lambda: _portada_open_library_por_titulo(titulo, autor)]
    if clave_google.strip():  # Google tiene muchas más portadas de libros españoles
        busquedas.insert(0, lambda: _portada_google_por_titulo(titulo, autor, clave_google.strip()))
    errores = 0
    for busqueda in busquedas:
        try:
            imagen = busqueda()
        except ErrorConsulta:
            errores += 1
            continue
        except (TypeError, AttributeError, KeyError, IndexError, ValueError):
            continue
        if imagen:
            return imagen
    if errores == len(busquedas):
        raise ErrorConsulta("No hay conexión a Internet o el servicio no responde.")
    return None


def orden_fuentes(isbn: str, clave_google: str = "") -> list[tuple[str, object]]:
    """Fuentes a consultar, de la más a la menos probable según el país del ISBN.

    978-84 y 979-13 son ISBN españoles; 978-2 y 979-10, de editoriales francófonas.
    Las demás fuentes se consultan después por si acaso (un libro en castellano puede
    estar editado en otro país y tenerlo la BNE, por ejemplo).
    """
    from . import catalogos

    espanolas = [("Agencia del ISBN", catalogos.consultar_agencia), ("BNE", catalogos.consultar_bne)]
    francesa = [("BnF", catalogos.consultar_bnf)]
    open_library = [("Open Library", consultar_open_library)]
    if isbn.startswith(("97884", "97913")):
        orden = espanolas + open_library + francesa
    elif isbn.startswith(("9782", "97910")):
        orden = francesa + open_library + espanolas
    else:
        orden = open_library + espanolas + francesa
    if clave_google.strip():  # justo después de Open Library
        orden.insert(orden.index(open_library[0]) + 1,
                     ("Google Books", lambda c: consultar_google_books(c, clave_google.strip())))
    return orden


CAMPOS_FUSION = ("subtitulo", "editorial", "anio", "paginas", "idioma", "portada")
TIEMPO_TOTAL = 30  # segundos: con la red muy lenta no se encadenan más fuentes que esto


def completo(datos: DatosLibro) -> bool:
    return bool(datos.titulo and datos.autores and datos.editorial and datos.anio)


def fusionar(base: DatosLibro, otro: DatosLibro) -> None:
    """Rellena lo que le falta a ``base`` con lo de ``otro`` (sin pisar nada)."""
    for campo in CAMPOS_FUSION:
        if not getattr(base, campo) and getattr(otro, campo):
            setattr(base, campo, getattr(otro, campo))
    if not base.autores and otro.autores:
        base.autores = list(otro.autores)
    if not base.traductores and otro.traductores:
        base.traductores = list(otro.traductores)
    base.materias += [m for m in otro.materias if m not in base.materias]
    if otro.fuente and otro.fuente not in base.fuente:
        base.fuente += f" + {otro.fuente}"


def consultar(texto_isbn: str, clave_google: str = "") -> DatosLibro | None:
    """Busca los datos de un ISBN. None si no se encuentra; ErrorConsulta si no se pudo consultar."""
    isbn = validar(texto_isbn)
    if isbn is None:
        raise ValueError("El ISBN no es válido (revisa las cifras).")
    resultado: DatosLibro | None = None
    errores: list[ErrorConsulta] = []
    inicio = time.monotonic()
    fuentes = orden_fuentes(isbn, clave_google)
    for _nombre, fuente in fuentes:
        if resultado is not None and completo(resultado):
            break
        if time.monotonic() - inicio > TIEMPO_TOTAL:
            break
        try:
            datos = fuente(isbn)
        except ErrorConsulta as error:
            errores.append(error)  # una fuente caída no impide probar las demás
            continue
        except (TypeError, AttributeError, KeyError, IndexError, ValueError):
            # Última red de seguridad ante una respuesta con una forma que no se ha previsto.
            errores.append(ErrorConsulta("Un servicio ha devuelto datos no válidos."))
            continue
        if datos is None or not datos.titulo:
            continue
        if resultado is None:
            resultado = datos
        else:
            fusionar(resultado, datos)
    if resultado is None:
        if errores and len(errores) == len(fuentes):
            raise errores[0]  # ninguna fuente ha respondido: probablemente no hay conexión
        return None
    if resultado.portada is None and "Open Library" not in resultado.fuente:
        resultado.portada = portada_open_library(isbn)
    if resultado.portada is None and clave_google.strip() and "Google Books" not in resultado.fuente:
        # Los catálogos españoles no tienen portadas: con clave, se le piden a Google.
        try:
            google = consultar_google_books(isbn, clave_google.strip())
        except (ErrorConsulta, TypeError, AttributeError, KeyError, IndexError, ValueError):
            google = None
        if google is not None and google.portada:
            fusionar(resultado, google)
    if resultado.portada is None:
        # Último intento: por título y autor (puede ser la portada de otra edición).
        try:
            resultado.portada = buscar_portada(resultado.titulo, resultado.autores, clave_google)
        except ErrorConsulta:
            resultado.portada = None
        resultado.portada_por_titulo = resultado.portada is not None
    return resultado
