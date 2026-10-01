"""Categorías: el campo de la ficha, el diálogo para elegirlas y el editor del catálogo."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QVBoxLayout, QWidget)

from .. import texto
from ..datos import categorias
from ..datos.categorias import ErrorCategoria
from . import comun, tema


def _pedir_nombre(padre: QWidget, titulo: str, actual: str = "") -> str | None:
    nombre, ok = QInputDialog.getText(padre, titulo, "Nombre de la categoría:", text=actual)
    return nombre.strip() if ok and nombre.strip() else None


class _ListaFiltrable(QWidget):
    """Buscador + lista de categorías (con casillas o sin ellas)."""

    def __init__(self, casillas: bool, parent=None):
        super().__init__(parent)
        self.casillas = casillas
        self.filtro = QLineEdit(placeholderText="Filtrar categorías…", clearButtonEnabled=True)
        self.lista = QListWidget()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.filtro)
        capa.addWidget(self.lista, 1)
        self.filtro.textChanged.connect(self._filtrar)

    def llenar(self, lista: list[categorias.Categoria], marcadas: set[str] = frozenset(),
               mostrar_usos: bool = False) -> None:
        self.lista.clear()
        claves = {texto.clave_orden(n) for n in marcadas}
        for c in lista:
            rotulo = f"{c.nombre}   ({c.usos})" if mostrar_usos else c.nombre
            item = QListWidgetItem(rotulo)
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, c.nombre)
            if self.casillas:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if texto.clave_orden(c.nombre) in claves
                                   else Qt.CheckState.Unchecked)
            self.lista.addItem(item)
        self._filtrar(self.filtro.text())

    def _filtrar(self, filtro: str) -> None:
        clave = texto.clave_orden(filtro.strip())
        for n in range(self.lista.count()):
            item = self.lista.item(n)
            self.lista.setRowHidden(n, bool(clave) and clave not in texto.clave_orden(item.data(Qt.ItemDataRole.UserRole + 1)))

    def marcadas(self) -> list[str]:
        return [self.lista.item(n).data(Qt.ItemDataRole.UserRole + 1) for n in range(self.lista.count())
                if self.lista.item(n).checkState() == Qt.CheckState.Checked]

    def actual(self) -> tuple[int, str] | None:
        item = self.lista.currentItem()
        return (item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)) if item else None


class DialogoElegirCategorias(QDialog):
    """Casillas con todas las categorías del catálogo; permite crear una nueva sin salir."""

    def __init__(self, con: sqlite3.Connection, marcadas: list[str], parent=None):
        super().__init__(parent)
        self.con = con
        self.setWindowTitle("Categorías")
        self.resize(tema.px(380), tema.px(520))
        self.lista = _ListaFiltrable(casillas=True)
        b_nueva = comun.boton("Nueva categoría…", "plus", "enlace")
        b_nueva.clicked.connect(self.nueva)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addWidget(QLabel("Marca una o varias:"))
        capa.addWidget(self.lista, 1)
        capa.addWidget(b_nueva, alignment=Qt.AlignmentFlag.AlignLeft)
        capa.addWidget(botones)
        self.lista.llenar(categorias.listar(con), set(marcadas))
        self.lista.filtro.setFocus()

    def nueva(self, nombre: str | None = None) -> bool:
        nombre = nombre or _pedir_nombre(self, "Nueva categoría", self.lista.filtro.text())
        if not nombre:
            return False
        try:
            categorias.crear(self.con, nombre)
        except ErrorCategoria as e:
            comun.error(self, str(e))
            return False
        marcadas = set(self.lista.marcadas()) | {" ".join(nombre.split())}
        self.lista.filtro.clear()
        self.lista.llenar(categorias.listar(self.con), marcadas)
        return True

    def elegidas(self) -> list[str]:
        return self.lista.marcadas()


class CampoCategorias(QWidget):
    """Campo de la ficha: las categorías elegidas y un botón para cambiarlas."""

    cambiado = Signal()

    def __init__(self, con: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.con = con
        self._valor: list[str] = []
        self.texto = QLabel(textFormat=Qt.TextFormat.PlainText, wordWrap=True)
        self.boton = comun.boton("Elegir…")
        self.boton.clicked.connect(self.elegir)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.texto, 1)
        capa.addWidget(self.boton)
        self.establecer([])

    def establecer(self, nombres: list[str]) -> None:
        self._valor = list(nombres)
        self.texto.setText(", ".join(self._valor) if self._valor else "(ninguna)")
        self.texto.setObjectName("" if self._valor else "suave")
        self.texto.style().unpolish(self.texto)
        self.texto.style().polish(self.texto)
        self.cambiado.emit()

    def valor(self) -> list[str]:
        return list(self._valor)

    def elegir(self) -> None:
        dialogo = DialogoElegirCategorias(self.con, self._valor, self)
        if dialogo.exec():
            self.establecer(dialogo.elegidas())


class EditorCategorias(QDialog):
    """Catálogo › Categorías: añadir, renombrar y borrar (con cuántos elementos usan cada una)."""

    def __init__(self, con: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.con = con
        self.hubo_cambios = False
        self.setWindowTitle("Categorías")
        self.resize(tema.px(440), tema.px(560))
        ayuda = QLabel("Las categorías sirven para clasificar lo que guardas (géneros, materias…) y para "
                       "buscar por ellas. Entre paréntesis, cuántos elementos tiene cada una.",
                       objectName="suave", wordWrap=True)
        self.lista = _ListaFiltrable(casillas=False)
        b_nueva = comun.boton("Añadir…", "plus")
        b_renombrar = comun.boton("Cambiar nombre…", "pencil")
        b_borrar = comun.boton("Borrar", "trash-2", "peligro")
        fila = QHBoxLayout()
        for b in (b_nueva, b_renombrar, b_borrar):
            fila.addWidget(b)
        fila.addStretch()
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addWidget(ayuda)
        capa.addWidget(self.lista, 1)
        capa.addLayout(fila)
        capa.addWidget(botones)
        b_nueva.clicked.connect(lambda: self.nueva())
        b_renombrar.clicked.connect(lambda: self.renombrar())
        b_borrar.clicked.connect(lambda: self.borrar())
        self.lista.lista.itemDoubleClicked.connect(lambda _i: self.renombrar())
        self.cargar()

    def cargar(self, seleccionar: str = "") -> None:
        self.lista.llenar(categorias.listar(self.con), mostrar_usos=True)
        for n in range(self.lista.lista.count()):
            item = self.lista.lista.item(n)
            if seleccionar and item.data(Qt.ItemDataRole.UserRole + 1) == seleccionar:
                self.lista.lista.setCurrentItem(item)

    def nueva(self, nombre: str | None = None) -> bool:
        nombre = nombre or _pedir_nombre(self, "Nueva categoría")
        if not nombre:
            return False
        try:
            categorias.crear(self.con, nombre)
        except ErrorCategoria as e:
            comun.error(self, str(e))
            return False
        self.hubo_cambios = True
        self.cargar(" ".join(nombre.split()))
        return True

    def renombrar(self, nombre: str | None = None) -> bool:
        actual = self.lista.actual()
        if actual is None:
            return False
        nombre = nombre or _pedir_nombre(self, "Cambiar nombre", actual[1])
        if not nombre or nombre == actual[1]:
            return False
        try:
            with comun.ocupado(self, "Actualizando…"):
                categorias.renombrar(self.con, actual[0], nombre)
        except ErrorCategoria as e:
            comun.error(self, str(e))
            return False
        self.hubo_cambios = True
        self.cargar(" ".join(nombre.split()))
        return True

    def borrar(self) -> bool:
        actual = self.lista.actual()
        if actual is None:
            return False
        usos = next((c.usos for c in categorias.listar(self.con) if c.id == actual[0]), 0)
        pregunta = f"¿Borrar la categoría «{actual[1]}»?"
        if usos:
            pregunta += f"\n\nSe quitará de {usos} elemento{'s' if usos != 1 else ''} (los elementos no se borran)."
        if not comun.confirmar(self, pregunta):
            return False
        with comun.ocupado(self, "Borrando…"):
            categorias.borrar(self.con, actual[0])
        self.hubo_cambios = True
        self.cargar()
        return True
