"""Datos iniciales de una base de datos nueva: tipos de ubicación, la casa con
sus plantas y los tipos de elemento predefinidos con sus campos.

Todo lo que se crea aquí se puede modificar después desde el programa.
"""

import sqlite3

TIPOS_UBICACION = [
    # (nombre, prefijo para sugerir códigos, icono)
    ("Casa", "CASA", "house"),
    ("Planta", "PL", "layers"),
    ("Habitación", "HAB", "door-open"),
    ("Armario", "ARM", "archive"),
    ("Estantería", "EST", "library"),
    ("Balda", "B", "rows-3"),
    ("Caja", "CAJ", "box"),
    ("Cajón", "CJN", "inbox"),
    ("Archivador", "ARC", "file-box"),
    ("Otro", "OTR", "map-pin"),
]

# Plantas iniciales, en orden físico (de abajo arriba).
PLANTAS = [("Sótano", "SOT"), ("Planta baja", "PB"), ("Planta alta", "PA"), ("Buhardilla", "BUH")]

# Campos propios: (clave, etiqueta, tipo_dato, opciones)
TIPOS_ELEMENTO = [
    {
        "nombre": "Libro", "icono": "book", "verbo": "Leído", "personal": 0,
        "roles": "Autor;Traductor;Ilustrador",
        "campos": [
            ("editorial", "Editorial", "texto", ""),
            ("edicion", "Edición", "texto", ""),
            ("paginas", "Nº de páginas", "numero", ""),
            ("coleccion", "Colección / serie", "texto", ""),
            ("numero_serie", "Nº en la serie", "numero", ""),
            ("encuadernacion", "Encuadernación", "lista", "Tapa dura;Tapa blanda;Bolsillo;Rústica;Otra"),
        ],
    },
    {
        "nombre": "Revista / Cómic", "icono": "newspaper", "verbo": "Leído", "personal": 0,
        "roles": "Autor;Guionista;Dibujante",
        "campos": [
            ("cabecera", "Cabecera / colección", "texto", ""),
            ("numero", "Número", "texto", ""),
            ("editorial", "Editorial", "texto", ""),
        ],
    },
    {
        "nombre": "Disco", "icono": "disc-3", "verbo": "Escuchado", "personal": 0,
        "roles": "Intérprete;Compositor",
        "campos": [
            ("soporte", "Soporte", "lista", "CD;Vinilo LP;Vinilo single;Casete;Otro"),
            ("sello", "Sello discográfico", "texto", ""),
            ("num_discos", "Nº de discos", "numero", ""),
            ("pistas", "Lista de pistas", "texto_largo", ""),
        ],
    },
    {
        "nombre": "Película", "icono": "clapperboard", "verbo": "Visto", "personal": 0,
        "roles": "Director;Actor",
        "campos": [
            ("soporte", "Soporte", "lista", "DVD;Blu-ray;VHS;Otro"),
            ("duracion", "Duración (min)", "numero", ""),
            ("num_discos", "Nº de discos", "numero", ""),
        ],
    },
    {
        "nombre": "Videojuego", "icono": "gamepad-2", "verbo": "Jugado", "personal": 0,
        "roles": "Desarrollador",
        "campos": [
            ("plataforma", "Plataforma", "texto", ""),
            ("soporte", "Soporte", "lista", "Cartucho;CD/DVD;Blu-ray;Tarjeta;Otro"),
        ],
    },
    {
        "nombre": "Partitura", "icono": "music", "verbo": "Tocado", "personal": 0,
        "roles": "Compositor;Arreglista",
        "campos": [
            ("instrumentacion", "Instrumentación", "texto", ""),
            ("editorial", "Editorial", "texto", ""),
        ],
    },
    {
        "nombre": "Álbum de fotos", "icono": "images", "verbo": "Revisado", "personal": 1,
        "roles": "Aparece;Fotógrafo",
        "campos": [("formato", "Formato", "texto", "")],
    },
    {
        "nombre": "Diapositivas", "icono": "projector", "verbo": "Revisado", "personal": 1,
        "roles": "Aparece;Fotógrafo",
        "campos": [
            ("formato", "Formato", "lista", "35 mm;Medio formato;Otro"),
            ("contenedor", "Contenedor (caja / carro)", "texto", ""),
        ],
    },
    {
        "nombre": "Carpeta", "icono": "folder", "verbo": "Revisado", "personal": 1,
        "roles": "Propietario;Aparece",
        "campos": [("tematica", "Temática", "texto", "")],
    },
    {
        "nombre": "Mapa / Documento", "icono": "map", "verbo": "Revisado", "personal": 1,
        "roles": "Autor;Propietario",
        "campos": [
            ("clase", "Clase de documento", "texto", ""),
            ("escala", "Escala (mapas)", "texto", ""),
        ],
    },
]


def cargar(con: sqlite3.Connection) -> None:
    for orden, (nombre, prefijo, icono) in enumerate(TIPOS_UBICACION):
        con.execute(
            "INSERT INTO tipo_ubicacion (nombre, prefijo, orden, icono) VALUES (?, ?, ?, ?)",
            (nombre, prefijo, orden, icono),
        )
    tipo = {fila[1]: fila[0] for fila in con.execute("SELECT id, nombre FROM tipo_ubicacion")}

    casa_id = con.execute(
        "INSERT INTO ubicacion (padre_id, tipo_id, nombre, codigo, orden) VALUES (NULL, ?, 'Casa', 'CASA', 0)",
        (tipo["Casa"],),
    ).lastrowid
    for orden, (nombre, codigo) in enumerate(PLANTAS):
        con.execute(
            "INSERT INTO ubicacion (padre_id, tipo_id, nombre, codigo, orden) VALUES (?, ?, ?, ?, ?)",
            (casa_id, tipo["Planta"], nombre, codigo, orden),
        )

    for orden, definicion in enumerate(TIPOS_ELEMENTO):
        tipo_id = con.execute(
            "INSERT INTO tipo_elemento (nombre, icono, verbo_consumo, personal, roles, predefinido, orden)"
            " VALUES (?, ?, ?, ?, ?, 1, ?)",
            (definicion["nombre"], definicion["icono"], definicion["verbo"],
             definicion["personal"], definicion["roles"], orden),
        ).lastrowid
        for orden_campo, (clave, etiqueta, tipo_dato, opciones) in enumerate(definicion["campos"]):
            con.execute(
                "INSERT INTO campo (tipo_elemento_id, clave, etiqueta, tipo_dato, opciones, orden)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (tipo_id, clave, etiqueta, tipo_dato, opciones, orden_campo),
            )
