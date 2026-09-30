"""Editor del catálogo de la casa: plantas, habitaciones, muebles, baldas, cajas..."""

import sqlite3

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from ..datos import ubicaciones
from ..datos.ubicaciones import ErrorUbicacion
from . import comun
from .arbol_ubicaciones import ArbolUbicaciones
from .selector_ubicacion import elegir_ubicacion


def _llenar_tipos(combo: QComboBox, con: sqlite3.Connection, seleccionado: int | None) -> None:
    combo.clear()
    for t in ubicaciones.listar_tipos(con):
        combo.addItem(t["nombre"], t["id"])
    if seleccionado is not None:
        combo.setCurrentIndex(max(0, combo.findData(seleccionado)))


def tipo_sugerido(con: sqlite3.Connection, padre_id: int | None) -> int | None:
    """Tipo probable para un hijo: el siguiente al del padre (Planta -> Habitación -> Armario...)."""
    lista = ubicaciones.listar_tipos(con)
    if not lista:
        return None
    padre = ubicaciones.obtener(con, padre_id) if padre_id else None
    if padre is None:
        return lista[0]["id"]
    ids = [t["id"] for t in lista]
    posicion = ids.index(padre.tipo_id) if padre.tipo_id in ids else -1
    return ids[min(posicion + 1, len(ids) - 1)]


class DialogoNuevaUbicacion(QDialog):
    def __init__(self, con: sqlite3.Connection, padre_id: int | None, parent=None):
        super().__init__(parent)
        self.con, self.padre_id = con, padre_id
        self.setWindowTitle("Nueva ubicación")
        self.nombre = QLineEdit()
        self.tipo = QComboBox()
        _llenar_tipos(self.tipo, con, tipo_sugerido(con, padre_id))
        self.codigo = QLineEdit()
        self.codigo.setToolTip("Déjalo vacío para usar el código sugerido.")
        self.descripcion = QLineEdit()
        dentro = ubicaciones.ruta_texto(con, padre_id, incluir_raiz=True) if padre_id else "(nivel superior)"
        formulario = QFormLayout()
        formulario.addRow("Dentro de:", QLabel(dentro, objectName="ruta"))
        formulario.addRow("Nombre:", self.nombre)
        formulario.addRow("Tipo:", self.tipo)
        formulario.addRow("Código:", self.codigo)
        formulario.addRow("Descripción:", self.descripcion)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        capa = QVBoxLayout(self)
        capa.addLayout(formulario)
        capa.addWidget(botones)
        self.nombre.textChanged.connect(self._sugerir)
        self.nuevo_id: int | None = None

    def _sugerir(self, nombre: str):
        self.codigo.setPlaceholderText(ubicaciones.sugerir_codigo(self.con, self.padre_id, nombre) if nombre.strip() else "")

    def _aceptar(self):
        try:
            self.nuevo_id = ubicaciones.crear(self.con, self.padre_id, self.tipo.currentData(), self.nombre.text(),
                                              self.codigo.text(), self.descripcion.text())
        except ErrorUbicacion as e:
            comun.error(self, str(e))
            return
        self.accept()


class DialogoTiposUbicacion(QDialog):
    """Alta, cambio de nombre y borrado de los tipos de ubicación."""

    def __init__(self, con: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.con = con
        self.setWindowTitle("Tipos de ubicación")
        self.resize(360, 400)
        self.lista = QListWidget()
        nuevo, renombrar, borrar = QPushButton("Añadir…"), QPushButton("Cambiar…"), QPushButton("Borrar")
        cerrar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        cerrar.rejected.connect(self.accept)
        botones = QVBoxLayout()
        for b in (nuevo, renombrar, borrar):
            botones.addWidget(b)
        botones.addStretch()
        fila = QHBoxLayout()
        fila.addWidget(self.lista)
        fila.addLayout(botones)
        capa = QVBoxLayout(self)
        capa.addLayout(fila)
        capa.addWidget(cerrar)
        nuevo.clicked.connect(lambda: self._editar(None))
        renombrar.clicked.connect(self._cambiar)
        self.lista.itemDoubleClicked.connect(self._cambiar)
        borrar.clicked.connect(self._borrar)
        self._cargar()

    def _cargar(self):
        self.lista.clear()
        for t in ubicaciones.listar_tipos(self.con):
            item = QListWidgetItem(f"{t['nombre']}   [{t['prefijo']}]   · {t['usos']} en uso")
            item.setData(Qt.ItemDataRole.UserRole, dict(t))
            self.lista.addItem(item)

    def _actual(self):
        item = self.lista.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _cambiar(self, *_):
        tipo = self._actual()
        if tipo is not None:
            self._editar(tipo)

    def _editar(self, tipo: dict | None):
        """Con ``tipo`` None crea uno nuevo; si no, modifica el indicado."""
        nombre, ok = QInputDialog.getText(self, "Tipo de ubicación", "Nombre:", text=tipo["nombre"] if tipo else "")
        if not ok or not nombre.strip():
            return
        prefijo, ok = QInputDialog.getText(self, "Tipo de ubicación", "Prefijo para códigos (opcional):",
                                           text=tipo["prefijo"] if tipo else "")
        if not ok:
            return
        try:
            ubicaciones.guardar_tipo(self.con, nombre, prefijo, tipo["id"] if tipo else None)
        except ErrorUbicacion as e:
            comun.error(self, str(e))
        self._cargar()

    def _borrar(self):
        tipo = self._actual()
        if tipo and comun.confirmar(self, f"¿Borrar el tipo «{tipo['nombre']}»?"):
            try:
                ubicaciones.borrar_tipo(self.con, tipo["id"])
            except ErrorUbicacion as e:
                comun.error(self, str(e))
            self._cargar()


class EditorUbicaciones(QDialog):
    def __init__(self, con: sqlite3.Connection, seleccionar: int | None = None, parent=None):
        super().__init__(parent)
        self.con = con
        self.setWindowTitle("Catálogo de ubicaciones de la casa")
        self.resize(900, 600)
        self.hubo_cambios = False

        # Árbol
        self.filtro = QLineEdit(placeholderText="Filtrar…")
        self.arbol = ArbolUbicaciones(con, contar=True, al_mover=self._mover)
        ayuda = QLabel("Arrastra para reorganizar. Todo lo que contiene una ubicación viaja con ella.")
        ayuda.setWordWrap(True)
        izquierda = QVBoxLayout()
        izquierda.addWidget(self.filtro)
        izquierda.addWidget(self.arbol)
        izquierda.addWidget(ayuda)

        # Botones de acciones
        self.b_dentro = QPushButton("➕ Añadir dentro…")
        self.b_nivel = QPushButton("➕ Añadir al mismo nivel…")
        self.b_subir = QPushButton("▲ Subir")
        self.b_bajar = QPushButton("▼ Bajar")
        self.b_mover = QPushButton("Mover a…")
        self.b_borrar = QPushButton("🗑 Borrar…")
        self.b_tipos = QPushButton("Tipos de ubicación…")
        acciones = QHBoxLayout()
        for b in (self.b_dentro, self.b_nivel, self.b_subir, self.b_bajar, self.b_mover, self.b_borrar):
            acciones.addWidget(b)
        acciones.addStretch()
        acciones.addWidget(self.b_tipos)

        # Ficha de la ubicación seleccionada
        self.nombre = QLineEdit()
        self.tipo = QComboBox()
        self.codigo = QLineEdit()
        self.descripcion = QPlainTextEdit()
        self.descripcion.setMaximumHeight(90)
        self.ruta = QLabel(objectName="ruta", wordWrap=True)
        self.contenido = QLabel()
        self.b_guardar = QPushButton("Guardar cambios")
        self.b_codigo = QPushButton("Sugerir código")
        ficha = QFormLayout()
        ficha.addRow("Ruta:", self.ruta)
        ficha.addRow("Nombre:", self.nombre)
        ficha.addRow("Tipo:", self.tipo)
        fila_codigo = QHBoxLayout()
        fila_codigo.addWidget(self.codigo)
        fila_codigo.addWidget(self.b_codigo)
        ficha.addRow("Código:", fila_codigo)
        ficha.addRow("Descripción:", self.descripcion)
        ficha.addRow("Contiene:", self.contenido)
        ficha.addRow("", self.b_guardar)
        self.grupo = QGroupBox("Ubicación seleccionada")
        self.grupo.setLayout(ficha)

        cuerpo = QHBoxLayout()
        cuerpo.addLayout(izquierda, 1)
        derecha = QVBoxLayout()
        derecha.addWidget(self.grupo)
        derecha.addStretch()
        panel = QWidget()
        panel.setLayout(derecha)
        cuerpo.addWidget(panel, 1)

        cerrar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        cerrar.rejected.connect(self.accept)
        capa = QVBoxLayout(self)
        capa.addLayout(acciones)
        capa.addLayout(cuerpo)
        capa.addWidget(cerrar)

        self.filtro.textChanged.connect(self.arbol.filtrar)
        self.arbol.ubicacion_cambiada.connect(self._mostrar)
        self.b_dentro.clicked.connect(lambda: self._nueva(dentro=True))
        self.b_nivel.clicked.connect(lambda: self._nueva(dentro=False))
        self.b_subir.clicked.connect(lambda: self._desplazar(-1))
        self.b_bajar.clicked.connect(lambda: self._desplazar(+1))
        self.b_mover.clicked.connect(self._mover_a)
        self.b_borrar.clicked.connect(self._borrar)
        self.b_tipos.clicked.connect(self._tipos)
        self.b_guardar.clicked.connect(self._guardar)
        self.b_codigo.clicked.connect(self._sugerir_codigo)

        self.arbol.seleccionar(seleccionar) if seleccionar else self.arbol.setCurrentItem(self.arbol.topLevelItem(0))
        self._mostrar(self.arbol.id_actual())

    # ------------------------------------------------------------ ficha

    def _mostrar(self, ubicacion_id):
        u = ubicaciones.obtener(self.con, ubicacion_id) if ubicacion_id else None
        for w in (self.grupo, self.b_nivel, self.b_subir, self.b_bajar, self.b_mover, self.b_borrar, self.b_dentro):
            w.setEnabled(u is not None)
        if u is None:
            return
        _llenar_tipos(self.tipo, self.con, u.tipo_id)
        self.nombre.setText(u.nombre)
        self.codigo.setText(u.codigo)
        self.descripcion.setPlainText(u.descripcion)
        self.ruta.setText(ubicaciones.ruta_texto(self.con, u.id, incluir_raiz=True))
        total = ubicaciones.contar_elementos(self.con).get(u.id, 0)
        subs = len(ubicaciones.descendientes(self.con, u.id)) - 1
        self.contenido.setText(f"{total} elementos · {subs} sububicaciones")

    def _guardar(self):
        id_ = self.arbol.id_actual()
        try:
            ubicaciones.actualizar(self.con, id_, self.nombre.text(), self.tipo.currentData(),
                                   self.codigo.text(), self.descripcion.toPlainText())
        except ErrorUbicacion as e:
            comun.error(self, str(e))
            return
        self._recargar(id_)

    def _sugerir_codigo(self):
        u = ubicaciones.obtener(self.con, self.arbol.id_actual())
        if u:
            self.codigo.setText(ubicaciones.sugerir_codigo(self.con, u.padre_id, self.nombre.text() or u.nombre, u.id))

    # ------------------------------------------------------------ acciones

    def _recargar(self, seleccionar=None):
        self.hubo_cambios = True
        self.arbol.cargar(seleccionar)
        self.arbol.filtrar(self.filtro.text())
        self._mostrar(self.arbol.id_actual())

    def _nueva(self, dentro: bool):
        actual = ubicaciones.obtener(self.con, self.arbol.id_actual())
        padre_id = actual.id if (dentro and actual) else (actual.padre_id if actual else None)
        dialogo = DialogoNuevaUbicacion(self.con, padre_id, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._recargar(dialogo.nuevo_id)

    def _mover(self, ubicacion_id, nuevo_padre_id, indice):
        try:
            ubicaciones.mover(self.con, ubicacion_id, nuevo_padre_id, indice)
        except ErrorUbicacion as e:
            comun.error(self, str(e))
        self._recargar(ubicacion_id)

    def _mover_a(self):
        u = ubicaciones.obtener(self.con, self.arbol.id_actual())
        if u is None:
            return
        destino = elegir_ubicacion(self.con, self, titulo=f"Mover «{u.nombre}» dentro de…",
                                   excluir=set(ubicaciones.descendientes(self.con, u.id)))
        if destino is not None:
            self._mover(u.id, destino, None)

    def _desplazar(self, paso: int):
        u = ubicaciones.obtener(self.con, self.arbol.id_actual())
        if u is None:
            return
        hermanos = [h.id for h in ubicaciones.hijos(self.con, u.padre_id)]
        nuevo = hermanos.index(u.id) + paso
        if 0 <= nuevo < len(hermanos):
            self._mover(u.id, u.padre_id, nuevo)

    def _borrar(self):
        u = ubicaciones.obtener(self.con, self.arbol.id_actual())
        if u is None:
            return
        ids = ubicaciones.descendientes(self.con, u.id)
        total = ubicaciones.contar_elementos(self.con).get(u.id, 0)
        destino = None
        if total:
            comun.aviso(self, f"«{u.nombre}» contiene {total} elementos.\n"
                              "Elige a continuación a qué ubicación deben moverse.")
            destino = elegir_ubicacion(self.con, self, titulo=f"Mover los {total} elementos a…", excluir=set(ids))
            if destino is None:
                return
        extra = f" y sus {len(ids) - 1} sububicaciones" if len(ids) > 1 else ""
        if not comun.confirmar(self, f"¿Borrar «{u.nombre}»{extra}?"):
            return
        try:
            ubicaciones.borrar(self.con, u.id, destino)
        except ErrorUbicacion as e:
            comun.error(self, str(e))
            return
        self._recargar(u.padre_id)

    def _tipos(self):
        DialogoTiposUbicacion(self.con, self).exec()
        self._recargar(self.arbol.id_actual())
