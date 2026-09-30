"""Capa que coloca los controles en fila y pasa a la línea siguiente cuando no caben
(se usa en la barra de filtros para que nada se corte con ventanas estrechas o letra grande)."""

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem


class CapaFluida(QLayout):
    def __init__(self, parent=None, espacio: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._espacio = espacio
        self.setContentsMargins(QMargins(0, 0, 0, 0))

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - nombres impuestos por Qt
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, indice: int):  # noqa: N802
        return self._items[indice] if 0 <= indice < len(self._items) else None

    def takeAt(self, indice: int):  # noqa: N802
        return self._items.pop(indice) if 0 <= indice < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, ancho: int) -> int:  # noqa: N802
        return self._colocar(QRect(0, 0, ancho, 0), solo_medir=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._colocar(rect, solo_medir=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        tamano = QSize()
        for item in self._items:
            tamano = tamano.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return tamano + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _colocar(self, rect: QRect, solo_medir: bool) -> int:
        m = self.contentsMargins()
        zona = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, alto_linea = zona.x(), zona.y(), 0
        for item in self._items:
            if item.widget() is not None and not item.widget().isVisible() and not solo_medir:
                continue
            tamano = item.sizeHint()
            if x + tamano.width() > zona.right() + 1 and alto_linea > 0:
                x, y = zona.x(), y + alto_linea + self._espacio
                alto_linea = 0
            if not solo_medir:
                item.setGeometry(QRect(QPoint(x, y), tamano))
            x += tamano.width() + self._espacio
            alto_linea = max(alto_linea, tamano.height())
        return y + alto_linea - rect.y() + m.bottom()

