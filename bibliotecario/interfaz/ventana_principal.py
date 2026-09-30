"""Ventana principal: árbol de ubicaciones, buscador y lista de elementos."""

import sqlite3

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QMenu, QSplitter, QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import NOMBRE, VERSION
from ..datos import elementos, tipos, ubicaciones
from ..servicios import busqueda
from ..servicios.busqueda import Filtros
from . import comun
from .arbol_ubicaciones import ID_SIN_UBICACION, ID_TODAS, ArbolUbicaciones
from .editor_ubicaciones import EditorUbicaciones
from .ficha_elemento import FichaElemento
from .modelo_resultados import ModeloResultados, OrdenadorResultados
from .selector_ubicacion import elegir_ubicacion


class VentanaPrincipal(QMainWindow):
    def __init__(self, con: sqlite3.Connection):
        super().__init__()
        self.con = con
        self.setWindowTitle(f"{NOMBRE} {VERSION}")
        self.setWindowIcon(comun.icono_app())
        self.resize(1200, 720)

        # --- árbol
        self.arbol = ArbolUbicaciones(con, contar=True, especiales=True)
        self.filtro_arbol = QLineEdit(placeholderText="Filtrar ubicaciones…")
        izquierda = QWidget()
        capa_izq = QVBoxLayout(izquierda)
        capa_izq.setContentsMargins(0, 0, 0, 0)
        capa_izq.addWidget(self.filtro_arbol)
        capa_izq.addWidget(self.arbol)

        # --- tabla
        self.modelo = ModeloResultados(self)
        self.ordenador = OrdenadorResultados(self)
        self.ordenador.setSourceModel(self.modelo)
        self.tabla = QTableView()
        self.tabla.setModel(self.ordenador)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(-1, Qt.SortOrder.AscendingOrder)  # orden de la búsqueda (relevancia)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setWordWrap(False)
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        cabecera.setStretchLastSection(True)
        for columna, ancho in enumerate([130, 330, 200, 60, 300, 90]):
            self.tabla.setColumnWidth(columna, ancho)
        self.ruta_actual = QLabel(objectName="titulo_seccion")
        derecha = QWidget()
        capa_der = QVBoxLayout(derecha)
        capa_der.setContentsMargins(0, 0, 0, 0)
        self.capa_derecha = capa_der
        capa_der.addWidget(self.ruta_actual)
        capa_der.addWidget(self.tabla)

        divisor = QSplitter()
        divisor.addWidget(izquierda)
        divisor.addWidget(derecha)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([300, 900])
        self.setCentralWidget(divisor)

        self._crear_acciones()
        self._crear_barra()
        self._crear_menus()

        self.temporizador = QTimer(self, singleShot=True, interval=250)
        self.temporizador.timeout.connect(self.refrescar_resultados)
        self.busqueda.textChanged.connect(lambda _t: self.temporizador.start())
        self.filtro_arbol.textChanged.connect(self.arbol.filtrar)
        self.arbol.ubicacion_cambiada.connect(lambda _id: self.refrescar_resultados())
        self.tabla.doubleClicked.connect(lambda _i: self.editar())
        self.tabla.customContextMenuRequested.connect(self._menu_contextual)
        self.tabla.selectionModel().selectionChanged.connect(lambda *_: self._actualizar_acciones())

        self.refrescar_resultados()

    # ------------------------------------------------------------ construcción

    def _crear_acciones(self):
        self.acc_nuevo = QAction("➕ Nuevo", self, shortcut=QKeySequence.StandardKey.New)
        self.acc_nuevo.triggered.connect(lambda: self.nuevo())
        self.acc_editar = QAction("✏️ Editar", self, shortcut=QKeySequence("F2"))
        self.acc_editar.triggered.connect(self.editar)
        self.acc_mover = QAction("📦 Mover a…", self, shortcut=QKeySequence("Ctrl+M"))
        self.acc_mover.triggered.connect(self.mover)
        self.acc_borrar = QAction("🗑 Borrar", self, shortcut=QKeySequence.StandardKey.Delete)
        self.acc_borrar.triggered.connect(self.borrar)
        self.acc_ubicaciones = QAction("🏠 Ubicaciones de la casa…", self)
        self.acc_ubicaciones.triggered.connect(self.editar_ubicaciones)
        self.acc_buscar = QAction("Buscar", self, shortcut=QKeySequence.StandardKey.Find)
        self.acc_buscar.triggered.connect(lambda: (self.busqueda.setFocus(), self.busqueda.selectAll()))
        self.addAction(self.acc_buscar)

    def _crear_barra(self):
        barra = self.addToolBar("Principal")
        barra.setMovable(False)
        boton_nuevo = QToolButton()
        boton_nuevo.setDefaultAction(self.acc_nuevo)
        boton_nuevo.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.menu_nuevo = QMenu(self)
        boton_nuevo.setMenu(self.menu_nuevo)
        self._llenar_menu_nuevo()
        barra.addWidget(boton_nuevo)
        barra.addAction(self.acc_editar)
        barra.addAction(self.acc_mover)
        barra.addAction(self.acc_borrar)
        barra.addSeparator()
        self.busqueda = QLineEdit(objectName="busqueda", clearButtonEnabled=True)
        self.busqueda.setPlaceholderText('🔍 Buscar… (sin acentos, "frase exacta", -excluir)')
        barra.addWidget(self.busqueda)
        barra.addSeparator()
        barra.addWidget(QLabel(" Ir a código: "))
        self.ir_codigo = QLineEdit(placeholderText="p. ej. PB-SAL-EA-B3", clearButtonEnabled=True)
        self.ir_codigo.setMaximumWidth(170)
        self.ir_codigo.returnPressed.connect(self.ir_a_codigo)
        barra.addWidget(self.ir_codigo)
        barra.addSeparator()
        barra.addAction(self.acc_ubicaciones)

    def _llenar_menu_nuevo(self):
        self.menu_nuevo.clear()
        for t in tipos.listar(self.con, con_campos=False):
            accion = self.menu_nuevo.addAction(f"{t.icono}  {t.nombre}")
            accion.triggered.connect(lambda _c=False, tipo_id=t.id: self.nuevo(tipo_id))

    def _crear_menus(self):
        archivo = self.menuBar().addMenu("&Archivo")
        salir = archivo.addAction("Salir")
        salir.triggered.connect(self.close)
        self.menu_archivo = archivo

        elemento = self.menuBar().addMenu("&Elemento")
        for accion in (self.acc_nuevo, self.acc_editar, self.acc_mover, self.acc_borrar):
            elemento.addAction(accion)

        self.menu_catalogo = self.menuBar().addMenu("&Catálogo")
        self.menu_catalogo.addAction(self.acc_ubicaciones)

        self.menu_ayuda = self.menuBar().addMenu("Ay&uda")
        acerca = self.menu_ayuda.addAction("Acerca de…")
        acerca.triggered.connect(lambda: comun.aviso(
            self, f"{NOMBRE} {VERSION}\n\nRegistra dónde guardas cada libro, disco, álbum o carpeta.\n"
                  "Los datos están en la carpeta «datos» junto al programa."))

    # ------------------------------------------------------------ datos

    def filtros_actuales(self) -> Filtros:
        f = Filtros(texto=self.busqueda.text())
        ubic = self.arbol.id_actual()
        if ubic == ID_SIN_UBICACION:
            f.sin_ubicacion = True
        elif ubic not in (None, ID_TODAS):
            f.ubicacion_id = ubic
        return f

    def refrescar_resultados(self, seleccionar: int | None = None):
        filtros = self.filtros_actuales()
        resultados = busqueda.buscar(self.con, filtros)
        self.modelo.establecer(resultados)
        if filtros.sin_ubicacion:
            titulo = "Sin ubicación"
        elif filtros.ubicacion_id:
            titulo = ubicaciones.ruta_texto(self.con, filtros.ubicacion_id, incluir_raiz=True)
        else:
            titulo = "Todas las ubicaciones"
        self.ruta_actual.setText(titulo)
        total = self.con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
        self.statusBar().showMessage(f"Mostrando {len(resultados)} de {total} elementos")
        if seleccionar is not None:
            self.seleccionar_elemento(seleccionar)
        self._actualizar_acciones()

    def refrescar_todo(self, seleccionar: int | None = None):
        self.arbol.cargar()
        self.arbol.filtrar(self.filtro_arbol.text())
        self._llenar_menu_nuevo()
        self.refrescar_resultados(seleccionar)

    def seleccionar_elemento(self, elemento_id: int) -> None:
        for fila in range(self.modelo.rowCount()):
            if self.modelo.resultado(fila).id == elemento_id:
                indice = self.ordenador.mapFromSource(self.modelo.index(fila, 1))
                self.tabla.selectRow(indice.row())
                self.tabla.scrollTo(indice)
                return

    def ids_seleccionados(self) -> list[int]:
        filas = {self.ordenador.mapToSource(i).row() for i in self.tabla.selectionModel().selectedRows()}
        return [self.modelo.resultado(f).id for f in sorted(filas)]

    def _actualizar_acciones(self):
        n = len(self.ids_seleccionados())
        self.acc_editar.setEnabled(n == 1)
        self.acc_mover.setEnabled(n >= 1)
        self.acc_borrar.setEnabled(n >= 1)

    # ------------------------------------------------------------ acciones

    def ubicacion_para_nuevo(self) -> int | None:
        ubic = self.arbol.id_actual()
        return ubic if ubic not in (None, ID_TODAS, ID_SIN_UBICACION) else None

    def nuevo(self, tipo_id: int | None = None):
        ficha = FichaElemento(self.con, tipo_id=tipo_id, ubicacion_id=self.ubicacion_para_nuevo(), parent=self)
        guardados: list[int] = []
        ficha.guardado.connect(guardados.append)
        ficha.exec()
        if guardados:
            self.refrescar_todo(guardados[-1])

    def editar(self):
        ids = self.ids_seleccionados()
        if len(ids) != 1:
            return
        ficha = FichaElemento(self.con, elemento_id=ids[0], parent=self)
        if ficha.exec():
            self.refrescar_todo(ids[0])

    def mover(self):
        ids = self.ids_seleccionados()
        if not ids:
            return
        destino = elegir_ubicacion(self.con, self, titulo=f"Mover {len(ids)} elemento(s) a…")
        if destino is not None:
            elementos.mover(self.con, ids, destino)
            self.refrescar_todo()

    def borrar(self):
        ids = self.ids_seleccionados()
        if not ids:
            return
        if len(ids) == 1:
            pregunta = f"¿Borrar «{elementos.obtener(self.con, ids[0]).titulo}»?"
        else:
            pregunta = f"¿Borrar los {len(ids)} elementos seleccionados?"
        if comun.confirmar(self, pregunta + "\n\nEsta acción no se puede deshacer."):
            elementos.borrar(self.con, ids)
            self.refrescar_todo()

    def editar_ubicaciones(self):
        editor = EditorUbicaciones(self.con, self.ubicacion_para_nuevo(), self)
        editor.exec()
        if editor.hubo_cambios:
            self.refrescar_todo()

    def ir_a_codigo(self):
        codigo = self.ir_codigo.text().strip()
        if not codigo:
            return
        u = ubicaciones.buscar_por_codigo(self.con, codigo)
        if u is None:
            comun.aviso(self, f"No hay ninguna ubicación con el código «{codigo}».")
            return
        self.filtro_arbol.clear()
        self.busqueda.clear()
        self.arbol.seleccionar(u.id)
        self.ir_codigo.clear()

    def _menu_contextual(self, posicion):
        if not self.ids_seleccionados():
            return
        menu = QMenu(self)
        for accion in (self.acc_editar, self.acc_mover, self.acc_borrar):
            menu.addAction(accion)
        menu.exec(self.tabla.viewport().mapToGlobal(posicion))
