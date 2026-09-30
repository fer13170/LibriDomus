"""Árbol de ubicaciones reutilizable (ventana principal, selector y editor)."""

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from ..datos import ubicaciones
from .. import texto

ROL_ID = Qt.ItemDataRole.UserRole
ID_TODAS = -1          # nodo especial "Todas las ubicaciones"
ID_SIN_UBICACION = -2  # nodo especial "Sin ubicación"


class ArbolUbicaciones(QTreeWidget):
    """Muestra el catálogo de ubicaciones.

    ``al_mover(ubicacion_id, nuevo_padre_id, indice)`` activa el arrastrar y soltar:
    el árbol no mueve nada por sí mismo, llama a la función y luego se recarga.
    """

    ubicacion_cambiada = Signal(object)  # id o None

    def __init__(self, con: sqlite3.Connection, contar: bool = False, especiales: bool = False,
                 al_mover: Callable[[int, int | None, int], None] | None = None, parent=None):
        super().__init__(parent)
        self.con = con
        self.contar = contar
        self.especiales = especiales
        self.al_mover = al_mover
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.currentItemChanged.connect(lambda actual, _anterior: self.ubicacion_cambiada.emit(self.id_actual()))
        if al_mover:
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.cargar()

    # ------------------------------------------------------------ carga

    def cargar(self, seleccionar: int | None = None) -> None:
        anterior = self.id_actual() if seleccionar is None else seleccionar
        abiertos = self._ids_expandidos()
        self.blockSignals(True)
        self.clear()
        cuentas = ubicaciones.contar_elementos(self.con) if self.contar else {}
        if self.especiales:
            total = self.con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
            sin = self.con.execute("SELECT COUNT(*) FROM elemento WHERE ubicacion_id IS NULL").fetchone()[0]
            self._nodo_especial(f"Todas las ubicaciones ({total})", ID_TODAS)
        items: dict[int, QTreeWidgetItem] = {}
        for u in ubicaciones.todas(self.con):
            padre = items.get(u.padre_id) if u.padre_id else None
            item = QTreeWidgetItem(padre) if padre else QTreeWidgetItem(self)
            etiqueta = u.nombre
            if self.contar and cuentas.get(u.id):
                etiqueta += f"  ({cuentas[u.id]})"
            item.setText(0, etiqueta)
            item.setToolTip(0, f"{u.tipo} · código {u.codigo}" + (f"\n{u.descripcion}" if u.descripcion else ""))
            item.setData(0, ROL_ID, u.id)
            items[u.id] = item
        if self.especiales and sin:
            self._nodo_especial(f"Sin ubicación ({sin})", ID_SIN_UBICACION)
        # Por defecto se ven la casa y sus plantas desplegadas.
        for id_, item in items.items():
            if id_ in abiertos or item.parent() is None:
                item.setExpanded(True)
        self.blockSignals(False)
        if anterior is not None:
            self.seleccionar(anterior)
        elif self.especiales:
            self.setCurrentItem(self.topLevelItem(0))

    def _nodo_especial(self, texto_: str, id_: int) -> None:
        item = QTreeWidgetItem(self)
        item.setText(0, texto_)
        item.setData(0, ROL_ID, id_)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled & ~Qt.ItemFlag.ItemIsDropEnabled)
        fuente = item.font(0)
        fuente.setItalic(True)
        item.setFont(0, fuente)

    def _ids_expandidos(self) -> set[int]:
        resultado = set()
        pila = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while pila:
            item = pila.pop()
            if item.isExpanded():
                resultado.add(item.data(0, ROL_ID))
            pila.extend(item.child(i) for i in range(item.childCount()))
        return resultado

    # ------------------------------------------------------------ selección

    def id_actual(self) -> int | None:
        item = self.currentItem()
        return item.data(0, ROL_ID) if item else None

    def seleccionar(self, ubicacion_id: int | None) -> bool:
        for item in self._todos_los_items():
            if item.data(0, ROL_ID) == ubicacion_id:
                padre = item.parent()
                while padre:
                    padre.setExpanded(True)
                    padre = padre.parent()
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return True
        return False

    def _todos_los_items(self):
        pila = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while pila:
            item = pila.pop(0)
            yield item
            pila.extend(item.child(i) for i in range(item.childCount()))

    def filtrar(self, texto_filtro: str) -> None:
        """Oculta lo que no coincide (sin acentos), dejando visibles sus antepasados."""
        buscado = texto.clave_orden(texto_filtro.strip())

        def visitar(item: QTreeWidgetItem) -> bool:
            visible_hijo = False
            for i in range(item.childCount()):
                visible_hijo |= visitar(item.child(i))
            coincide = not buscado or buscado in texto.clave_orden(item.text(0))
            item.setHidden(not (coincide or visible_hijo))
            if buscado and visible_hijo:
                item.setExpanded(True)
            return coincide or visible_hijo

        for i in range(self.topLevelItemCount()):
            visitar(self.topLevelItem(i))

    # ------------------------------------------------------------ arrastrar y soltar

    def dropEvent(self, event):  # noqa: N802 - nombre impuesto por Qt
        if not self.al_mover:
            event.ignore()
            return
        origen = self.currentItem()
        destino = self.itemAt(event.position().toPoint())
        if origen is None or destino is None or destino is origen:
            event.ignore()
            return
        posicion = self.dropIndicatorPosition()
        destino_id = destino.data(0, ROL_ID)
        if destino_id is None or destino_id < 0:
            event.ignore()
            return
        if posicion == QAbstractItemView.DropIndicatorPosition.OnItem:
            nuevo_padre, indice = destino_id, None
        else:
            padre_item = destino.parent()
            nuevo_padre = padre_item.data(0, ROL_ID) if padre_item else None
            hermanos = padre_item or self.invisibleRootItem()
            indice = hermanos.indexOfChild(destino)
            # Si el origen es un hermano anterior, al quitarlo el índice se desplaza.
            if origen.parent() is destino.parent() and hermanos.indexOfChild(origen) < indice:
                indice -= 1
            if posicion == QAbstractItemView.DropIndicatorPosition.BelowItem:
                indice += 1
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        self.al_mover(origen.data(0, ROL_ID), nuevo_padre, indice)
