"""Modelo de la tabla de resultados de la ventana principal."""

import html

from PySide6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, QSortFilterProxyModel, Qt, QUrl

from .. import texto
from ..servicios import portadas
from ..servicios.busqueda import Resultado

MIME_ELEMENTOS = "application/x-bibliotecario-elementos"

COLUMNAS = ["Tipo", "Título", "Personas", "Año", "Ubicación", "Estado", "Prestado a"]

# Clave de ordenación de cada columna (sin acentos ni mayúsculas; el año, como número).
CLAVES_ORDEN = [
    lambda r: texto.clave_orden(r.tipo),
    lambda r: texto.clave_orden(r.titulo + " " + r.subtitulo),
    lambda r: texto.clave_orden(r.creadores),
    lambda r: r.anio or 0,
    lambda r: texto.clave_orden(r.ubicacion),
    lambda r: texto.clave_orden(r.estado),
    lambda r: texto.clave_orden(r.prestado_a),
]


class ModeloResultados(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filas: list[Resultado] = []

    def establecer(self, filas: list[Resultado]) -> None:
        self.beginResetModel()
        self.filas = filas
        self.endResetModel()

    def sort(self, columna: int, orden=Qt.SortOrder.AscendingOrder):
        """Ordena la lista en Python: una clave por fila (rápido incluso con 20.000 filas)."""
        if not 0 <= columna < len(COLUMNAS):
            return
        # Reinicio completo del modelo (y no layoutChanged) para que la selección no quede
        # apuntando a filas que han cambiado de sitio.
        self.beginResetModel()
        self.filas.sort(key=CLAVES_ORDEN[columna], reverse=orden == Qt.SortOrder.DescendingOrder)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - nombre impuesto por Qt
        return 0 if parent.isValid() else len(self.filas)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNAS)

    def headerData(self, seccion, orientacion, rol=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[seccion]
        return None

    def resultado(self, fila: int) -> Resultado:
        return self.filas[fila]

    # --- arrastrar elementos hacia el árbol de ubicaciones para moverlos
    def flags(self, indice):
        base = super().flags(indice)
        return base | Qt.ItemFlag.ItemIsDragEnabled if indice.isValid() else base

    def mimeTypes(self):  # noqa: N802 - nombre impuesto por Qt
        return [MIME_ELEMENTOS]

    def mimeData(self, indices):  # noqa: N802
        ids = sorted({self.filas[i.row()].id for i in indices if i.isValid()})
        datos = QMimeData()
        datos.setData(MIME_ELEMENTOS, ",".join(map(str, ids)).encode())
        return datos

    def supportedDragActions(self):  # noqa: N802
        return Qt.DropAction.MoveAction

    def data(self, indice, rol=Qt.ItemDataRole.DisplayRole):
        if not indice.isValid():
            return None
        r = self.filas[indice.row()]
        col = indice.column()
        if rol == Qt.ItemDataRole.DisplayRole:
            return [
                f"{r.icono} {r.tipo}", r.titulo + (f": {r.subtitulo}" if r.subtitulo else ""), r.creadores,
                str(r.anio) if r.anio else "", r.ubicacion or "(sin ubicación)", r.estado, r.prestado_a,
            ][col]
        if rol == Qt.ItemDataRole.ToolTipRole and col == 4:
            return r.ubicacion
        if rol == Qt.ItemDataRole.ToolTipRole and col == 1 and r.portada:
            ruta = portadas.ruta(r.portada)
            if ruta:  # al pasar el ratón por el título se ve la portada
                return f'<img src="{QUrl.fromLocalFile(str(ruta)).toString()}" width="160"><br>{html.escape(r.titulo)}'
        if rol == Qt.ItemDataRole.ForegroundRole and col == 4 and not r.ubicacion:
            return Qt.GlobalColor.gray
        return None


class OrdenadorResultados(QSortFilterProxyModel):
    """Intermediario entre la tabla y el modelo: la ordenación la hace el propio modelo."""

    def sort(self, columna: int, orden=Qt.SortOrder.AscendingOrder):
        if self.sourceModel() is not None:
            self.sourceModel().sort(columna, orden)
