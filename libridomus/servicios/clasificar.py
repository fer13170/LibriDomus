"""Proponer categorías a partir de las materias que dan las fuentes del ISBN.

Las materias llegan de dos formas:
- Con código, de la Agencia Española del ISBN: 'FH - Obra De Misterio Y Suspense'. Son códigos
  Thema y BIC, las clasificaciones estándar del comercio del libro (https://www.editeur.org/151/Thema/).
  Se traducen con CODIGOS: gana el prefijo más largo ('FV' antes que 'F').
- Como texto, de la BNE ('Novelas rosas'), la BnF, Open Library o Google Books
  ('Fiction / Romance / Contemporary'). Se buscan palabras clave con PALABRAS.

Solo se proponen categorías que existan en el catálogo del usuario (si ha borrado o
renombrado una de las iniciales, simplemente no se propone).
"""

import re

from .. import texto

MAXIMO = 3  # categorías propuestas como mucho

# Prefijo de código Thema / BIC -> categoría inicial del catálogo
CODIGOS = {
    # Ficción
    "FV": "Novela histórica", "FF": "Novela negra y suspense", "FH": "Novela negra y suspense",
    "FL": "Ciencia ficción", "FM": "Fantasía", "FK": "Terror", "FR": "Romántica", "FU": "Humor",
    "FC": "Clásicos de la literatura", "FYB": "Cuento y relato", "F": "Novela",
    # Literatura y biografía
    "DC": "Poesía", "DD": "Teatro", "DB": "Clásicos de la literatura", "DNJ": "Ensayo", "DNL": "Ensayo",
    "DN": "Biografías y memorias", "DS": "Ensayo", "B": "Biografías y memorias",
    "X": "Cómic y novela gráfica", "Y": "Infantil y juvenil",
    # Artes
    "AC": "Historia del arte", "AJ": "Fotografía", "AM": "Arquitectura y diseño", "AK": "Arquitectura y diseño",
    "AV": "Música", "AT": "Cine, televisión y espectáculos", "AP": "Cine, televisión y espectáculos",
    "A": "Arte",
    # Humanidades y sociedad
    "HB": "Historia", "HD": "Historia", "N": "Historia", "HP": "Filosofía", "QD": "Filosofía",
    "HR": "Religión y espiritualidad", "QR": "Religión y espiritualidad", "JM": "Psicología",
    "JN": "Educación", "J": "Ciencias sociales y política", "K": "Economía y empresa", "L": "Derecho",
    # Ciencia y técnica
    "M": "Medicina y salud", "P": "Ciencia", "RG": "Geografía y mapas", "R": "Naturaleza y medio ambiente",
    "U": "Informática y tecnología", "T": "Informática y tecnología",
    # Lengua y referencia
    "C": "Idiomas y diccionarios", "E": "Idiomas y diccionarios", "G": "Obras de referencia",
    # Vida práctica
    "VFV": "Familia y crianza", "VS": "Autoayuda y desarrollo personal", "VF": "Medicina y salud",
    "V": "Autoayuda y desarrollo personal", "WB": "Gastronomía y cocina", "WT": "Viajes",
    "WK": "Hogar y jardín", "WM": "Hogar y jardín", "WN": "Naturaleza y medio ambiente",
    "WS": "Deportes", "S": "Deportes", "W": "Aficiones y manualidades",
}

# Palabras clave (sin acentos, en minúsculas) -> categoría. Se prueban en este orden.
PALABRAS = [
    (r"novelas? historic|historical fiction", "Novela histórica"),
    (r"policiac|novela negra|novelas negras|detective|crime|mystery|thriller|suspense", "Novela negra y suspense"),
    (r"ciencia ficcion|science fiction", "Ciencia ficción"),
    (r"fantas(y|ia|ica|ico)", "Fantasía"),
    (r"\bterror\b|horror", "Terror"),
    (r"novelas? rosas?|romantic|romance", "Romántica"),
    (r"\bhumor|humour", "Humor"),
    (r"cuentos|relatos|short stories", "Cuento y relato"),
    (r"poesia|poemas|poetry", "Poesía"),
    (r"\bteatro\b|\bdrama\b", "Teatro"),
    (r"comics?\b|novela grafica|graphic novel|tebeos", "Cómic y novela gráfica"),
    (r"juvenil|infantil|juvenile|children", "Infantil y juvenil"),
    (r"biografia|autobiografia|memorias|biography|memoir", "Biografías y memorias"),
    (r"ensayos?\b|essays", "Ensayo"),
    (r"historia del arte|art history", "Historia del arte"),
    (r"cocina|recetas|cookery|cooking", "Gastronomía y cocina"),
    (r"\bviajes\b|\btravel\b|guias turisticas", "Viajes"),
    (r"filosofia|philosophy", "Filosofía"),
    (r"religion|teologia|theology|espiritualidad", "Religión y espiritualidad"),
    (r"psicologia|psychology", "Psicología"),
    (r"novelas?\b|\bfiction\b|narrativa", "Novela"),
]

GENERICA = "Novela"
DE_FICCION = {"Novela histórica", "Novela negra y suspense", "Ciencia ficción", "Fantasía", "Terror",
              "Romántica", "Humor", "Clásicos de la literatura", "Cuento y relato"}

_CODIGO = re.compile(r"^\s*([A-Z][A-Z0-9]*)\s+-\s+")


def _por_codigo(codigo: str) -> str | None:
    for largo in range(len(codigo), 0, -1):
        if codigo[:largo] in CODIGOS:
            return CODIGOS[codigo[:largo]]
    return None


def _por_palabras(materia: str) -> str | None:
    normal = texto.sin_acentos(materia).casefold()
    for patron, categoria in PALABRAS:
        if re.search(patron, normal):
            return categoria
    return None


def proponer(materias: list[str], disponibles: list[str]) -> list[str]:
    """Categorías del catálogo (``disponibles``) que corresponden a esas materias."""
    por_clave = {texto.clave_orden(n): n for n in disponibles}
    propuestas: list[str] = []
    for materia in materias:
        m = _CODIGO.match(materia)
        # Los códigos que empiezan por una cifra son matices (época, lugar, edad), no temas.
        categoria = _por_codigo(m.group(1)) if m else _por_palabras(materia)
        nombre = por_clave.get(texto.clave_orden(categoria)) if categoria else None
        if nombre and nombre not in propuestas:
            propuestas.append(nombre)
    # 'Novela' sobra si ya se sabe el género (novela negra, romántica...).
    if any(p in DE_FICCION for p in propuestas):
        propuestas = [p for p in propuestas if p != por_clave.get(texto.clave_orden(GENERICA))]
    return propuestas[:MAXIMO]
