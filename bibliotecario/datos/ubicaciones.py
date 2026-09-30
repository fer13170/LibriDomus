"""Catálogo de ubicaciones: la casa, sus plantas, habitaciones, muebles, baldas, cajas...

Las ubicaciones forman un árbol (cada una tiene un ``padre_id``) de profundidad libre.
"""

import sqlite3
from dataclasses import dataclass

from .. import texto
from .conexion import transaccion

SEPARADOR_RUTA = " › "


class ErrorUbicacion(Exception):
    """Operación no permitida sobre el catálogo de ubicaciones (mensaje para el usuario)."""


@dataclass
class Ubicacion:
    id: int
    padre_id: int | None
    tipo_id: int
    tipo: str
    nombre: str
    codigo: str
    descripcion: str
    orden: int


_SELECT = (
    "SELECT u.id, u.padre_id, u.tipo_id, t.nombre AS tipo, u.nombre, u.codigo, u.descripcion, u.orden"
    " FROM ubicacion u JOIN tipo_ubicacion t ON t.id = u.tipo_id"
)


def _desde_fila(fila: sqlite3.Row) -> Ubicacion:
    return Ubicacion(**{k: fila[k] for k in fila.keys()})


# ---------------------------------------------------------------- tipos de ubicación

def listar_tipos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT t.id, t.nombre, t.prefijo, t.orden,"
        " (SELECT COUNT(*) FROM ubicacion u WHERE u.tipo_id = t.id) AS usos"
        " FROM tipo_ubicacion t ORDER BY t.orden, t.nombre COLLATE ES"
    ).fetchall()


def guardar_tipo(con: sqlite3.Connection, nombre: str, prefijo: str = "", tipo_id: int | None = None) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ErrorUbicacion("El tipo de ubicación necesita un nombre.")
    prefijo = prefijo.strip().upper() or texto.abreviar(nombre)
    try:
        if tipo_id is None:
            orden = con.execute("SELECT COALESCE(MAX(orden), -1) + 1 FROM tipo_ubicacion").fetchone()[0]
            return con.execute(
                "INSERT INTO tipo_ubicacion (nombre, prefijo, orden) VALUES (?, ?, ?)", (nombre, prefijo, orden)
            ).lastrowid
        con.execute("UPDATE tipo_ubicacion SET nombre = ?, prefijo = ? WHERE id = ?", (nombre, prefijo, tipo_id))
        return tipo_id
    except sqlite3.IntegrityError as error:
        raise ErrorUbicacion(f"Ya existe un tipo de ubicación llamado «{nombre}».") from error


def borrar_tipo(con: sqlite3.Connection, tipo_id: int) -> None:
    usos = con.execute("SELECT COUNT(*) FROM ubicacion WHERE tipo_id = ?", (tipo_id,)).fetchone()[0]
    if usos:
        raise ErrorUbicacion(f"No se puede borrar: hay {usos} ubicaciones de este tipo.")
    con.execute("DELETE FROM tipo_ubicacion WHERE id = ?", (tipo_id,))


# ---------------------------------------------------------------- consultas

def todas(con: sqlite3.Connection) -> list[Ubicacion]:
    """Todas las ubicaciones, ordenadas por padre y orden (para construir el árbol)."""
    filas = con.execute(_SELECT + " ORDER BY u.padre_id IS NOT NULL, u.padre_id, u.orden, u.nombre COLLATE ES")
    return [_desde_fila(f) for f in filas]


def obtener(con: sqlite3.Connection, ubicacion_id: int) -> Ubicacion | None:
    fila = con.execute(_SELECT + " WHERE u.id = ?", (ubicacion_id,)).fetchone()
    return _desde_fila(fila) if fila else None


def buscar_por_codigo(con: sqlite3.Connection, codigo: str) -> Ubicacion | None:
    fila = con.execute(_SELECT + " WHERE u.codigo = ? COLLATE NOCASE", (codigo.strip(),)).fetchone()
    return _desde_fila(fila) if fila else None


def hijos(con: sqlite3.Connection, padre_id: int | None) -> list[Ubicacion]:
    filas = con.execute(
        _SELECT + " WHERE u.padre_id IS ? ORDER BY u.orden, u.nombre COLLATE ES", (padre_id,)
    )
    return [_desde_fila(f) for f in filas]


def descendientes(con: sqlite3.Connection, ubicacion_id: int) -> list[int]:
    """Ids de la ubicación y de todo lo que cuelga de ella."""
    filas = con.execute(
        "WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL"
        " SELECT u.id FROM ubicacion u JOIN sub ON u.padre_id = sub.id) SELECT id FROM sub",
        (ubicacion_id,),
    )
    return [f[0] for f in filas]


def ruta(con: sqlite3.Connection, ubicacion_id: int | None) -> list[Ubicacion]:
    """Desde la raíz hasta la ubicación indicada (incluida)."""
    resultado: list[Ubicacion] = []
    actual = obtener(con, ubicacion_id) if ubicacion_id else None
    while actual is not None:
        resultado.insert(0, actual)
        actual = obtener(con, actual.padre_id) if actual.padre_id else None
    return resultado


def ruta_texto(con: sqlite3.Connection, ubicacion_id: int | None, incluir_raiz: bool = False) -> str:
    """'Planta baja › Salón › Estantería A'. La casa (raíz) se omite salvo que se pida."""
    partes = ruta(con, ubicacion_id)
    if not incluir_raiz and len(partes) > 1:
        partes = partes[1:]
    return SEPARADOR_RUTA.join(u.nombre for u in partes)


def rutas_todas(con: sqlite3.Connection) -> dict[int, str]:
    """Ruta de texto de todas las ubicaciones de una vez (para listados grandes)."""
    lista = todas(con)
    por_id = {u.id: u for u in lista}
    cache: dict[int, str] = {}

    def calcular(u: Ubicacion) -> str:
        if u.id in cache:
            return cache[u.id]
        if u.padre_id is None:
            valor = u.nombre
        else:
            padre = por_id[u.padre_id]
            valor = u.nombre if padre.padre_id is None else calcular(padre) + SEPARADOR_RUTA + u.nombre
        cache[u.id] = valor
        return valor

    for u in lista:
        calcular(u)
    return cache


def contar_elementos(con: sqlite3.Connection) -> dict[int, int]:
    """Número de elementos de cada ubicación incluyendo sus sububicaciones."""
    directos = {f[0]: f[1] for f in con.execute(
        "SELECT ubicacion_id, COUNT(*) FROM elemento WHERE ubicacion_id IS NOT NULL GROUP BY ubicacion_id"
    )}
    lista = todas(con)
    totales = {u.id: directos.get(u.id, 0) for u in lista}
    por_id = {u.id: u for u in lista}
    for u in lista:
        cantidad = directos.get(u.id, 0)
        padre = u.padre_id
        while cantidad and padre is not None:
            totales[padre] += cantidad
            padre = por_id[padre].padre_id
    return totales


# ---------------------------------------------------------------- códigos

def sugerir_codigo(con: sqlite3.Connection, padre_id: int | None, nombre: str,
                   excluir_id: int | None = None) -> str:
    """Código corto y único: código del padre + abreviatura ('PB-SAL-EA-B3').

    Los hijos directos de la casa (las plantas) no llevan el código de la casa delante.
    """
    base = texto.abreviar(nombre)
    padre = obtener(con, padre_id) if padre_id else None
    if padre is not None and padre.padre_id is not None:
        base = f"{padre.codigo}-{base}"
    codigo, n = base, 2
    while _codigo_ocupado(con, codigo, excluir_id):
        codigo, n = f"{base}{n}" if base[-1].isalpha() else f"{base}-{n}", n + 1
    return codigo


def _codigo_ocupado(con: sqlite3.Connection, codigo: str, excluir_id: int | None) -> bool:
    fila = con.execute(
        "SELECT 1 FROM ubicacion WHERE codigo = ? COLLATE NOCASE AND id IS NOT ?", (codigo, excluir_id)
    ).fetchone()
    return fila is not None


# ---------------------------------------------------------------- cambios

def crear(con: sqlite3.Connection, padre_id: int | None, tipo_id: int, nombre: str,
          codigo: str = "", descripcion: str = "") -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ErrorUbicacion("La ubicación necesita un nombre.")
    if padre_id is not None and obtener(con, padre_id) is None:
        raise ErrorUbicacion("La ubicación padre no existe.")
    codigo = codigo.strip().upper() or sugerir_codigo(con, padre_id, nombre)
    if _codigo_ocupado(con, codigo, None):
        raise ErrorUbicacion(f"El código «{codigo}» ya está en uso.")
    orden = con.execute(
        "SELECT COALESCE(MAX(orden), -1) + 1 FROM ubicacion WHERE padre_id IS ?", (padre_id,)
    ).fetchone()[0]
    return con.execute(
        "INSERT INTO ubicacion (padre_id, tipo_id, nombre, codigo, descripcion, orden) VALUES (?, ?, ?, ?, ?, ?)",
        (padre_id, tipo_id, nombre, codigo, descripcion.strip(), orden),
    ).lastrowid


def actualizar(con: sqlite3.Connection, ubicacion_id: int, nombre: str, tipo_id: int,
               codigo: str, descripcion: str = "") -> None:
    from ..servicios import busqueda

    nombre, codigo = nombre.strip(), codigo.strip().upper()
    if not nombre or not codigo:
        raise ErrorUbicacion("El nombre y el código son obligatorios.")
    if _codigo_ocupado(con, codigo, ubicacion_id):
        raise ErrorUbicacion(f"El código «{codigo}» ya está en uso.")
    with transaccion(con):
        con.execute(
            "UPDATE ubicacion SET nombre = ?, tipo_id = ?, codigo = ?, descripcion = ? WHERE id = ?",
            (nombre, tipo_id, codigo, descripcion.strip(), ubicacion_id),
        )
        busqueda.reindexar_ubicacion(con, ubicacion_id)  # la ruta forma parte del índice


def mover(con: sqlite3.Connection, ubicacion_id: int, nuevo_padre_id: int | None, indice: int | None = None) -> None:
    """Mueve una ubicación (con todo su contenido) bajo otro padre, en la posición ``indice``."""
    from ..servicios import busqueda

    if nuevo_padre_id is not None and nuevo_padre_id in descendientes(con, ubicacion_id):
        raise ErrorUbicacion("No se puede mover una ubicación dentro de sí misma.")
    with transaccion(con):
        hermanos = [u.id for u in hijos(con, nuevo_padre_id) if u.id != ubicacion_id]
        indice = len(hermanos) if indice is None else max(0, min(indice, len(hermanos)))
        hermanos.insert(indice, ubicacion_id)
        con.execute("UPDATE ubicacion SET padre_id = ? WHERE id = ?", (nuevo_padre_id, ubicacion_id))
        for orden, id_ in enumerate(hermanos):
            con.execute("UPDATE ubicacion SET orden = ? WHERE id = ?", (orden, id_))
        busqueda.reindexar_ubicacion(con, ubicacion_id)


def borrar(con: sqlite3.Connection, ubicacion_id: int, destino_id: int | None = None) -> int:
    """Borra la ubicación y todas sus sububicaciones.

    Si contienen elementos, es obligatorio indicar ``destino_id``: los elementos se
    mueven allí antes de borrar. Devuelve cuántos elementos se han movido.
    """
    from ..servicios import busqueda

    ids = descendientes(con, ubicacion_id)
    marcas = ",".join("?" * len(ids))
    elementos = [f[0] for f in con.execute(f"SELECT id FROM elemento WHERE ubicacion_id IN ({marcas})", ids)]
    if elementos and destino_id is None:
        raise ErrorUbicacion(
            f"Contiene {len(elementos)} elementos. Indica a qué ubicación deben moverse antes de borrarla."
        )
    if destino_id is not None and destino_id in ids:
        raise ErrorUbicacion("El destino no puede estar dentro de la ubicación que se borra.")
    with transaccion(con):
        if elementos:
            con.execute(f"UPDATE elemento SET ubicacion_id = ? WHERE ubicacion_id IN ({marcas})", [destino_id, *ids])
        # Se borran de las hojas hacia arriba para respetar la relación padre-hijo.
        for id_ in reversed(ids):
            con.execute("DELETE FROM ubicacion WHERE id = ?", (id_,))
        for id_ in elementos:
            busqueda.reindexar(con, id_)
    return len(elementos)
