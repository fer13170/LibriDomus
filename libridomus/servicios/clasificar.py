"""Proponer categorías a partir de las materias que dan las fuentes del ISBN.

Las materias llegan de dos formas:
- Con código, de la Agencia Española del ISBN: 'FH - Obra De Misterio Y Suspense'. Son códigos
  Thema y BIC, las clasificaciones estándar del comercio del libro (https://www.editeur.org/151/Thema/).
  Se traducen con CODIGOS: gana el prefijo más largo ('FV' antes que 'F').
- Como texto, de la BNE ('Novelas rosas'), la BnF, Open Library o Google Books
  ('Fiction / Romance / Contemporary'). Se buscan palabras clave con PALABRAS.
- Antes que nada se buscan los temas muy concretos (ESPECIFICAS: educación física, medicina
  deportiva...) en todo el texto, también en la descripción que acompaña al código
  ('SCGF - Nutrición deportiva'): el código solo diría «Deportes».

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

# Temas concretos (educación y deporte): se buscan en cualquier materia, con código o sin él.
ESPECIFICAS = [
    (r"educacion fisica|physical education", "Educación física"),
    (r"medicina (deportiva|del deporte)|sports? medicine|lesiones deportivas|sports? injur", "Medicina deportiva"),
    (r"nutricion deportiva|sports? nutrition|alimentacion (y|del|en el) deporte", "Nutrición deportiva"),
    (r"psicologia (del deporte|deportiva)|sports? psychology", "Psicología del deporte"),
    (r"fisioterapia|rehabilitacion fisica|physiotherapy|physical therapy", "Fisioterapia y rehabilitación"),
    (r"biomecanica|fisiologia del (ejercicio|deporte)|anatomia|biomechanics|exercise physiology",
     "Anatomía, fisiología y biomecánica"),
    (r"entrenamiento (deportivo|fisico)|preparacion fisica|acondicionamiento fisico|musculacion|"
     r"sports? training|strength training|coaching deportivo", "Entrenamiento y preparación física"),
    (r"actividad fisica y salud|ejercicio fisico|physical activity", "Actividad física y salud"),
    (r"primeros auxilios|first aid", "Primeros auxilios"),
    (r"oposiciones", "Oposiciones"),
    (r"libros? de texto|textbooks?", "Libros de texto"),
    (r"educacion especial|necesidades educativas|educacion inclusiva|special education", "Educación especial e inclusiva"),
    (r"didactica|pedagogia|metodologia docente|teaching methods|teaching skills", "Didáctica y pedagogía"),
    (r"juegos (motores|populares|cooperativos|tradicionales)|actividades recreativas", "Juegos y actividades recreativas"),
    (r"expresion corporal|\bdanzas?\b|\bdance\b", "Expresión corporal y danza"),
    (r"deportes de equipo|futbol|baloncesto|balonmano|voleibol|rugby|hockey", "Deportes de equipo"),
    (r"deportes individuales|atletismo|natacion|ciclismo|gimnasia|\btenis\b|judo|karate", "Deportes individuales"),
    (r"senderismo|montanismo|escalada|orientacion deportiva|medio natural|deportes de aventura",
     "Actividades en la naturaleza"),
    (r"gestion deportiva|sports? management", "Gestión deportiva"),
]

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
    (r"\bdeportes?\b|\bsports?\b", "Deportes"),
    (r"educacion|\beducation\b|ensenanza", "Educación"),
]

# Categorías generales que sobran si ya se ha encontrado una más concreta de su ámbito
# (una novela negra no necesita además «Novela»; un libro de medicina deportiva, «Deportes»).
DEPORTIVAS = {"Medicina deportiva", "Nutrición deportiva", "Psicología del deporte", "Entrenamiento y preparación física",
              "Deportes de equipo", "Deportes individuales", "Actividades en la naturaleza", "Gestión deportiva",
              "Educación física"}
GENERICAS = {
    "Novela": {"Novela histórica", "Novela negra y suspense", "Ciencia ficción", "Fantasía", "Terror",
               "Romántica", "Humor", "Clásicos de la literatura", "Cuento y relato"},
    "Deportes": DEPORTIVAS,
    "Educación": {"Educación física", "Didáctica y pedagogía", "Libros de texto", "Oposiciones",
                  "Educación especial e inclusiva"},
    "Medicina y salud": {"Medicina deportiva", "Fisioterapia y rehabilitación", "Primeros auxilios",
                         "Anatomía, fisiología y biomecánica", "Nutrición deportiva"},
    "Psicología": {"Psicología del deporte"},
}

_CODIGO = re.compile(r"^\s*([A-Z][A-Z0-9]*)\s+-\s+")


def _por_codigo(codigo: str) -> str | None:
    for largo in range(len(codigo), 0, -1):
        if codigo[:largo] in CODIGOS:
            return CODIGOS[codigo[:largo]]
    return None


def _todas(materia: str, lista: list[tuple[str, str]]) -> list[str]:
    """Todas las categorías de ``lista`` que aparecen en la materia ('Fútbol -- Entrenamiento' da dos)."""
    normal = texto.sin_acentos(materia).casefold()
    return [categoria for patron, categoria in lista if re.search(patron, normal)]


def _por_palabras(materia: str, lista: list[tuple[str, str]]) -> str | None:
    normal = texto.sin_acentos(materia).casefold()
    for patron, categoria in lista:
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
        encontradas = (_todas(materia, ESPECIFICAS)
                       or [_por_codigo(m.group(1)) if m else _por_palabras(materia, PALABRAS)])
        for categoria in encontradas:
            nombre = por_clave.get(texto.clave_orden(categoria)) if categoria else None
            if nombre and nombre not in propuestas:
                propuestas.append(nombre)
    # Las generales sobran si ya hay una concreta de su ámbito.
    claves = {texto.clave_orden(p) for p in propuestas}
    for general, concretas in GENERICAS.items():
        if claves & {texto.clave_orden(c) for c in concretas}:
            propuestas = [p for p in propuestas if texto.clave_orden(p) != texto.clave_orden(general)]
    return propuestas[:MAXIMO]
