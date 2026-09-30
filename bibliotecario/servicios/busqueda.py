"""Búsqueda de elementos: índice de texto completo (FTS5) y filtros.

Sintaxis que entiende el cuadro de búsqueda:
  palabras sueltas     -> deben aparecer todas; se buscan por prefijo ('garc' encuentra 'García')
  "frase exacta"       -> entre comillas
  -palabra             -> excluye los resultados que la contengan
Los acentos y las mayúsculas no importan.
"""

import re
import sqlite3
from dataclasses import dataclass

from .. import texto
from ..datos import ubicaciones


# ---------------------------------------------------------------- índice

def reindexar(con: sqlite3.Connection, elemento_id: int) -> None:
    """Actualiza la entrada del índice de búsqueda de un elemento."""
    con.execute("DELETE FROM elemento_fts WHERE rowid = ?", (elemento_id,))
    fila = con.execute("SELECT * FROM elemento WHERE id = ?", (elemento_id,)).fetchone()
    if fila is None:
        return
    personas = " ".join(f[0] for f in con.execute(
        "SELECT p.nombre FROM elemento_persona ep JOIN persona p ON p.id = ep.persona_id WHERE ep.elemento_id = ?",
        (elemento_id,)))
    etiquetas = " ".join(f[0] for f in con.execute(
        "SELECT t.nombre FROM elemento_etiqueta et JOIN etiqueta t ON t.id = et.etiqueta_id WHERE et.elemento_id = ?",
        (elemento_id,)))
    campos = " ".join(f[0] for f in con.execute(
        "SELECT valor FROM valor_campo WHERE elemento_id = ?", (elemento_id,)))
    texto = " ".join(str(v) for v in (
        fila["subtitulo"], fila["identificador"], fila["lugar_evento"], fila["fecha_desde"],
        fila["fecha_hasta"], fila["prestado_a"], fila["notas"], campos) if v)
    ruta = ubicaciones.ruta_texto(con, fila["ubicacion_id"]) if fila["ubicacion_id"] else ""
    con.execute(
        "INSERT INTO elemento_fts (rowid, titulo, personas, etiquetas, texto, ubicacion) VALUES (?, ?, ?, ?, ?, ?)",
        (elemento_id, fila["titulo"], personas, etiquetas, texto, ruta),
    )


def reindexar_ubicacion(con: sqlite3.Connection, ubicacion_id: int) -> None:
    """Tras renombrar o mover una ubicación cambia la ruta de todo lo que contiene."""
    ids = ubicaciones.descendientes(con, ubicacion_id)
    marcas = ",".join("?" * len(ids))
    for fila in con.execute(f"SELECT id FROM elemento WHERE ubicacion_id IN ({marcas})", ids).fetchall():
        reindexar(con, fila[0])


def reindexar_todo(con: sqlite3.Connection) -> int:
    con.execute("DELETE FROM elemento_fts")
    ids = [f[0] for f in con.execute("SELECT id FROM elemento").fetchall()]
    for id_ in ids:
        reindexar(con, id_)
    return len(ids)


# ---------------------------------------------------------------- consulta

_PALABRA = re.compile(r"\w+", re.UNICODE)
_TROZO = re.compile(r'(-?)"([^"]*)"|(\S+)')


def construir_consulta(texto: str) -> str | None:
    """Convierte lo que escribe el usuario en una consulta FTS5 segura.

    Devuelve None si no hay nada que buscar (las exclusiones solas las trata
    ``construir_exclusion``, porque FTS5 no admite una consulta que empiece por NOT).
    """
    incluir, excluir = _terminos(texto)
    if not incluir:
        return None
    consulta = " AND ".join(incluir)
    for termino in excluir:
        consulta += f" NOT {termino}"
    return consulta


def construir_exclusion(texto: str) -> str | None:
    """Si la búsqueda solo tiene exclusiones ('-palabra'), consulta con lo que hay que quitar."""
    incluir, excluir = _terminos(texto)
    return " OR ".join(excluir) if excluir and not incluir else None


def _terminos(texto: str) -> tuple[list[str], list[str]]:
    incluir: list[str] = []
    excluir: list[str] = []
    for negado_frase, frase, suelto in _TROZO.findall(texto or ""):
        if frase or negado_frase:
            palabras = _PALABRA.findall(frase)
            if palabras:
                termino = '"' + " ".join(palabras) + '"'
                (excluir if negado_frase else incluir).append(termino)
            continue
        negado = suelto.startswith("-") and len(suelto) > 1
        for palabra in _PALABRA.findall(suelto):
            termino = f'"{palabra}"*'
            (excluir if negado else incluir).append(termino)
    return incluir, excluir


@dataclass
class Filtros:
    texto: str = ""
    tipo_id: int | None = None
    ubicacion_id: int | None = None      # incluye sus sububicaciones
    sin_ubicacion: bool = False
    etiqueta: str = ""
    persona: str = ""
    estado: str = ""
    idioma: str = ""
    solo_prestados: bool = False
    solo_no_consumidos: bool = False


@dataclass
class Resultado:
    id: int
    tipo_id: int
    tipo: str
    icono: str
    titulo: str
    subtitulo: str
    creadores: str
    anio: int | None
    ubicacion_id: int | None
    ubicacion: str
    estado: str
    idioma: str
    consumido: bool
    valoracion: int
    prestado_a: str
    identificador: str
    portada: str


def buscar(con: sqlite3.Connection, filtros: Filtros) -> list[Resultado]:
    condiciones: list[str] = []
    parametros: list = []
    union_fts = ""
    orden = ""

    consulta = construir_consulta(filtros.texto)
    if consulta:
        union_fts = "JOIN elemento_fts f ON f.rowid = e.id"
        condiciones.append("elemento_fts MATCH ?")
        parametros.append(consulta)
        # El título pesa más que el resto de columnas al ordenar por relevancia.
        orden = "ORDER BY bm25(elemento_fts, 10.0, 5.0, 3.0, 1.0, 1.0)"
    else:
        exclusion = construir_exclusion(filtros.texto)
        if exclusion:
            condiciones.append("e.id NOT IN (SELECT rowid FROM elemento_fts WHERE elemento_fts MATCH ?)")
            parametros.append(exclusion)
    if filtros.tipo_id is not None:
        condiciones.append("e.tipo_id = ?")
        parametros.append(filtros.tipo_id)
    if filtros.sin_ubicacion:
        condiciones.append("e.ubicacion_id IS NULL")
    elif filtros.ubicacion_id is not None:
        ids = ubicaciones.descendientes(con, filtros.ubicacion_id)
        condiciones.append(f"e.ubicacion_id IN ({','.join('?' * len(ids))})")
        parametros.extend(ids)
    if filtros.etiqueta:
        condiciones.append(
            "e.id IN (SELECT et.elemento_id FROM elemento_etiqueta et JOIN etiqueta t ON t.id = et.etiqueta_id"
            " WHERE t.nombre = ? COLLATE NOCASE)")
        parametros.append(filtros.etiqueta)
    if filtros.persona:
        condiciones.append(
            "e.id IN (SELECT ep.elemento_id FROM elemento_persona ep JOIN persona p ON p.id = ep.persona_id"
            " WHERE p.nombre = ? COLLATE NOCASE)")
        parametros.append(filtros.persona)
    if filtros.estado:
        condiciones.append("e.estado = ?")
        parametros.append(filtros.estado)
    if filtros.idioma:
        condiciones.append("e.idioma = ?")
        parametros.append(filtros.idioma)
    if filtros.solo_prestados:
        condiciones.append("e.prestado_a <> ''")
    if filtros.solo_no_consumidos:
        condiciones.append("e.consumido = 0")

    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    sql = f"""
        SELECT e.id, e.tipo_id, t.nombre AS tipo, t.icono, e.titulo, e.subtitulo, e.anio, e.ubicacion_id,
               e.estado, e.idioma, e.consumido, e.valoracion, e.prestado_a, e.identificador, e.portada,
               c.creadores
        FROM elemento e JOIN tipo_elemento t ON t.id = e.tipo_id {union_fts}
        LEFT JOIN (SELECT ep.elemento_id, GROUP_CONCAT(p.nombre, ', ' ORDER BY ep.orden) AS creadores
                   FROM elemento_persona ep JOIN persona p ON p.id = ep.persona_id
                   GROUP BY ep.elemento_id) c ON c.elemento_id = e.id
        {donde}
        {orden}
    """
    rutas = ubicaciones.rutas_todas(con)
    resultados = [
        Resultado(
            id=f["id"], tipo_id=f["tipo_id"], tipo=f["tipo"], icono=f["icono"], titulo=f["titulo"],
            subtitulo=f["subtitulo"], creadores=f["creadores"] or "", anio=f["anio"],
            ubicacion_id=f["ubicacion_id"], ubicacion=rutas.get(f["ubicacion_id"], ""),
            estado=f["estado"], idioma=f["idioma"], consumido=bool(f["consumido"]),
            valoracion=f["valoracion"], prestado_a=f["prestado_a"], identificador=f["identificador"],
            portada=f["portada"],
        )
        for f in con.execute(sql, parametros)
    ]
    if not consulta:
        # Orden alfabético sin acentos. Se hace aquí (una clave por fila) y no con
        # 'COLLATE ES' en SQL, que llamaría a Python en cada comparación: con 20.000
        # elementos pasa de ~2,4 s a unas décimas.
        resultados.sort(key=lambda r: texto.clave_orden(r.titulo))
    return resultados
