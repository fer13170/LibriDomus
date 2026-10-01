"""Esquema de la base de datos y sus migraciones.

Cada entrada de ``MIGRACIONES`` lleva la base de datos de la versión N-1 a la N.
La versión actual se guarda en ``PRAGMA user_version``. Para cambiar el esquema
en el futuro: añadir una nueva entrada al final de la lista (nunca modificar las
anteriores, porque ya se han aplicado en bases de datos existentes).
"""

MIGRACION_1 = """
CREATE TABLE tipo_ubicacion (
    id      INTEGER PRIMARY KEY,
    nombre  TEXT NOT NULL UNIQUE COLLATE NOCASE,
    prefijo TEXT NOT NULL DEFAULT '',          -- para sugerir códigos (p. ej. 'EST')
    orden   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ubicacion (
    id          INTEGER PRIMARY KEY,
    padre_id    INTEGER REFERENCES ubicacion(id) ON DELETE RESTRICT,
    tipo_id     INTEGER NOT NULL REFERENCES tipo_ubicacion(id) ON DELETE RESTRICT,
    nombre      TEXT NOT NULL,
    codigo      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    descripcion TEXT NOT NULL DEFAULT '',
    orden       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_ubicacion_padre ON ubicacion(padre_id);

CREATE TABLE tipo_elemento (
    id            INTEGER PRIMARY KEY,
    nombre        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    icono         TEXT NOT NULL DEFAULT '',
    verbo_consumo TEXT NOT NULL DEFAULT 'Leído',  -- 'Leído', 'Visto', 'Escuchado'...
    personal      INTEGER NOT NULL DEFAULT 0,     -- destaca periodo/personas/lugar
    roles         TEXT NOT NULL DEFAULT '',       -- roles de persona separados por ';'
    predefinido   INTEGER NOT NULL DEFAULT 0,
    orden         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE campo (
    id               INTEGER PRIMARY KEY,
    tipo_elemento_id INTEGER NOT NULL REFERENCES tipo_elemento(id) ON DELETE CASCADE,
    clave            TEXT NOT NULL,
    etiqueta         TEXT NOT NULL,
    tipo_dato        TEXT NOT NULL
        CHECK (tipo_dato IN ('texto', 'texto_largo', 'numero', 'fecha', 'lista', 'si_no')),
    opciones         TEXT NOT NULL DEFAULT '',   -- valores de la lista separados por ';'
    orden            INTEGER NOT NULL DEFAULT 0,
    oculto           INTEGER NOT NULL DEFAULT 0,
    UNIQUE (tipo_elemento_id, clave)
);

CREATE TABLE elemento (
    id             INTEGER PRIMARY KEY,
    tipo_id        INTEGER NOT NULL REFERENCES tipo_elemento(id) ON DELETE RESTRICT,
    titulo         TEXT NOT NULL,
    subtitulo      TEXT NOT NULL DEFAULT '',
    anio           INTEGER,
    fecha_desde    TEXT NOT NULL DEFAULT '',
    fecha_hasta    TEXT NOT NULL DEFAULT '',
    idioma         TEXT NOT NULL DEFAULT '',
    estado         TEXT NOT NULL DEFAULT '',
    valoracion     INTEGER NOT NULL DEFAULT 0 CHECK (valoracion BETWEEN 0 AND 5),
    consumido      INTEGER NOT NULL DEFAULT 0,
    identificador  TEXT NOT NULL DEFAULT '',     -- ISBN / EAN / ISSN sin guiones
    lugar_evento   TEXT NOT NULL DEFAULT '',
    ubicacion_id   INTEGER REFERENCES ubicacion(id) ON DELETE RESTRICT,
    portada        TEXT NOT NULL DEFAULT '',     -- nombre del archivo en datos/portadas
    prestado_a     TEXT NOT NULL DEFAULT '',
    fecha_prestamo TEXT NOT NULL DEFAULT '',
    notas          TEXT NOT NULL DEFAULT '',
    creado         TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    modificado     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX ix_elemento_tipo ON elemento(tipo_id);
CREATE INDEX ix_elemento_ubicacion ON elemento(ubicacion_id);
CREATE INDEX ix_elemento_identificador ON elemento(identificador);

CREATE TABLE valor_campo (
    elemento_id INTEGER NOT NULL REFERENCES elemento(id) ON DELETE CASCADE,
    campo_id    INTEGER NOT NULL REFERENCES campo(id) ON DELETE CASCADE,
    valor       TEXT NOT NULL,
    PRIMARY KEY (elemento_id, campo_id)
);

CREATE TABLE persona (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE elemento_persona (
    elemento_id INTEGER NOT NULL REFERENCES elemento(id) ON DELETE CASCADE,
    persona_id  INTEGER NOT NULL REFERENCES persona(id) ON DELETE RESTRICT,
    rol         TEXT NOT NULL,
    orden       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (elemento_id, persona_id, rol)
);
CREATE INDEX ix_elemento_persona_persona ON elemento_persona(persona_id);

CREATE TABLE etiqueta (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE elemento_etiqueta (
    elemento_id INTEGER NOT NULL REFERENCES elemento(id) ON DELETE CASCADE,
    etiqueta_id INTEGER NOT NULL REFERENCES etiqueta(id) ON DELETE CASCADE,
    PRIMARY KEY (elemento_id, etiqueta_id)
);

-- Índice de búsqueda de texto completo. rowid = elemento.id.
-- Lo mantiene el programa (servicios/busqueda.py -> reindexar).
CREATE VIRTUAL TABLE elemento_fts USING fts5(
    titulo, personas, etiquetas, texto, ubicacion,
    tokenize = 'unicode61 remove_diacritics 2',
    prefix = '2 3'
);
"""

# Versión 2 (LibriDomus): iconos Lucide en lugar de emojis y un icono por tipo de ubicación.
MIGRACION_2 = """
ALTER TABLE tipo_ubicacion ADD COLUMN icono TEXT NOT NULL DEFAULT '';
UPDATE tipo_ubicacion SET icono = CASE nombre
    WHEN 'Casa' THEN 'house' WHEN 'Planta' THEN 'layers' WHEN 'Habitación' THEN 'door-open'
    WHEN 'Armario' THEN 'archive' WHEN 'Estantería' THEN 'library' WHEN 'Balda' THEN 'rows-3'
    WHEN 'Caja' THEN 'box' WHEN 'Cajón' THEN 'inbox' WHEN 'Archivador' THEN 'file-box'
    ELSE 'map-pin' END;
UPDATE tipo_elemento SET icono = CASE icono
    WHEN '📖' THEN 'book' WHEN '📰' THEN 'newspaper' WHEN '💿' THEN 'disc-3' WHEN '🎬' THEN 'clapperboard'
    WHEN '🎮' THEN 'gamepad-2' WHEN '🎼' THEN 'music' WHEN '📷' THEN 'images' WHEN '🎞️' THEN 'projector'
    WHEN '📁' THEN 'folder' WHEN '🗺️' THEN 'map' ELSE icono END;
"""

# Versión 3 (LibriDomus 1.4): catálogo de categorías (géneros y materias) configurable por el
# usuario. Un elemento puede tener varias. Se crea con las categorías habituales de librerías y
# bibliotecas (también en las bases de datos que ya existían). servicios/clasificar.py usa estos
# nombres para proponer la categoría a partir de los datos del ISBN.
MIGRACION_3 = """
CREATE TABLE categoria (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE elemento_categoria (
    elemento_id  INTEGER NOT NULL REFERENCES elemento(id) ON DELETE CASCADE,
    categoria_id INTEGER NOT NULL REFERENCES categoria(id) ON DELETE CASCADE,
    PRIMARY KEY (elemento_id, categoria_id)
);
CREATE INDEX ix_elemento_categoria_categoria ON elemento_categoria(categoria_id);

INSERT INTO categoria (nombre) VALUES
    ('Novela'), ('Novela histórica'), ('Novela negra y suspense'), ('Ciencia ficción'), ('Fantasía'),
    ('Terror'), ('Romántica'), ('Humor'), ('Clásicos de la literatura'), ('Cuento y relato'), ('Poesía'),
    ('Teatro'), ('Cómic y novela gráfica'), ('Infantil y juvenil'), ('Biografías y memorias'), ('Ensayo'),
    ('Historia'), ('Arte'), ('Historia del arte'), ('Arquitectura y diseño'), ('Fotografía'), ('Música'),
    ('Cine, televisión y espectáculos'), ('Filosofía'), ('Religión y espiritualidad'), ('Psicología'),
    ('Ciencias sociales y política'), ('Economía y empresa'), ('Derecho'), ('Ciencia'),
    ('Naturaleza y medio ambiente'), ('Medicina y salud'), ('Informática y tecnología'),
    ('Idiomas y diccionarios'), ('Obras de referencia'), ('Viajes'), ('Geografía y mapas'),
    ('Gastronomía y cocina'), ('Deportes'), ('Aficiones y manualidades'), ('Hogar y jardín'),
    ('Educación'), ('Autoayuda y desarrollo personal'), ('Familia y crianza');
"""

# Versión 4 (LibriDomus 1.4.1): categorías de educación, educación física y deporte.
# OR IGNORE: si el usuario ya había creado alguna con ese nombre, se respeta la suya.
MIGRACION_4 = """
INSERT OR IGNORE INTO categoria (nombre) VALUES
    ('Educación física'), ('Didáctica y pedagogía'), ('Libros de texto'), ('Oposiciones'),
    ('Educación especial e inclusiva'), ('Entrenamiento y preparación física'), ('Medicina deportiva'),
    ('Fisioterapia y rehabilitación'), ('Nutrición deportiva'), ('Psicología del deporte'),
    ('Anatomía, fisiología y biomecánica'), ('Actividad física y salud'), ('Juegos y actividades recreativas'),
    ('Expresión corporal y danza'), ('Deportes de equipo'), ('Deportes individuales'),
    ('Actividades en la naturaleza'), ('Gestión deportiva'), ('Primeros auxilios');
"""

MIGRACIONES: list[str] = [MIGRACION_1, MIGRACION_2, MIGRACION_3, MIGRACION_4]

VERSION_ESQUEMA = len(MIGRACIONES)
