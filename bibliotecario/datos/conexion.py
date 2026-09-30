"""Apertura de la base de datos SQLite, migraciones y transacciones."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .. import rutas, texto
from . import esquema, semillas


class ErrorBaseDatos(Exception):
    """Error comprensible para mostrar al usuario."""


def abrir(ruta: Path | str | None = None) -> sqlite3.Connection:
    """Abre (o crea) la base de datos y la deja lista para usar."""
    ruta = Path(ruta) if ruta else rutas.ruta_base_datos()
    con = sqlite3.connect(ruta, isolation_level=None)  # transacciones explícitas
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.create_collation("ES", texto.comparar)  # ORDER BY ... COLLATE ES (sin acentos)
    _comprobar_fts5(con)
    migrar(con, ruta)
    return con


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
    con.execute("BEGIN")
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
