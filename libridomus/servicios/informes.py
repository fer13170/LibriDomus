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


FILAS_POR_PARTE = 2000  # los informes grandes se maquetan por partes para no agotar la memoria


def _envolver(cuerpo: str) -> str:
    return f"<html><head><style>{ESTILO}</style></head><body>{cuerpo}</body></html>"


def _cabecera(titulo: str, subtitulo: str) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"<h1>{html.escape(titulo)}</h1><p class='sub'>{html.escape(subtitulo)} · {NOMBRE} · {fecha}</p>"


def _partes(cabecera: str, bloques: list[tuple[str, list[Resultado], bool, bool]], vacio: str) -> list[str]:
    """Reparte los bloques (título de sección, filas, con ubicación, con préstamo) en partes de
    como mucho FILAS_POR_PARTE filas. Cada parte se maqueta y se libera por separado: el inventario
    completo de 90.000 elementos llegaba a 1 GB de memoria maquetado de una vez."""
    partes: list[str] = []
    actual, filas_actual = [cabecera], 0
    for titulo_seccion, filas, con_ubicacion, con_prestamo in bloques:
        for i in range(0, len(filas), FILAS_POR_PARTE):
            trozo = filas[i:i + FILAS_POR_PARTE]
            if filas_actual and filas_actual + len(trozo) > FILAS_POR_PARTE:
                partes.append("".join(actual))
                actual, filas_actual = [], 0
            if titulo_seccion:
                sufijo = " (continuación)" if i else ""
                actual.append(f"<h2>{titulo_seccion}{sufijo}</h2>")
            actual.append(_tabla(trozo, con_ubicacion, con_prestamo))
            filas_actual += len(trozo)
    if not bloques:
        actual.append(vacio)
    partes.append("".join(actual))
    return partes


def _nuevo_pdf(destino: Path | str, titulo: str) -> QPdfWriter:
    pdf = QPdfWriter(str(destino))
    # A 96 ppp un píxel del documento coincide con un punto del PDF (el texto sigue siendo vectorial).
    pdf.setResolution(96)
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(15, 12, 15, 12), QPageLayout.Unit.Millimeter))
    pdf.setTitle(titulo)
    pdf.setCreator(NOMBRE)
    return pdf


ALTO_PIE = 28


def _pintar(pdf: QPdfWriter, pintor: QPainter, documento: QTextDocument, primera: int,
            total: int | None, progreso=None) -> int:
    """Pinta el documento a partir de la página ``primera`` (0 = la primera del PDF).
    Devuelve cuántas páginas ha ocupado."""
    area = pdf.pageLayout().paintRectPixels(96)
    documento.setPageSize(QSizeF(area.width(), area.height() - ALTO_PIE))
    alto_pagina = documento.pageSize().height()
    paginas = documento.pageCount()
    for n in range(paginas):
        numero = primera + n + 1
        if progreso is not None and (n % 5 == 0 or n == paginas - 1):
            progreso(numero, total)  # la ventana muestra «página n» (o «n de N» si se conoce)
        if numero > 1:
            pdf.newPage()
        pintor.save()
        pintor.translate(0, -n * alto_pagina)
        documento.drawContents(pintor, QRectF(0, n * alto_pagina, area.width(), alto_pagina))
        pintor.restore()
        pintor.setFont(QFont("Segoe UI", 8))
        pintor.setPen(QColor("#666666"))
        pintor.drawText(QRectF(0, area.height() - ALTO_PIE + 8, area.width(), ALTO_PIE - 8),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        f"Página {numero} de {total}" if total else f"Página {numero}")
    return paginas


def escribir_partes(partes: list[str], destino: Path | str, titulo: str, progreso=None) -> int:
    """Maqueta cada parte HTML por separado (poca memoria) y las pinta seguidas. Devuelve las páginas.

    Con una sola parte el pie dice «Página n de N»; con varias, «Página n» (el total no se
    conoce sin maquetarlo todo antes, que es justo lo que se quiere evitar)."""
    pdf = _nuevo_pdf(destino, titulo)
    pintor = QPainter(pdf)
    paginas = 0
    try:
        for parte in partes:
            documento = QTextDocument()
            documento.setHtml(_envolver(parte))
            paginas += _pintar(pdf, pintor, documento, paginas, None if len(partes) > 1 else
                               _contar(documento, pdf), progreso)
            del documento  # se libera antes de maquetar la siguiente parte
    finally:
        pintor.end()
    return paginas


def _contar(documento: QTextDocument, pdf: QPdfWriter) -> int:
    area = pdf.pageLayout().paintRectPixels(96)
    documento.setPageSize(QSizeF(area.width(), area.height() - ALTO_PIE))
    return documento.pageCount()


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


def escribir_documento(documento: QTextDocument, destino: Path | str, titulo: str, progreso=None) -> int:
    """Pagina un documento ya construido (p. ej. el manual) con «Página n de N» al pie."""
    pdf = _nuevo_pdf(destino, titulo)
    pintor = QPainter(pdf)
    try:
        return _pintar(pdf, pintor, documento, 0, _contar(documento, pdf), progreso)
    finally:
        pintor.end()


def inventario(con: sqlite3.Connection, ubicacion_id: int | None, destino: Path | str, progreso=None) -> int:
    """Todo lo que hay en una ubicación (o en toda la casa), agrupado por ubicación. Devuelve el nº de elementos."""
    resultados = buscar(con, Filtros(ubicacion_id=ubicacion_id))
    grupos: dict[str, list[Resultado]] = defaultdict(list)
    for r in resultados:
        grupos[r.ubicacion or "(sin ubicación)"].append(r)
    orden_rutas = {u.id: i for i, u in enumerate(_recorrido_arbol(con))}
    ruta_a_id = {r.ubicacion: r.ubicacion_id for r in resultados}
    claves = sorted(grupos, key=lambda ruta: orden_rutas.get(ruta_a_id.get(ruta), 10**9))
    bloques = [(f"{html.escape(ruta)} ({len(grupos[ruta])})", grupos[ruta], False, False) for ruta in claves]
    nombre = ubicaciones.ruta_texto(con, ubicacion_id, incluir_raiz=True) if ubicacion_id else "Toda la casa"
    titulo = f"Inventario: {nombre}"
    escribir_partes(_partes(_cabecera(titulo, f"{len(resultados)} elementos"), bloques, "<p>No hay elementos.</p>"),
                    destino, titulo, progreso)
    return len(resultados)


def _recorrido_arbol(con: sqlite3.Connection):
    """Ubicaciones en el orden en que se ven en el árbol (para ordenar el inventario)."""
    def visitar(padre_id):
        for u in ubicaciones.hijos(con, padre_id):
            yield u
            yield from visitar(u.id)
    return list(visitar(None))


def prestados(con: sqlite3.Connection, destino: Path | str, progreso=None) -> int:
    lista = buscar(con, Filtros(solo_prestados=True))
    lista.sort(key=lambda r: (r.prestado_a.casefold(), r.titulo.casefold()))
    titulo = "Elementos prestados"
    bloques = [("", lista, True, True)] if lista else []
    escribir_partes(_partes(_cabecera(titulo, f"{len(lista)} elementos"), bloques, "<p>No hay nada prestado.</p>"),
                    destino, titulo, progreso)
    return len(lista)


def resultados(lista: list[Resultado], descripcion: str, destino: Path | str, progreso=None) -> int:
    titulo = "Resultado de la búsqueda"
    bloques = [("", lista, True, True)] if lista else []
    escribir_partes(_partes(_cabecera(titulo, f"{descripcion} · {len(lista)} elementos"), bloques,
                            "<p>Sin resultados.</p>"), destino, titulo, progreso)
    return len(lista)
