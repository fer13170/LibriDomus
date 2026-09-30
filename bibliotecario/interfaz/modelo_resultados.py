"""Modelo de la tabla de resultados de la ventana principal."""

from PySide6.QtCore import QAbstractTableModel, QMimeData, QModelIndex, QSortFilterProxyModel, Qt

from .. import texto
from ..servicios.busqueda import Resultado

MIME_ELEMENTOS = "application/x-bibliotecario-elementos"

COLUMNAS = ["Tipo", "Título", "Personas", "Año", "Ubicación", "Estado", "Prestado a"]
ROL_CLAVE_ORDEN = Qt.ItemDataRole.UserRole + 1


class ModeloResultados(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filas: list[Resultado] = []

    def establecer(self, filas: list[Resultado]) -> None:
        self.beginResetModel()
        self.filas = filas
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
        if rol == ROL_CLAVE_ORDEN:
            if col == 3:
                return r.anio or 0
            return texto.clave_orden(self.data(indice, Qt.ItemDataRole.DisplayRole))
        if rol == Qt.ItemDataRole.ToolTipRole and col == 4:
            return r.ubicacion
        if rol == Qt.ItemDataRole.ForegroundRole and col == 4 and not r.ubicacion:
            return Qt.GlobalColor.gray
        return None


class OrdenadorResultados(QSortFilterProxyModel):
    """Ordena sin tener en cuenta acentos y el año como número."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(ROL_CLAVE_ORDEN)
