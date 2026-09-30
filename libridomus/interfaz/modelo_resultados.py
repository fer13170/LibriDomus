"""Modelo de la tabla de resultados de la ventana principal."""

import html

from PySide6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, Qt, QUrl

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyledItemDelegate

from .. import texto
from ..servicios import portadas
from ..servicios.busqueda import Resultado
from . import tema

MIME_ELEMENTOS = "application/x-libridomus-elementos"
_BANDERAS_CELDA = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled
_SIN_BANDERAS = Qt.ItemFlag.NoItemFlags

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

    # --- cambios de filas sueltas (tras guardar un elemento no hace falta recargarlo todo)
    def fila_de(self, elemento_id: int) -> int | None:
        return next((i for i, r in enumerate(self.filas) if r.id == elemento_id), None)

    def poner(self, resultado: Resultado) -> None:
        """Sustituye la fila del elemento o, si no estaba, la añade al final."""
        fila = self.fila_de(resultado.id)
        if fila is None:
            self.beginInsertRows(QModelIndex(), len(self.filas), len(self.filas))
            self.filas.append(resultado)
            self.endInsertRows()
        else:
            self.filas[fila] = resultado
            self.dataChanged.emit(self.index(fila, 0), self.index(fila, len(COLUMNAS) - 1))

    def quitar(self, elemento_id: int) -> None:
        fila = self.fila_de(elemento_id)
        if fila is not None:
            self.beginRemoveRows(QModelIndex(), fila, fila)
            del self.filas[fila]
            self.endRemoveRows()

    # --- arrastrar elementos hacia el árbol de ubicaciones para moverlos
    def flags(self, indice):
        # Qt llama a esto por cada celda al seleccionar (Ctrl+A con 90.000 filas = 540.000 veces):
        # se devuelve un valor precalculado en lugar de combinar enumeraciones en cada llamada.
        return _BANDERAS_CELDA if indice.isValid() else _SIN_BANDERAS

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
                r.tipo, r.titulo + (f": {r.subtitulo}" if r.subtitulo else ""), r.creadores,
                str(r.anio) if r.anio else "", r.ubicacion or "Sin ubicación", r.estado, r.prestado_a,
            ][col]
        if rol == Qt.ItemDataRole.DecorationRole:
            if col == 0:
                return tema.icono(r.icono or "package", "primario")
            if col == 6 and r.prestado_a:
                return tema.icono("handshake", "acento", tema.px(15))
            return None
        if rol == Qt.ItemDataRole.FontRole and col == 1:
            negrita = QFont()
            negrita.setWeight(QFont.Weight.DemiBold)
            return negrita
        if rol == Qt.ItemDataRole.ToolTipRole and col == 4:
            return r.ubicacion
        if rol == Qt.ItemDataRole.ToolTipRole and col == 1 and r.portada:
            ruta = portadas.ruta(r.portada)
            if ruta:  # al pasar el ratón por el título se ve la portada
                return f'<img src="{QUrl.fromLocalFile(str(ruta)).toString()}" width="160"><br>{html.escape(r.titulo)}'
        if rol == Qt.ItemDataRole.ForegroundRole and ((col == 4 and not r.ubicacion) or col in (3, 5)):
            return QColor(tema.color("texto_suave"))
        if rol == Qt.ItemDataRole.ForegroundRole and col == 6:
            return QColor(tema.color("acento"))
        return None


class DelegadoRuta(QStyledItemDelegate):
    """En la columna Ubicación se recorta por la izquierda: se ve la balda o caja final."""

    def initStyleOption(self, opcion, indice):  # noqa: N802 - nombre impuesto por Qt
        super().initStyleOption(opcion, indice)
        opcion.textElideMode = Qt.TextElideMode.ElideLeft
