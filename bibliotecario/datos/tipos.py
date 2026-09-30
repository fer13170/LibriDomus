"""Tipos de elemento (Libro, Disco, Álbum de fotos...) y sus campos propios."""

import re
import sqlite3
from dataclasses import dataclass, field

from .. import texto

TIPOS_DATO = {
    "texto": "Texto",
    "texto_largo": "Texto largo",
    "numero": "Número",
    "fecha": "Fecha",
    "lista": "Lista de opciones",
    "si_no": "Sí / No",
}


class ErrorTipo(Exception):
    """Operación no permitida sobre los tipos de elemento (mensaje para el usuario)."""


@dataclass
class Campo:
    id: int | None
    clave: str
    etiqueta: str
    tipo_dato: str
    opciones: list[str] = field(default_factory=list)
    orden: int = 0
    oculto: bool = False


@dataclass
class TipoElemento:
    id: int | None
    nombre: str
    icono: str = ""
    verbo_consumo: str = "Leído"
    personal: bool = False
    roles: list[str] = field(default_factory=list)
    predefinido: bool = False
    orden: int = 0
    campos: list[Campo] = field(default_factory=list)


def _separar(valor: str) -> list[str]:
    return [p.strip() for p in valor.split(";") if p.strip()]


def listar(con: sqlite3.Connection, con_campos: bool = True) -> list[TipoElemento]:
    tipos = [
        TipoElemento(
            id=f["id"], nombre=f["nombre"], icono=f["icono"], verbo_consumo=f["verbo_consumo"],
            personal=bool(f["personal"]), roles=_separar(f["roles"]), predefinido=bool(f["predefinido"]),
            orden=f["orden"],
        )
        for f in con.execute("SELECT * FROM tipo_elemento ORDER BY orden, nombre COLLATE ES")
    ]
    if con_campos:
        for tipo in tipos:
            tipo.campos = campos(con, tipo.id, incluir_ocultos=True)
    return tipos


def obtener(con: sqlite3.Connection, tipo_id: int) -> TipoElemento | None:
    return next((t for t in listar(con) if t.id == tipo_id), None)


def por_nombre(con: sqlite3.Connection, nombre: str) -> TipoElemento | None:
    return next((t for t in listar(con) if t.nombre.casefold() == nombre.casefold()), None)


def campos(con: sqlite3.Connection, tipo_id: int, incluir_ocultos: bool = False) -> list[Campo]:
    sql = "SELECT * FROM campo WHERE tipo_elemento_id = ?" + ("" if incluir_ocultos else " AND oculto = 0")
    return [
        Campo(id=f["id"], clave=f["clave"], etiqueta=f["etiqueta"], tipo_dato=f["tipo_dato"],
              opciones=_separar(f["opciones"]), orden=f["orden"], oculto=bool(f["oculto"]))
        for f in con.execute(sql + " ORDER BY orden, id", (tipo_id,))
    ]


def _clave_de(etiqueta: str) -> str:
    clave = re.sub(r"[^a-z0-9]+", "_", texto.sin_acentos(etiqueta).lower()).strip("_")
    return clave or "campo"


def guardar(con: sqlite3.Connection, tipo: TipoElemento) -> int:
    """Crea o actualiza un tipo y sus campos. Los campos que desaparecen de la lista
    se ocultan (no se borran) para no perder los datos ya introducidos."""
    from .conexion import transaccion

    nombre = tipo.nombre.strip()
    if not nombre:
        raise ErrorTipo("El tipo necesita un nombre.")
    etiquetas = [c.etiqueta.strip() for c in tipo.campos]
    if any(not e for e in etiquetas):
        raise ErrorTipo("Todos los campos necesitan un nombre.")
    if len({e.casefold() for e in etiquetas}) != len(etiquetas):
        raise ErrorTipo("Hay dos campos con el mismo nombre.")
    for c in tipo.campos:
        if c.tipo_dato not in TIPOS_DATO:
            raise ErrorTipo(f"Tipo de dato desconocido: {c.tipo_dato}")
        if c.tipo_dato == "lista" and not c.opciones:
            raise ErrorTipo(f"El campo «{c.etiqueta}» es una lista y necesita opciones.")

    with transaccion(con):
        valores = (nombre, tipo.icono.strip(), tipo.verbo_consumo.strip() or "Leído",
                   int(tipo.personal), ";".join(r.strip() for r in tipo.roles if r.strip()))
        try:
            if tipo.id is None:
                orden = con.execute("SELECT COALESCE(MAX(orden), -1) + 1 FROM tipo_elemento").fetchone()[0]
                tipo.id = con.execute(
                    "INSERT INTO tipo_elemento (nombre, icono, verbo_consumo, personal, roles, predefinido, orden)"
                    " VALUES (?, ?, ?, ?, ?, 0, ?)", (*valores, orden),
                ).lastrowid
            else:
                con.execute(
                    "UPDATE tipo_elemento SET nombre = ?, icono = ?, verbo_consumo = ?, personal = ?, roles = ?"
                    " WHERE id = ?", (*valores, tipo.id),
                )
        except sqlite3.IntegrityError as error:
            raise ErrorTipo(f"Ya existe un tipo llamado «{nombre}».") from error

        existentes = {c.id: c for c in campos(con, tipo.id, incluir_ocultos=True)}
        claves_usadas = {c.clave for c in existentes.values()}
        conservados: set[int] = set()
        for orden, c in enumerate(tipo.campos):
            opciones = ";".join(o.strip() for o in c.opciones if o.strip())
            if c.id in existentes:
                con.execute(
                    "UPDATE campo SET etiqueta = ?, tipo_dato = ?, opciones = ?, orden = ?, oculto = ? WHERE id = ?",
                    (c.etiqueta.strip(), c.tipo_dato, opciones, orden, int(c.oculto), c.id),
                )
                conservados.add(c.id)
            else:
                clave, n = _clave_de(c.etiqueta), 2
                base = clave
                while clave in claves_usadas:
                    clave, n = f"{base}_{n}", n + 1
                claves_usadas.add(clave)
                c.id = con.execute(
                    "INSERT INTO campo (tipo_elemento_id, clave, etiqueta, tipo_dato, opciones, orden, oculto)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (tipo.id, clave, c.etiqueta.strip(), c.tipo_dato, opciones, orden, int(c.oculto)),
                ).lastrowid
                conservados.add(c.id)
        for campo_id in existentes.keys() - conservados:
            con.execute("UPDATE campo SET oculto = 1 WHERE id = ?", (campo_id,))
    return tipo.id


def borrar(con: sqlite3.Connection, tipo_id: int) -> None:
    fila = con.execute("SELECT predefinido FROM tipo_elemento WHERE id = ?", (tipo_id,)).fetchone()
    if fila is None:
        return
    if fila["predefinido"]:
        raise ErrorTipo("Los tipos predefinidos no se pueden borrar (sí se pueden ampliar).")
    usos = con.execute("SELECT COUNT(*) FROM elemento WHERE tipo_id = ?", (tipo_id,)).fetchone()[0]
    if usos:
        raise ErrorTipo(f"No se puede borrar: hay {usos} elementos de este tipo.")
    con.execute("DELETE FROM tipo_elemento WHERE id = ?", (tipo_id,))
