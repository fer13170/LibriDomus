"""Elementos de la colección: libros, discos, álbumes... Cada registro es un objeto físico."""

import re
import sqlite3
from dataclasses import dataclass, field

from .. import rutas
from .conexion import transaccion

ESTADOS = ["Nuevo", "Muy bueno", "Bueno", "Regular", "Deteriorado"]
IDIOMAS = ["Español", "Inglés", "Catalán", "Gallego", "Euskera", "Francés", "Alemán",
           "Italiano", "Portugués", "Latín", "Varios", "Otro"]


class ErrorElemento(Exception):
    """Datos no válidos al guardar un elemento (mensaje para el usuario)."""


@dataclass
class Elemento:
    tipo_id: int
    titulo: str
    id: int | None = None
    subtitulo: str = ""
    anio: int | None = None
    fecha_desde: str = ""
    fecha_hasta: str = ""
    idioma: str = ""
    estado: str = ""
    valoracion: int = 0
    consumido: bool = False
    identificador: str = ""
    lugar_evento: str = ""
    ubicacion_id: int | None = None
    portada: str = ""
    prestado_a: str = ""
    fecha_prestamo: str = ""
    notas: str = ""
    creado: str = ""
    modificado: str = ""
    personas: list[tuple[str, str]] = field(default_factory=list)  # (nombre, rol)
    etiquetas: list[str] = field(default_factory=list)
    valores: dict[int, str] = field(default_factory=dict)          # campo_id -> valor


_COLUMNAS = ["tipo_id", "titulo", "subtitulo", "anio", "fecha_desde", "fecha_hasta", "idioma", "estado",
             "valoracion", "consumido", "identificador", "lugar_evento", "ubicacion_id", "portada",
             "prestado_a", "fecha_prestamo", "notas"]


def normalizar_identificador(valor: str) -> str:
    """Quita guiones y espacios: '978-84-8346-846-3' -> '9788483468463'."""
    return re.sub(r"[\s\-‐‑–]", "", valor or "").upper()


_FECHA = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")


def fecha_valida(valor: str) -> bool:
    """Vacía, 'AAAA', 'AAAA-MM' o 'AAAA-MM-DD' (así se ordenan bien como texto)."""
    return not valor or bool(_FECHA.match(valor))


def _validar(e: Elemento) -> None:
    e.titulo = e.titulo.strip()
    if not e.titulo:
        raise ErrorElemento("El título es obligatorio.")
    for nombre, valor in (("Desde", e.fecha_desde), ("Hasta", e.fecha_hasta), ("Fecha de préstamo", e.fecha_prestamo)):
        if not fecha_valida(valor.strip()):
            raise ErrorElemento(f"«{nombre}»: escribe la fecha como AAAA, AAAA-MM o AAAA-MM-DD.")
    e.fecha_desde, e.fecha_hasta, e.fecha_prestamo = e.fecha_desde.strip(), e.fecha_hasta.strip(), e.fecha_prestamo.strip()
    if e.fecha_desde and e.fecha_hasta and e.fecha_hasta < e.fecha_desde:
        raise ErrorElemento("La fecha «Hasta» es anterior a «Desde».")
    if e.anio is not None and not (0 <= int(e.anio) <= 9999):
        raise ErrorElemento("El año no es válido.")
    if not 0 <= int(e.valoracion) <= 5:
        raise ErrorElemento("La valoración debe estar entre 0 y 5.")
    e.identificador = normalizar_identificador(e.identificador)
    e.personas = [(n.strip(), r.strip()) for n, r in e.personas if n.strip()]
    vistas, etiquetas = set(), []
    for et in (x.strip() for x in e.etiquetas):
        if et and et.casefold() not in vistas:
            vistas.add(et.casefold())
            etiquetas.append(et)
    e.etiquetas = etiquetas


def guardar(con: sqlite3.Connection, e: Elemento) -> int:
    from ..servicios import busqueda

    _validar(e)
    valores = [getattr(e, c) for c in _COLUMNAS]
    valores[_COLUMNAS.index("consumido")] = int(bool(e.consumido))
    with transaccion(con):
        if e.id is None:
            marcas = ", ".join("?" * len(_COLUMNAS))
            e.id = con.execute(f"INSERT INTO elemento ({', '.join(_COLUMNAS)}) VALUES ({marcas})", valores).lastrowid
        else:
            asignaciones = ", ".join(f"{c} = ?" for c in _COLUMNAS)
            cursor = con.execute(
                f"UPDATE elemento SET {asignaciones}, modificado = datetime('now', 'localtime') WHERE id = ?",
                [*valores, e.id],
            )
            if cursor.rowcount == 0:
                raise ErrorElemento("El elemento ya no existe.")

        con.execute("DELETE FROM elemento_persona WHERE elemento_id = ?", (e.id,))
        for orden, (nombre, rol) in enumerate(e.personas):
            persona_id = _obtener_o_crear(con, "persona", nombre)
            con.execute(
                "INSERT OR IGNORE INTO elemento_persona (elemento_id, persona_id, rol, orden) VALUES (?, ?, ?, ?)",
                (e.id, persona_id, rol, orden),
            )
        con.execute("DELETE FROM elemento_etiqueta WHERE elemento_id = ?", (e.id,))
        for nombre in e.etiquetas:
            con.execute(
                "INSERT OR IGNORE INTO elemento_etiqueta (elemento_id, etiqueta_id) VALUES (?, ?)",
                (e.id, _obtener_o_crear(con, "etiqueta", nombre)),
            )
        con.execute("DELETE FROM valor_campo WHERE elemento_id = ?", (e.id,))
        for campo_id, valor in e.valores.items():
            if str(valor).strip():
                con.execute("INSERT INTO valor_campo (elemento_id, campo_id, valor) VALUES (?, ?, ?)",
                            (e.id, campo_id, str(valor).strip()))
        _limpiar_huerfanos(con)
        busqueda.reindexar(con, e.id)
    return e.id


def _obtener_o_crear(con: sqlite3.Connection, tabla: str, nombre: str) -> int:
    fila = con.execute(f"SELECT id FROM {tabla} WHERE nombre = ?", (nombre,)).fetchone()  # NOCASE en el esquema
    if fila:
        return fila[0]
    return con.execute(f"INSERT INTO {tabla} (nombre) VALUES (?)", (nombre,)).lastrowid


def _limpiar_huerfanos(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM persona WHERE id NOT IN (SELECT persona_id FROM elemento_persona)")
    con.execute("DELETE FROM etiqueta WHERE id NOT IN (SELECT etiqueta_id FROM elemento_etiqueta)")


def obtener(con: sqlite3.Connection, elemento_id: int) -> Elemento | None:
    fila = con.execute("SELECT * FROM elemento WHERE id = ?", (elemento_id,)).fetchone()
    if fila is None:
        return None
    e = Elemento(**{k: fila[k] for k in fila.keys()})
    e.consumido = bool(e.consumido)
    e.personas = [(f[0], f[1]) for f in con.execute(
        "SELECT p.nombre, ep.rol FROM elemento_persona ep JOIN persona p ON p.id = ep.persona_id"
        " WHERE ep.elemento_id = ? ORDER BY ep.orden", (elemento_id,))]
    e.etiquetas = [f[0] for f in con.execute(
        "SELECT t.nombre FROM elemento_etiqueta et JOIN etiqueta t ON t.id = et.etiqueta_id"
        " WHERE et.elemento_id = ? ORDER BY t.nombre COLLATE ES", (elemento_id,))]
    e.valores = {f[0]: f[1] for f in con.execute(
        "SELECT campo_id, valor FROM valor_campo WHERE elemento_id = ?", (elemento_id,))}
    return e


def borrar(con: sqlite3.Connection, ids: list[int]) -> int:
    """Borra elementos (y sus portadas). Devuelve cuántos se han borrado."""
    if not ids:
        return 0
    marcas = ",".join("?" * len(ids))
    portadas = [f[0] for f in con.execute(
        f"SELECT portada FROM elemento WHERE id IN ({marcas}) AND portada <> ''", ids)]
    with transaccion(con):
        borrados = con.execute(f"DELETE FROM elemento WHERE id IN ({marcas})", ids).rowcount
        con.execute(f"DELETE FROM elemento_fts WHERE rowid IN ({marcas})", ids)
        _limpiar_huerfanos(con)
    for nombre in portadas:
        (rutas.carpeta_portadas() / nombre).unlink(missing_ok=True)
    return borrados


def mover(con: sqlite3.Connection, ids: list[int], ubicacion_id: int | None) -> None:
    from ..servicios import busqueda

    with transaccion(con):
        for id_ in ids:
            con.execute(
                "UPDATE elemento SET ubicacion_id = ?, modificado = datetime('now', 'localtime') WHERE id = ?",
                (ubicacion_id, id_),
            )
            busqueda.reindexar(con, id_)


def prestar(con: sqlite3.Connection, ids: list[int], a_quien: str, fecha: str) -> None:
    from ..servicios import busqueda

    a_quien = a_quien.strip()
    if not a_quien:
        raise ErrorElemento("Indica a quién se presta.")
    if not fecha_valida(fecha):
        raise ErrorElemento("La fecha del préstamo no es válida (AAAA-MM-DD).")
    with transaccion(con):
        for id_ in ids:
            con.execute("UPDATE elemento SET prestado_a = ?, fecha_prestamo = ?,"
                        " modificado = datetime('now', 'localtime') WHERE id = ?", (a_quien, fecha, id_))
            busqueda.reindexar(con, id_)


def devolver(con: sqlite3.Connection, ids: list[int]) -> None:
    from ..servicios import busqueda

    with transaccion(con):
        for id_ in ids:
            con.execute("UPDATE elemento SET prestado_a = '', fecha_prestamo = '',"
                        " modificado = datetime('now', 'localtime') WHERE id = ?", (id_,))
            busqueda.reindexar(con, id_)


def nombres_prestatarios(con: sqlite3.Connection) -> list[str]:
    return [f[0] for f in con.execute(
        "SELECT DISTINCT prestado_a FROM elemento WHERE prestado_a <> '' ORDER BY prestado_a COLLATE ES")]


def nombres_personas(con: sqlite3.Connection) -> list[str]:
    return [f[0] for f in con.execute("SELECT nombre FROM persona ORDER BY nombre COLLATE ES")]


def nombres_etiquetas(con: sqlite3.Connection) -> list[str]:
    return [f[0] for f in con.execute("SELECT nombre FROM etiqueta ORDER BY nombre COLLATE ES")]


def idiomas_usados(con: sqlite3.Connection) -> list[str]:
    usados = [f[0] for f in con.execute("SELECT DISTINCT idioma FROM elemento WHERE idioma <> ''")]
    return IDIOMAS + sorted(i for i in usados if i not in IDIOMAS)


def buscar_por_identificador(con: sqlite3.Connection, identificador: str) -> list[int]:
    valor = normalizar_identificador(identificador)
    if not valor:
        return []
    return [f[0] for f in con.execute("SELECT id FROM elemento WHERE identificador = ?", (valor,))]
