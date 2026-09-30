"""Editor de tipos de elemento: crear tipos nuevos y añadir, ordenar u ocultar campos."""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ..datos import tipos
from ..datos.tipos import Campo, ErrorTipo, TipoElemento
from . import comun, tema

# Iconos que se pueden elegir para un tipo de elemento (conjunto Lucide incluido en recursos/iconos).
ICONOS_TIPO = [
    "book", "book-open", "book-marked", "library", "newspaper", "disc-3", "music", "clapperboard",
    "gamepad-2", "images", "image", "projector", "folder", "file-box", "map", "puzzle", "dices", "palette",
    "stamp", "coins", "gem", "trophy", "wine", "shirt", "watch", "glasses", "briefcase", "graduation-cap",
    "star", "heart", "key", "lamp", "sofa", "package", "box", "archive", "tag", "sticky-note",
]

COL_NOMBRE, COL_TIPO, COL_OPCIONES, COL_OCULTO = range(4)


class EditorTipos(QDialog):
    def __init__(self, con: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.con = con
        self.hubo_cambios = False
        self.actual: TipoElemento | None = None
        self.setWindowTitle("Tipos de elemento y sus campos")
        self.resize(tema.px(980), tema.px(600))

        # --- lista de tipos
        self.lista = QListWidget()
        self.b_nuevo = comun.boton("Nuevo tipo", "plus")
        self.b_borrar = comun.boton("Borrar tipo", "trash-2", "peligro")
        izquierda = QVBoxLayout()
        izquierda.addWidget(self.lista)
        fila = QHBoxLayout()
        fila.addWidget(self.b_nuevo)
        fila.addWidget(self.b_borrar)
        izquierda.addLayout(fila)

        # --- datos del tipo
        self.nombre = QLineEdit()
        self.icono = QComboBox()
        self.icono.setToolTip("Icono con el que se mostrará este tipo")
        for nombre in ICONOS_TIPO:
            self.icono.addItem(tema.icono(nombre, "primario"), "", nombre)
        self.icono.setMaxVisibleItems(12)
        self.verbo = QComboBox(editable=True)
        self.verbo.addItems(["Leído", "Visto", "Escuchado", "Jugado", "Tocado", "Revisado"])
        self.personal = QCheckBox("Destacar periodo, personas y lugar (álbumes, carpetas, documentos…)")
        self.roles = QLineEdit(placeholderText="Autor; Traductor; Ilustrador")
        datos = QFormLayout()
        fila = QHBoxLayout()
        fila.addWidget(self.nombre, 1)
        fila.addWidget(QLabel("  Icono"))
        fila.addWidget(self.icono)
        datos.addRow("Nombre:", fila)
        datos.addRow("Marca de consumo:", self.verbo)
        datos.addRow("Roles de persona:", self.roles)
        datos.addRow("", self.personal)

        # --- campos
        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Campo", "Tipo de dato", "Opciones (separadas por ;)", "Oculto"])
        self.tabla.horizontalHeader().setSectionResizeMode(COL_OPCIONES, QHeaderView.ResizeMode.Stretch)
        self.tabla.setColumnWidth(COL_NOMBRE, 200)
        self.tabla.setColumnWidth(COL_TIPO, 140)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.b_campo = comun.boton("Añadir campo", "plus")
        self.b_quitar = QPushButton("Quitar campo")
        self.b_subir = comun.boton("", "arrow-up", tooltip="Subir el campo")
        self.b_bajar = comun.boton("", "arrow-down", tooltip="Bajar el campo")
        botones_campos = QHBoxLayout()
        for b in (self.b_campo, self.b_quitar, self.b_subir, self.b_bajar):
            botones_campos.addWidget(b)
        botones_campos.addStretch()
        nota = QLabel("Los campos quitados de un tipo con datos se ocultan: los valores guardados no se pierden.")
        nota.setWordWrap(True)
        campos = QVBoxLayout()
        campos.addWidget(self.tabla)
        campos.addLayout(botones_campos)
        campos.addWidget(nota)
        grupo_campos = QGroupBox("Campos propios")
        grupo_campos.setLayout(campos)

        self.b_guardar = QPushButton("Guardar tipo")
        derecha = QVBoxLayout()
        derecha.addLayout(datos)
        derecha.addWidget(grupo_campos, 1)
        derecha.addWidget(self.b_guardar, alignment=Qt.AlignmentFlag.AlignRight)

        cuerpo = QHBoxLayout()
        cuerpo.addLayout(izquierda, 1)
        cuerpo.addLayout(derecha, 3)
        cerrar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        cerrar.rejected.connect(self.accept)
        capa = QVBoxLayout(self)
        capa.addLayout(cuerpo)
        capa.addWidget(cerrar)

        self.lista.currentItemChanged.connect(lambda item, _a: self._mostrar(item.data(Qt.ItemDataRole.UserRole) if item else None))
        self.b_nuevo.clicked.connect(self.nuevo_tipo)
        self.b_borrar.clicked.connect(self.borrar_tipo)
        self.b_campo.clicked.connect(lambda: self.anadir_campo(Campo(None, "", "", "texto"), editar=True))
        self.b_quitar.clicked.connect(self.quitar_campo)
        self.b_subir.clicked.connect(lambda: self.desplazar_campo(-1))
        self.b_bajar.clicked.connect(lambda: self.desplazar_campo(+1))
        self.b_guardar.clicked.connect(self.guardar)
        self._cargar_lista()

    # ------------------------------------------------------------ lista

    def _cargar_lista(self, seleccionar: int | None = None) -> None:
        self.lista.clear()
        for t in tipos.listar(self.con, con_campos=False):
            item = QListWidgetItem(tema.icono(t.icono or "package", "primario"),
                                   t.nombre + ("" if t.predefinido else "   (propio)"))
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.lista.addItem(item)
            if t.id == seleccionar:
                self.lista.setCurrentItem(item)
        if self.lista.currentItem() is None and self.lista.count():
            self.lista.setCurrentRow(0)

    def _mostrar(self, tipo_id: int | None) -> None:
        self.actual = tipos.obtener(self.con, tipo_id) if tipo_id else None
        t = self.actual or TipoElemento(id=None, nombre="")
        self.nombre.setText(t.nombre)
        if self.icono.findData(t.icono) < 0 and t.icono:
            self.icono.addItem(tema.icono(t.icono, "primario"), "", t.icono)  # icono antiguo o propio
        self.icono.setCurrentIndex(max(0, self.icono.findData(t.icono or "package")))
        self.verbo.setCurrentText(t.verbo_consumo)
        self.personal.setChecked(t.personal)
        self.roles.setText("; ".join(t.roles))
        self.tabla.setRowCount(0)
        for c in t.campos:
            self.anadir_campo(c)
        self.b_borrar.setEnabled(bool(self.actual) and not self.actual.predefinido)

    # ------------------------------------------------------------ campos

    def anadir_campo(self, campo: Campo, editar: bool = False) -> None:
        fila = self.tabla.rowCount()
        self.tabla.insertRow(fila)
        nombre = QTableWidgetItem(campo.etiqueta)
        nombre.setData(Qt.ItemDataRole.UserRole, campo.id)
        self.tabla.setItem(fila, COL_NOMBRE, nombre)
        combo = QComboBox()
        for clave, texto in tipos.TIPOS_DATO.items():
            combo.addItem(texto, clave)
        combo.setCurrentIndex(max(0, combo.findData(campo.tipo_dato)))
        self.tabla.setCellWidget(fila, COL_TIPO, combo)
        self.tabla.setItem(fila, COL_OPCIONES, QTableWidgetItem("; ".join(campo.opciones)))
        oculto = QTableWidgetItem()
        oculto.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        oculto.setCheckState(Qt.CheckState.Checked if campo.oculto else Qt.CheckState.Unchecked)
        self.tabla.setItem(fila, COL_OCULTO, oculto)
        if editar:
            self.tabla.setCurrentCell(fila, COL_NOMBRE)
            self.tabla.editItem(nombre)

    def _leer_fila(self, fila: int) -> Campo:
        nombre = self.tabla.item(fila, COL_NOMBRE)
        opciones = self.tabla.item(fila, COL_OPCIONES)
        return Campo(
            id=nombre.data(Qt.ItemDataRole.UserRole),
            clave="",
            etiqueta=nombre.text(),
            tipo_dato=self.tabla.cellWidget(fila, COL_TIPO).currentData(),
            opciones=[o.strip() for o in (opciones.text() if opciones else "").split(";") if o.strip()],
            oculto=self.tabla.item(fila, COL_OCULTO).checkState() == Qt.CheckState.Checked,
        )

    def campos_en_pantalla(self) -> list[Campo]:
        return [self._leer_fila(f) for f in range(self.tabla.rowCount())]

    def quitar_campo(self) -> None:
        fila = self.tabla.currentRow()
        if fila >= 0:
            self.tabla.removeRow(fila)

    def desplazar_campo(self, paso: int) -> None:
        fila = self.tabla.currentRow()
        destino = fila + paso
        if fila < 0 or not 0 <= destino < self.tabla.rowCount():
            return
        campos = self.campos_en_pantalla()
        campos[fila], campos[destino] = campos[destino], campos[fila]
        self.tabla.setRowCount(0)
        for c in campos:
            self.anadir_campo(c)
        self.tabla.setCurrentCell(destino, COL_NOMBRE)

    # ------------------------------------------------------------ tipos

    def nuevo_tipo(self) -> None:
        self.lista.clearSelection()
        self.lista.setCurrentItem(None)
        self._mostrar(None)
        self.nombre.setFocus()

    def guardar(self) -> bool:
        t = TipoElemento(
            id=self.actual.id if self.actual else None,
            nombre=self.nombre.text(),
            icono=self.icono.currentData() or "package",
            verbo_consumo=self.verbo.currentText(),
            personal=self.personal.isChecked(),
            roles=[r.strip() for r in self.roles.text().split(";") if r.strip()],
            campos=self.campos_en_pantalla(),
        )
        try:
            tipo_id = tipos.guardar(self.con, t)
        except ErrorTipo as e:
            comun.error(self, str(e))
            return False
        self.hubo_cambios = True
        self._cargar_lista(tipo_id)
        self._mostrar(tipo_id)
        return True

    def borrar_tipo(self) -> None:
        if self.actual and comun.confirmar(self, f"¿Borrar el tipo «{self.actual.nombre}»?"):
            try:
                tipos.borrar(self.con, self.actual.id)
            except ErrorTipo as e:
                comun.error(self, str(e))
                return
            self.hubo_cambios = True
            self._cargar_lista()
