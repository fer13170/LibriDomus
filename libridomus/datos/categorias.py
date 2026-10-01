"""Catálogo de categorías (géneros y materias: Novela histórica, Historia del arte...).

El catálogo lo configura el usuario. Cada elemento puede tener varias categorías.
"""

import sqlite3
from dataclasses import dataclass

from .. import texto
from .conexion import transaccion


class ErrorCategoria(Exception):
    """Operación no permitida sobre las categorías (mensaje para el usuario)."""


@dataclass
class Categoria:
    id: int
    nombre: str
    usos: int = 0  # cuántos elementos la tienen


def listar(con: sqlite3.Connection) -> list[Categoria]:
    """Todas las categorías por orden alfabético (sin tener en cuenta los acentos)."""
    filas = con.execute(
        "SELECT c.id, c.nombre, COUNT(ec.elemento_id) FROM categoria c"
        " LEFT JOIN elemento_categoria ec ON ec.categoria_id = c.id GROUP BY c.id").fetchall()
    return sorted((Categoria(f[0], f[1], f[2]) for f in filas), key=lambda c: texto.clave_orden(c.nombre))


def nombres(con: sqlite3.Connection) -> list[str]:
    return [c.nombre for c in listar(con)]


def buscar(con: sqlite3.Connection, nombre: str) -> Categoria | None:
    """Por nombre, sin que importen mayúsculas ni acentos."""
    clave = texto.clave_orden(nombre.strip())
    return next((c for c in listar(con) if texto.clave_orden(c.nombre) == clave), None)


def _validar_nombre(con: sqlite3.Connection, nombre: str, excluir_id: int | None = None) -> str:
    nombre = " ".join((nombre or "").split())
    if not nombre:
        raise ErrorCategoria("Escribe el nombre de la categoría.")
    if len(nombre) > 80:
        raise ErrorCategoria("El nombre es demasiado largo (máximo 80 caracteres).")
    otra = buscar(con, nombre)
    if otra and otra.id != excluir_id:
        raise ErrorCategoria(f"Ya existe la categoría «{otra.nombre}».")
    return nombre


def crear(con: sqlite3.Connection, nombre: str) -> int:
    nombre = _validar_nombre(con, nombre)
    with transaccion(con):
        return con.execute("INSERT INTO categoria (nombre) VALUES (?)", (nombre,)).lastrowid


def obtener_o_crear(con: sqlite3.Connection, nombre: str) -> int:
    existente = buscar(con, nombre)
    return existente.id if existente else crear(con, nombre)


def renombrar(con: sqlite3.Connection, categoria_id: int, nombre: str) -> None:
    from ..servicios import busqueda

    nombre = _validar_nombre(con, nombre, categoria_id)
    with transaccion(con):
        con.execute("UPDATE categoria SET nombre = ? WHERE id = ?", (nombre, categoria_id))
        for (elemento_id,) in con.execute(
                "SELECT elemento_id FROM elemento_categoria WHERE categoria_id = ?", (categoria_id,)).fetchall():
            busqueda.reindexar(con, elemento_id)  # el nombre forma parte del índice de búsqueda


def borrar(con: sqlite3.Connection, categoria_id: int) -> int:
    """Borra la categoría y la quita de los elementos que la tenían. Devuelve cuántos eran."""
    from ..servicios import busqueda

    with transaccion(con):
        afectados = [f[0] for f in con.execute(
            "SELECT elemento_id FROM elemento_categoria WHERE categoria_id = ?", (categoria_id,)).fetchall()]
        con.execute("DELETE FROM categoria WHERE id = ?", (categoria_id,))  # ON DELETE CASCADE
        for elemento_id in afectados:
            busqueda.reindexar(con, elemento_id)
    return len(afectados)
