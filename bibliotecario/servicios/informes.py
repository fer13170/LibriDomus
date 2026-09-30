"""Informes en PDF: inventario por ubicación, elementos prestados y resultado de una búsqueda."""

import html
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextCursor,
                           QTextDocument)

from .. import NOMBRE
from ..datos import ubicaciones
from .busqueda import Filtros, Resultado, buscar

ESTILO = """
body { font-family: 'Segoe UI'; font-size: 9pt; }
h1 { font-size: 14pt; margin-bottom: 0; }
p.sub { color: #555; margin-top: 2px; }
h2 { font-size: 10pt; background: #e8eef3; padding: 3px; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; border-bottom: 1px solid #888; padding: 2px 4px; }
td { padding: 2px 4px; border-bottom: 1px solid #ddd; vertical-align: top; }
"""


def _fila(r: Resultado, con_ubicacion: bool, con_prestamo: bool) -> str:
    # Sin el icono emoji: en PDF no todos los visores lo muestran bien.
    celdas = [html.escape(r.tipo),
              html.escape(r.titulo + (f": {r.subtitulo}" if r.subtitulo else "")),
              html.escape(r.creadores), str(r.anio or "")]
    if con_ubicacion:
        celdas.append(html.escape(r.ubicacion or "(sin ubicación)"))
    if con_prestamo:
        celdas.append(html.escape(r.prestado_a))
    return "<tr>" + "".join(f"<td>{c}</td>" for c in celdas) + "</tr>"


def _tabla(filas: list[Resultado], con_ubicacion: bool, con_prestamo: bool = False) -> str:
    columnas = [("Tipo", 12), ("Título", 38), ("Personas", 24), ("Año", 6)]
    if con_ubicacion:
        columnas.append(("Ubicación", 24))
    if con_prestamo:
        columnas.append(("Prestado a", 12))
    total = sum(ancho for _, ancho in columnas)
    cabecera = "".join(f"<th width='{ancho * 100 // total}%'>{nombre}</th>" for nombre, ancho in columnas)
    cuerpo = "".join(_fila(r, con_ubicacion, con_prestamo) for r in filas)
    # QTextDocument no aplica 'width' de CSS en tablas: hay que usar los atributos HTML.
    return f"<table width='100%' cellspacing='0' cellpadding='3'><tr>{cabecera}</tr>{cuerpo}</table>"


def _documento(titulo: str, subtitulo: str, cuerpo: str) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    return (f"<html><head><style>{ESTILO}</style></head><body>"
            f"<h1>{html.escape(titulo)}</h1><p class='sub'>{html.escape(subtitulo)} · {NOMBRE} · {fecha}</p>"
            f"{cuerpo}</body></html>")


def _escribir_pdf(contenido_html: str, destino: Path | str, titulo: str) -> int:
    documento = QTextDocument()
    documento.setHtml(contenido_html)
    return escribir_documento(documento, destino, titulo)


def markdown_a_pdf(markdown: str, destino: Path | str, titulo: str) -> int:
    """Convierte un texto Markdown (p. ej. el manual de usuario) en PDF A4."""
    documento = QTextDocument()
    documento.setDefaultFont(QFont("Segoe UI", 10))
    documento.setMarkdown(markdown)
    # El texto `entre comillas invertidas` se marca como monoespaciado; se fija Consolas
    # (incluida en Windows) para no depender de la fuente que elija el sistema.
    cursor = QTextCursor(documento)
    bloque = documento.begin()
    while bloque.isValid():
        iterador = bloque.begin()
        while not iterador.atEnd():
            fragmento = iterador.fragment()
            formato = fragmento.charFormat()
            if formato.fontFixedPitch():
                formato.setFontFamilies(["Consolas", "Courier New"])
                cursor.setPosition(fragmento.position())
                cursor.setPosition(fragmento.position() + fragmento.length(), QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(formato)
            iterador += 1
        bloque = bloque.next()
    return escribir_documento(documento, destino, titulo)


def escribir_documento(documento: QTextDocument, destino: Path | str, titulo: str) -> int:
    """Pagina el documento en A4 y añade 'Página n de N' al pie. Devuelve el número de páginas."""
    pdf = QPdfWriter(str(destino))
    # A 96 ppp un píxel del documento coincide con un punto del PDF (el texto sigue siendo vectorial).
    pdf.setResolution(96)
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(15, 12, 15, 12), QPageLayout.Unit.Millimeter))
    pdf.setTitle(titulo)
    pdf.setCreator(NOMBRE)
    area = pdf.pageLayout().paintRectPixels(96)
    alto_pie = 28
    documento.setPageSize(QSizeF(area.width(), area.height() - alto_pie))
    alto_pagina = documento.pageSize().height()
    paginas = documento.pageCount()
    pintor = QPainter(pdf)
    try:
        for n in range(paginas):
            if n:
                pdf.newPage()
            pintor.save()
            pintor.translate(0, -n * alto_pagina)
            documento.drawContents(pintor, QRectF(0, n * alto_pagina, area.width(), alto_pagina))
            pintor.restore()
            pintor.setFont(QFont("Segoe UI", 8))
            pintor.setPen(QColor("#666666"))
            pintor.drawText(QRectF(0, area.height() - alto_pie + 8, area.width(), alto_pie - 8),
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                            f"Página {n + 1} de {paginas}")
    finally:
        pintor.end()
    return paginas


def inventario(con: sqlite3.Connection, ubicacion_id: int | None, destino: Path | str) -> int:
    """Todo lo que hay en una ubicación (o en toda la casa), agrupado por ubicación. Devuelve el nº de elementos."""
    filtros = Filtros(ubicacion_id=ubicacion_id)
    resultados = buscar(con, filtros)
    grupos: dict[str, list[Resultado]] = defaultdict(list)
    for r in resultados:
        grupos[r.ubicacion or "(sin ubicación)"].append(r)
    orden_rutas = {u.id: i for i, u in enumerate(_recorrido_arbol(con))}
    ruta_a_id = {r.ubicacion: r.ubicacion_id for r in resultados}
    claves = sorted(grupos, key=lambda ruta: orden_rutas.get(ruta_a_id.get(ruta), 10**9))
    cuerpo = "".join(f"<h2>{html.escape(ruta)} ({len(grupos[ruta])})</h2>{_tabla(grupos[ruta], False)}"
                     for ruta in claves)
    nombre = ubicaciones.ruta_texto(con, ubicacion_id, incluir_raiz=True) if ubicacion_id else "Toda la casa"
    titulo = f"Inventario: {nombre}"
    _escribir_pdf(_documento(titulo, f"{len(resultados)} elementos", cuerpo or "<p>No hay elementos.</p>"),
                  destino, titulo)
    return len(resultados)


def _recorrido_arbol(con: sqlite3.Connection):
    """Ubicaciones en el orden en que se ven en el árbol (para ordenar el inventario)."""
    def visitar(padre_id):
        for u in ubicaciones.hijos(con, padre_id):
            yield u
            yield from visitar(u.id)
    return list(visitar(None))


def prestados(con: sqlite3.Connection, destino: Path | str) -> int:
    resultados = buscar(con, Filtros(solo_prestados=True))
    resultados.sort(key=lambda r: (r.prestado_a.casefold(), r.titulo.casefold()))
    titulo = "Elementos prestados"
    _escribir_pdf(_documento(titulo, f"{len(resultados)} elementos",
                             _tabla(resultados, True, True) if resultados else "<p>No hay nada prestado.</p>"),
                  destino, titulo)
    return len(resultados)


def resultados(lista: list[Resultado], descripcion: str, destino: Path | str) -> int:
    titulo = "Resultado de la búsqueda"
    _escribir_pdf(_documento(titulo, f"{descripcion} · {len(lista)} elementos",
                             _tabla(lista, True, True) if lista else "<p>Sin resultados.</p>"),
                  destino, titulo)
    return len(lista)
