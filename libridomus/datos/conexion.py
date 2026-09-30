"""Apertura de la base de datos SQLite, migraciones y transacciones."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .. import rutas, texto
from . import esquema, semillas


class ErrorBaseDatos(Exception):
    """Error comprensible para mostrar al usuario."""


class BaseDatosDanada(ErrorBaseDatos):
    """El archivo no es una base de datos válida o está corrupto (se puede ofrecer restaurar una copia)."""


class BaseDatosSoloLectura(ErrorBaseDatos):
    """El archivo existe pero no se puede modificar (USB protegido, permisos, atributo de solo lectura)."""


ESPERA_BLOQUEO = 15  # segundos que se espera si la base de datos está ocupada antes de dar error


def abrir(ruta: Path | str | None = None, comprobar_integridad: bool = False,
          exigir_escritura: bool = False, copia_antes_de_migrar: bool = True) -> sqlite3.Connection:
    """Abre (o crea) la base de datos y la deja lista para usar.

    Cualquier fallo de SQLite se traduce a ``ErrorBaseDatos`` (o a sus subclases
    ``BaseDatosDanada`` y ``BaseDatosSoloLectura``) con un mensaje para el usuario.
    """
    ruta = Path(ruta) if ruta else rutas.ruta_base_datos()
    existia = ruta.exists() and ruta.stat().st_size > 0
    con = None
    try:
        con = sqlite3.connect(ruta, isolation_level=None, timeout=ESPERA_BLOQUEO)  # transacciones explícitas
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.create_collation("ES", texto.comparar)  # ORDER BY ... COLLATE ES (sin acentos)
        _comprobar_fts5(con)
        if comprobar_integridad and existia:
            resultado = con.execute("PRAGMA quick_check").fetchone()[0]
            if resultado != "ok":
                raise BaseDatosDanada(f"La base de datos está dañada ({resultado[:120]}).")
        migrar(con, ruta if copia_antes_de_migrar else None)
        if exigir_escritura:
            _comprobar_escritura(con)
        return con
    except ErrorBaseDatos:
        if con is not None:
            con.close()
        raise
    except sqlite3.DatabaseError as error:
        if con is not None:
            con.close()
        raise traducir_error(error) from error


def traducir_error(error: sqlite3.DatabaseError) -> ErrorBaseDatos:
    """Convierte un error de SQLite en un error con un mensaje para el usuario."""
    texto_error = str(error).lower()
    if "readonly" in texto_error or "read-only" in texto_error:
        return BaseDatosSoloLectura(
            "No se pueden guardar cambios: el archivo de datos es de solo lectura. Comprueba que la "
            "carpeta del programa no está en un USB protegido contra escritura ni en un disco de solo lectura.")
    if "locked" in texto_error or "busy" in texto_error:
        return ErrorBaseDatos("Los datos están en uso por otro programa. Espera unos segundos e inténtalo de nuevo.")
    if "unable to open" in texto_error:  # no es que esté dañada: no se puede acceder al archivo
        return ErrorBaseDatos("No se puede abrir el archivo de datos. Comprueba que la carpeta del programa "
                              "existe y que Windows permite escribir en ella.")
    if "disk is full" in texto_error:  # «database or disk is full»
        return ErrorBaseDatos("No queda espacio libre en el disco. Libera espacio e inténtalo de nuevo.")
    return BaseDatosDanada(f"La base de datos está dañada o no es válida ({error}).")


def _comprobar_escritura(con: sqlite3.Connection) -> None:
    """Hace una escritura real y la deshace: falla si el archivo es de solo lectura.

    (Pedir solo el bloqueo con BEGIN IMMEDIATE no basta: no escribe nada y no detecta el problema).
    """
    actual = version(con)
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute(f"PRAGMA user_version = {int(actual)}")
    finally:
        con.execute("ROLLBACK")


def abrir_solo_lectura(ruta: Path | str) -> sqlite3.Connection:
    """Abre otra base de datos (p. ej. una copia) sin posibilidad de modificarla.

    La URI se construye con Path.as_uri() para que rutas con '#', '%' o espacios funcionen.
    """
    return sqlite3.connect(Path(ruta).resolve().as_uri() + "?mode=ro", uri=True)


def _comprobar_fts5(con: sqlite3.Connection) -> None:
    try:
        con.execute("CREATE VIRTUAL TABLE temp._prueba_fts USING fts5(x)")
        con.execute("DROP TABLE temp._prueba_fts")
    except sqlite3.OperationalError as error:
        raise ErrorBaseDatos("Esta versión de SQLite no incluye la búsqueda FTS5.") from error


def version(con: sqlite3.Connection) -> int:
    return con.execute("PRAGMA user_version").fetchone()[0]


def migrar(con: sqlite3.Connection, ruta: Path | None = None) -> None:
    actual = version(con)
    objetivo = esquema.VERSION_ESQUEMA
    if actual > objetivo:
        raise ErrorBaseDatos(
            f"La base de datos es de una versión más nueva del programa "
            f"(esquema {actual}, este programa entiende hasta el {objetivo})."
        )
    if actual == objetivo:
        return
    if actual > 0 and ruta is not None:
        # Antes de tocar el esquema de una base de datos con datos, se guarda una copia.
        copiar_en_caliente(con, rutas.carpeta_copias() / f"antes_de_migrar_v{actual}_{_marca_tiempo()}.db")
    for numero in range(actual, objetivo):
        sql = esquema.MIGRACIONES[numero]
        try:
            con.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {numero + 1};\nCOMMIT;")
        except sqlite3.Error:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
    if actual == 0:
        with transaccion(con):
            semillas.cargar(con)


@contextmanager
def transaccion(con: sqlite3.Connection):
    """Agrupa varias operaciones: o se guardan todas o ninguna."""
    if con.in_transaction:  # transacción anidada: la gestiona la exterior
        yield con
        return
    # IMMEDIATE: se reserva la escritura al empezar. Con un BEGIN normal, una transacción que lee y
    # luego escribe puede chocar con otra y fallar al instante («database is locked») sin esperar.
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def copiar_en_caliente(con: sqlite3.Connection, destino: Path) -> Path:
    """Copia coherente de la base de datos abierta (API de copia de SQLite)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    copia = sqlite3.connect(destino)
    try:
        con.backup(copia)
    finally:
        copia.close()
    return destino


def _marca_tiempo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
