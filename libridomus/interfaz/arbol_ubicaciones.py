"""Árbol de ubicaciones reutilizable (ventana principal, selector y editor)."""

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QTreeWidget, QTreeWidgetItem)

from ..datos import ubicaciones
from .. import texto
from . import tema
from .modelo_resultados import MIME_ELEMENTOS

ROL_ID = Qt.ItemDataRole.UserRole
ROL_CUENTA = Qt.ItemDataRole.UserRole + 1
ID_TODAS = -1          # nodo especial "Toda la colección"
ID_SIN_UBICACION = -2  # nodo especial "Sin ubicación"


class DelegadoContador(QStyledItemDelegate):
    """Dibuja el número de elementos alineado a la derecha y en color suave."""

    def paint(self, pintor, opcion, indice):
        cuenta = indice.data(ROL_CUENTA)
        if not cuenta:
            super().paint(pintor, opcion, indice)
            return
        opt = QStyleOptionViewItem(opcion)
        self.initStyleOption(opt, indice)
        texto_cuenta = f"{cuenta:,}".replace(",", ".")
        ancho = opt.fontMetrics.horizontalAdvance(texto_cuenta) + tema.px(12)
        # El nombre se recorta antes de llegar al número.
        disponible = opt.rect.width() - ancho - opt.decorationSize.width() - tema.px(14)
        opt.text = opt.fontMetrics.elidedText(opt.text, Qt.TextElideMode.ElideRight, max(20, disponible))
        estilo = opt.widget.style() if opt.widget else QApplication.style()
        estilo.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, pintor, opt.widget)
        seleccionado = bool(opt.state & QStyle.StateFlag.State_Selected)
        pintor.save()
        pintor.setPen(QColor(tema.color("seleccion_texto" if seleccionado else "texto_suave")))
        pintor.setFont(opt.font)
        zona = QRect(opt.rect.right() - ancho, opt.rect.top(), ancho - tema.px(6), opt.rect.height())
        pintor.drawText(zona, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, texto_cuenta)
        pintor.restore()


class ArbolUbicaciones(QTreeWidget):
    """Muestra el catálogo de ubicaciones.

    ``al_mover(ubicacion_id, nuevo_padre_id, indice)`` activa el arrastrar y soltar:
    el árbol no mueve nada por sí mismo, llama a la función y luego se recarga.
    """

    ubicacion_cambiada = Signal(object)  # id o None

    def __init__(self, con: sqlite3.Connection, contar: bool = False, especiales: bool = False,
                 al_mover: Callable[[int, int | None, int], None] | None = None,
                 al_soltar_elementos: Callable[[list[int], int | None], None] | None = None, parent=None):
        super().__init__(parent)
        self.con = con
        self.contar = contar
        self.especiales = especiales
        self.al_mover = al_mover
        self.al_soltar_elementos = al_soltar_elementos
        if al_soltar_elementos:
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setItemDelegate(DelegadoContador(self))
        self.setIconSize(QSize(tema.px(18), tema.px(18)))
        self.setIndentation(tema.px(16))
        self.setAnimated(True)
        self.currentItemChanged.connect(lambda actual, _anterior: self.ubicacion_cambiada.emit(self.id_actual()))
        if al_mover:
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.cargar()

    # ------------------------------------------------------------ carga

    def cargar(self, seleccionar: int | None = None) -> None:
        previo = self.id_actual()  # lo seleccionado antes de recargar
        anterior = previo if seleccionar is None else seleccionar
        abiertos = self._ids_expandidos()
        self.blockSignals(True)
        self.clear()
        cuentas = ubicaciones.contar_elementos(self.con) if self.contar else {}
        if self.especiales:
            total = self.con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
            sin = self.con.execute("SELECT COUNT(*) FROM elemento WHERE ubicacion_id IS NULL").fetchone()[0]
            self._nodo_especial("Toda la colección", ID_TODAS, "library", total)
        items: dict[int, QTreeWidgetItem] = {}
        for u in ubicaciones.todas(self.con):
            padre = items.get(u.padre_id) if u.padre_id else None
            item = QTreeWidgetItem(padre) if padre else QTreeWidgetItem(self)
            item.setText(0, u.nombre)
            item.setIcon(0, tema.icono(u.icono or "map-pin", "primario" if u.padre_id is None else "texto_suave"))
            item.setToolTip(0, f"{u.tipo} · código {u.codigo}" + (f"\n{u.descripcion}" if u.descripcion else ""))
            item.setData(0, ROL_ID, u.id)
            if self.contar:
                item.setData(0, ROL_CUENTA, cuentas.get(u.id, 0))
            items[u.id] = item
        if self.especiales and sin:
            self._nodo_especial("Sin ubicación", ID_SIN_UBICACION, "circle-help", sin)
        # Por defecto se ven la casa y sus plantas desplegadas.
        for id_, item in items.items():
            if id_ in abiertos or item.parent() is None:
                item.setExpanded(True)
        # Se vuelve a seleccionar lo que había SIN emitir la señal: recargar el árbol (p. ej. para
        # actualizar contadores) no debe provocar una recarga completa de la lista.
        if anterior is not None:
            self.seleccionar(anterior)
        elif self.especiales:
            self.setCurrentItem(self.topLevelItem(0))
        self.blockSignals(False)
        if self.id_actual() != previo:  # solo si de verdad cambia la ubicación seleccionada
            self.ubicacion_cambiada.emit(self.id_actual())

    def _nodo_especial(self, texto_: str, id_: int, icono: str, cuenta: int) -> None:
        item = QTreeWidgetItem(self)
        item.setText(0, texto_)
        item.setIcon(0, tema.icono(icono, "primario"))
        item.setData(0, ROL_ID, id_)
        item.setData(0, ROL_CUENTA, cuenta)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled & ~Qt.ItemFlag.ItemIsDropEnabled)
        fuente = item.font(0)
        fuente.setBold(True)
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
        for item in self.todos_los_items():
            if item.data(0, ROL_ID) == ubicacion_id:
                padre = item.parent()
                while padre:
                    padre.setExpanded(True)
                    padre = padre.parent()
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return True
        return False

    def todos_los_items(self):
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

    def destino_elementos(self, punto) -> tuple[bool, int | None]:
        """¿Se pueden soltar elementos en ese punto? Devuelve (válido, ubicacion_id)."""
        item = self.itemAt(punto)
        if item is None:
            return False, None
        id_ = item.data(0, ROL_ID)
        if id_ == ID_SIN_UBICACION:
            return True, None
        return (id_ is not None and id_ >= 0), id_

    def _soltar_elementos_admitido(self, event) -> bool:
        return bool(self.al_soltar_elementos) and event.mimeData().hasFormat(MIME_ELEMENTOS)

    def dragEnterEvent(self, event):  # noqa: N802 - nombre impuesto por Qt
        if self._soltar_elementos_admitido(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if self._soltar_elementos_admitido(event):
            valido, _ = self.destino_elementos(event.position().toPoint())
            event.acceptProposedAction() if valido else event.ignore()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if self._soltar_elementos_admitido(event):
            valido, destino = self.destino_elementos(event.position().toPoint())
            if not valido:
                event.ignore()
                return
            texto_ids = bytes(event.mimeData().data(MIME_ELEMENTOS)).decode()
            ids = [int(x) for x in texto_ids.split(",") if x]
            event.setDropAction(Qt.DropAction.IgnoreAction)  # la tabla no debe quitar filas por su cuenta
            event.accept()
            self.al_soltar_elementos(ids, destino)
            return
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
