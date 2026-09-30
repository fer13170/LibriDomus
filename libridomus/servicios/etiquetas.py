"""Etiquetas para cajas y baldas en folio A4 (8 por hoja, para recortar).

Cada etiqueta lleva: código en grande, ruta completa, resumen del contenido y un QR
con el código (el QR contiene solo el texto del código, p. ej. 'PB-SAL-EA-B3'; al
escanearlo con el móvil o un lector se obtiene ese texto, que se puede escribir o
pegar en «Ir a código» de la ventana principal).
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import segno
from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from ..datos import ubicaciones

COLUMNAS, FILAS = 2, 4          # 8 etiquetas por folio
MARGEN_MM = 10
SEPARACION_MM = 4
PPP = 300                        # resolución del PDF (puntos por pulgada)


@dataclass
class DatosEtiqueta:
    codigo: str
    nombre: str
    ruta: str
    total: int
    titulos: list[str]


def datos_etiqueta(con: sqlite3.Connection, ubicacion_id: int, max_titulos: int) -> DatosEtiqueta:
    u = ubicaciones.obtener(con, ubicacion_id)
    ids = ubicaciones.descendientes(con, ubicacion_id)
    marcas = ",".join("?" * len(ids))
    total = con.execute(f"SELECT COUNT(*) FROM elemento WHERE ubicacion_id IN ({marcas})", ids).fetchone()[0]
    titulos = [f[0] for f in con.execute(
        f"SELECT titulo FROM elemento WHERE ubicacion_id IN ({marcas}) ORDER BY titulo COLLATE ES LIMIT ?",
        [*ids, max_titulos])] if max_titulos else []
    return DatosEtiqueta(codigo=u.codigo, nombre=u.nombre, total=total, titulos=titulos,
                         ruta=ubicaciones.ruta_texto(con, ubicacion_id, incluir_raiz=False))


def _mm(valor: float) -> float:
    return valor / 25.4 * PPP


def _dibujar_qr(p: QPainter, texto: str, zona: QRectF) -> None:
    """Dibuja el QR módulo a módulo (vectorial: nítido a cualquier tamaño)."""
    qr = segno.make(texto, error="m")
    matriz = list(qr.matrix_iter(border=2))
    lado = zona.width() / len(matriz)
    p.fillRect(zona, Qt.GlobalColor.white)
    for fila, modulos in enumerate(matriz):
        for columna, oscuro in enumerate(modulos):
            if oscuro:
                p.fillRect(QRectF(zona.x() + columna * lado, zona.y() + fila * lado, lado + 0.5, lado + 0.5),
                           Qt.GlobalColor.black)


def _dibujar_etiqueta(p: QPainter, d: DatosEtiqueta, caja: QRectF) -> None:
    relleno = _mm(4)
    p.setPen(QPen(QColor("#999999"), _mm(0.2), Qt.PenStyle.DashLine))  # guía de corte
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(caja, _mm(2), _mm(2))
    interior = caja.adjusted(relleno, relleno, -relleno, -relleno)
    lado_qr = _mm(28)
    _dibujar_qr(p, d.codigo, QRectF(interior.right() - lado_qr, interior.top(), lado_qr, lado_qr))
    ancho_texto = interior.width() - lado_qr - _mm(3)
    p.setPen(Qt.GlobalColor.black)

    # Código: lo más grande posible sin salirse
    fuente = QFont("Segoe UI", 20, QFont.Weight.Bold)
    while fuente.pointSizeF() > 9 and QFontMetricsF(fuente, p.device()).horizontalAdvance(d.codigo) > ancho_texto:
        fuente.setPointSizeF(fuente.pointSizeF() - 1)
    p.setFont(fuente)
    alto_codigo = QFontMetricsF(fuente, p.device()).height()
    p.drawText(QRectF(interior.left(), interior.top(), ancho_texto, alto_codigo),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, d.codigo)
    y = interior.top() + alto_codigo + _mm(1)

    # Nombre y ruta
    fuente_nombre = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
    p.setFont(fuente_nombre)
    alto = QFontMetricsF(fuente_nombre, p.device()).height()
    p.drawText(QRectF(interior.left(), y, ancho_texto, alto), Qt.AlignmentFlag.AlignLeft,
               QFontMetricsF(fuente_nombre, p.device()).elidedText(d.nombre, Qt.TextElideMode.ElideRight, ancho_texto))
    y += alto
    fuente_ruta = QFont("Segoe UI", 8)
    p.setFont(fuente_ruta)
    zona_ruta = QRectF(interior.left(), y, ancho_texto, interior.top() + lado_qr - y)
    p.drawText(zona_ruta, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, d.ruta)
    y = max(interior.top() + lado_qr, y + QFontMetricsF(fuente_ruta, p.device()).height()) + _mm(2)

    # Contenido
    p.setPen(QPen(QColor("#666666"), _mm(0.2)))
    p.drawLine(int(interior.left()), int(y), int(interior.right()), int(y))
    y += _mm(1.5)
    p.setPen(Qt.GlobalColor.black)
    fuente_lista = QFont("Segoe UI", 8)
    metrica = QFontMetricsF(fuente_lista, p.device())
    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    cabecera = "Vacía" if d.total == 0 else f"Contiene {d.total} elemento{'s' if d.total != 1 else ''}"
    p.drawText(QRectF(interior.left(), y, interior.width(), metrica.height()), Qt.AlignmentFlag.AlignLeft, cabecera)
    y += metrica.height()
    p.setFont(fuente_lista)
    lineas = [f"• {t}" for t in d.titulos]
    if d.total > len(d.titulos) and d.titulos:
        lineas.append(f"… y {d.total - len(d.titulos)} más")
    for linea in lineas:
        if y + metrica.height() > interior.bottom():
            break
        p.drawText(QRectF(interior.left(), y, interior.width(), metrica.height()), Qt.AlignmentFlag.AlignLeft,
                   metrica.elidedText(linea, Qt.TextElideMode.ElideRight, interior.width()))
        y += metrica.height()


def generar_pdf(con: sqlite3.Connection, ubicacion_ids: list[int], destino: Path | str,
                max_titulos: int = 6) -> int:
    """Crea el PDF de etiquetas. Devuelve el número de páginas."""
    if not ubicacion_ids:
        raise ValueError("No hay ubicaciones para las etiquetas.")
    datos = [datos_etiqueta(con, i, max_titulos) for i in ubicacion_ids]
    pdf = QPdfWriter(str(destino))
    pdf.setResolution(PPP)
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter))
    pdf.setTitle("Etiquetas de ubicaciones")
    pdf.setCreator("LibriDomus")
    ancho = (210 - 2 * MARGEN_MM - (COLUMNAS - 1) * SEPARACION_MM) / COLUMNAS
    alto = (297 - 2 * MARGEN_MM - (FILAS - 1) * SEPARACION_MM) / FILAS
    por_pagina = COLUMNAS * FILAS
    p = QPainter(pdf)
    try:
        for n, d in enumerate(datos):
            if n and n % por_pagina == 0:
                pdf.newPage()
            posicion = n % por_pagina
            columna, fila = posicion % COLUMNAS, posicion // COLUMNAS
            caja = QRectF(_mm(MARGEN_MM + columna * (ancho + SEPARACION_MM)),
                          _mm(MARGEN_MM + fila * (alto + SEPARACION_MM)), _mm(ancho), _mm(alto))
            _dibujar_etiqueta(p, d, caja)
    finally:
        p.end()
    return (len(datos) - 1) // por_pagina + 1
