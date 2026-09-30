"""Ventana principal: árbol de ubicaciones, buscador y lista de elementos."""

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
                               QFileDialog, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
                               QPushButton, QSplitter,
                               QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import NOMBRE, VERSION, rutas
from ..datos import elementos, tipos, ubicaciones
from ..servicios import busqueda, copias, informes
from ..servicios.busqueda import Filtros
from . import comun
from .comun import reiniciar
from .dialogo_copias import DialogoRestaurar
from .dialogo_etiquetas import DialogoEtiquetas
from .alta_masiva import AltaMasiva
from .editor_tipos import EditorTipos
from .arbol_ubicaciones import ID_SIN_UBICACION, ID_TODAS, ArbolUbicaciones
from .editor_ubicaciones import EditorUbicaciones
from .ficha_elemento import FichaElemento
from .modelo_resultados import ModeloResultados, OrdenadorResultados
from .preferencias import Preferencias
from .selector_ubicacion import elegir_ubicacion


def conexion_abierta(con: sqlite3.Connection) -> bool:
    try:
        con.execute("SELECT 1")
        return True
    except sqlite3.ProgrammingError:
        return False


class VentanaPrincipal(QMainWindow):
    def __init__(self, con: sqlite3.Connection):
        super().__init__()
        self.con = con
        self.restaurado = False
        self.setWindowTitle(f"{NOMBRE} {VERSION}")
        self.setWindowIcon(comun.icono_app())
        self.resize(1200, 720)

        # --- árbol (admite soltar elementos arrastrados desde la tabla para moverlos)
        self.arbol = ArbolUbicaciones(con, contar=True, especiales=True, al_soltar_elementos=self.mover_a)
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
        self.tabla.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # en rutas largas se ve el final
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.setDragEnabled(True)
        self.tabla.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
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
        capa_der.addWidget(self._crear_filtros())
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

    def _crear_filtros(self) -> QWidget:
        self.f_tipo = QComboBox()
        self.f_etiqueta = QComboBox()
        self.f_estado = QComboBox()
        self.f_idioma = QComboBox()
        self.f_prestados = QCheckBox("Prestados")
        self.f_pendientes = QCheckBox("Pendientes (sin leer / ver…)")
        self.f_limpiar = QPushButton("Quitar filtros")
        self._llenar_filtros()
        panel = QWidget()
        capa = QHBoxLayout(panel)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(QLabel("Filtros:"))
        for w in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma, self.f_prestados,
                  self.f_pendientes, self.f_limpiar):
            capa.addWidget(w)
        capa.addStretch()
        for combo in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma):
            combo.currentIndexChanged.connect(lambda _i: self.refrescar_resultados())
        for casilla in (self.f_prestados, self.f_pendientes):
            casilla.toggled.connect(lambda _v: self.refrescar_resultados())
        self.f_limpiar.clicked.connect(self.quitar_filtros)
        return panel

    def _llenar_filtros(self):
        """Rellena los desplegables de filtro conservando lo que estuviera elegido."""
        def llenar(combo: QComboBox, primero: str, opciones: list[tuple[str, object]]):
            actual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(primero, None)
            for texto_, dato in opciones:
                combo.addItem(texto_, dato)
            indice = combo.findData(actual)
            combo.setCurrentIndex(indice if indice >= 0 else 0)
            combo.blockSignals(False)

        llenar(self.f_tipo, "Todos los tipos",
               [(f"{t.icono} {t.nombre}", t.id) for t in tipos.listar(self.con, con_campos=False)])
        llenar(self.f_etiqueta, "Todas las etiquetas", [(e, e) for e in elementos.nombres_etiquetas(self.con)])
        llenar(self.f_estado, "Cualquier estado", [(e, e) for e in elementos.ESTADOS])
        usados = [f[0] for f in self.con.execute(
            "SELECT DISTINCT idioma FROM elemento WHERE idioma <> '' ORDER BY idioma COLLATE ES")]
        llenar(self.f_idioma, "Cualquier idioma", [(i, i) for i in usados])

    def quitar_filtros(self):
        for w in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma, self.f_prestados, self.f_pendientes):
            w.blockSignals(True)
        for combo in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma):
            combo.setCurrentIndex(0)
        self.f_prestados.setChecked(False)
        self.f_pendientes.setChecked(False)
        for w in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma, self.f_prestados, self.f_pendientes):
            w.blockSignals(False)
        self.busqueda.clear()
        self.refrescar_resultados()

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
        self.acc_tipos = QAction("🗂 Tipos de elemento y campos…", self)
        self.acc_tipos.triggered.connect(self.editar_tipos)
        self.acc_alta_masiva = QAction("⚡ Alta masiva…", self, shortcut=QKeySequence("Ctrl+Shift+N"))
        self.acc_alta_masiva.setToolTip("Registrar muchos elementos seguidos en la misma balda o caja")
        self.acc_alta_masiva.triggered.connect(self.alta_masiva)
        self.acc_prestar = QAction("🤝 Prestar a…", self)
        self.acc_prestar.triggered.connect(self.prestar)
        self.acc_devolver = QAction("↩ Marcar como devuelto", self)
        self.acc_devolver.triggered.connect(self.devolver)
        self.acc_preferencias = QAction("Preferencias…", self)
        self.acc_preferencias.triggered.connect(lambda: Preferencias(self).exec())
        self.acc_etiquetas = QAction("🏷 Etiquetas…", self, shortcut=QKeySequence("Ctrl+E"))
        self.acc_etiquetas.setToolTip("Imprimir etiquetas con código, contenido y QR para cajas y baldas")
        self.acc_etiquetas.triggered.connect(self.imprimir_etiquetas)
        self.acc_inventario = QAction("Inventario de la ubicación seleccionada…", self)
        self.acc_inventario.triggered.connect(self.informe_inventario)
        self.acc_inf_prestados = QAction("Elementos prestados…", self)
        self.acc_inf_prestados.triggered.connect(self.informe_prestados)
        self.acc_inf_busqueda = QAction("Resultado de la búsqueda actual…", self)
        self.acc_inf_busqueda.triggered.connect(self.informe_busqueda)
        self.acc_copia = QAction("Hacer copia de seguridad…", self)
        self.acc_copia.triggered.connect(self.copia_manual)
        self.acc_restaurar = QAction("Restaurar copia de seguridad…", self)
        self.acc_restaurar.triggered.connect(self.restaurar_copia)
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
        barra.addAction(self.acc_alta_masiva)
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
        barra.addAction(self.acc_etiquetas)

    def _llenar_menu_nuevo(self):
        self.menu_nuevo.clear()
        for t in tipos.listar(self.con, con_campos=False):
            accion = self.menu_nuevo.addAction(f"{t.icono}  {t.nombre}")
            accion.triggered.connect(lambda _c=False, tipo_id=t.id: self.nuevo(tipo_id))

    def _crear_menus(self):
        archivo = self.menuBar().addMenu("&Archivo")
        archivo.addAction(self.acc_copia)
        archivo.addAction(self.acc_restaurar)
        archivo.addSeparator()
        archivo.addAction(self.acc_preferencias)
        archivo.addSeparator()
        salir = archivo.addAction("Salir")
        salir.triggered.connect(self.close)
        self.menu_archivo = archivo

        elemento = self.menuBar().addMenu("&Elemento")
        for accion in (self.acc_nuevo, self.acc_alta_masiva, self.acc_editar, self.acc_mover, self.acc_borrar):
            elemento.addAction(accion)
        elemento.addSeparator()
        elemento.addAction(self.acc_prestar)
        elemento.addAction(self.acc_devolver)

        self.menu_catalogo = self.menuBar().addMenu("&Catálogo")
        self.menu_catalogo.addAction(self.acc_ubicaciones)
        self.menu_catalogo.addAction(self.acc_tipos)

        informes = self.menuBar().addMenu("&Informes")
        informes.addAction(self.acc_etiquetas)
        informes.addSeparator()
        for accion in (self.acc_inventario, self.acc_inf_prestados, self.acc_inf_busqueda):
            informes.addAction(accion)

        self.menu_ayuda = self.menuBar().addMenu("Ay&uda")
        manual = self.menu_ayuda.addAction("Manual de usuario")
        manual.setShortcut(QKeySequence("F1"))
        manual.triggered.connect(self.abrir_manual)
        carpeta = self.menu_ayuda.addAction("Abrir la carpeta de datos")
        carpeta.triggered.connect(lambda: self._abrir(str(rutas.carpeta_datos())))
        acerca = self.menu_ayuda.addAction("Acerca de…")
        acerca.triggered.connect(lambda: comun.aviso(
            self, f"{NOMBRE} {VERSION}\n\nRegistra dónde guardas cada libro, disco, álbum o carpeta.\n"
                  "Los datos están en la carpeta «datos» junto al programa."))

    # ------------------------------------------------------------ datos

    def filtros_actuales(self) -> Filtros:
        f = Filtros(
            texto=self.busqueda.text(),
            tipo_id=self.f_tipo.currentData(),
            etiqueta=self.f_etiqueta.currentData() or "",
            estado=self.f_estado.currentData() or "",
            idioma=self.f_idioma.currentData() or "",
            solo_prestados=self.f_prestados.isChecked(),
            solo_no_consumidos=self.f_pendientes.isChecked(),
        )
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
        cabecera = self.tabla.horizontalHeader()
        if cabecera.isSortIndicatorShown() and cabecera.sortIndicatorSection() >= 0:
            # Si el usuario ordenó por una columna, se mantiene ese orden al refrescar.
            self.modelo.sort(cabecera.sortIndicatorSection(), cabecera.sortIndicatorOrder())
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
        self._llenar_filtros()
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
        for accion in (self.acc_mover, self.acc_borrar, self.acc_prestar, self.acc_devolver):
            accion.setEnabled(n >= 1)

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
            self.mover_a(ids, destino)

    def mover_a(self, ids: list[int], destino: int | None):
        """Mueve elementos (también se usa al arrastrarlos desde la tabla al árbol)."""
        elementos.mover(self.con, ids, destino)
        ruta = ubicaciones.ruta_texto(self.con, destino) if destino else "Sin ubicación"
        self.refrescar_todo()
        self.statusBar().showMessage(f"{len(ids)} elemento(s) movido(s) a {ruta}", 6000)

    def prestar(self):
        ids = self.ids_seleccionados()
        if not ids:
            return
        a_quien, ok = QInputDialog.getItem(
            self, "Prestar", f"¿A quién prestas {len(ids)} elemento(s)?",
            ["", *elementos.nombres_prestatarios(self.con)], 0, True)
        if not ok or not a_quien.strip():
            return
        elementos.prestar(self.con, ids, a_quien, date.today().isoformat())
        self.refrescar_todo(ids[0])

    def devolver(self):
        ids = self.ids_seleccionados()
        if ids:
            elementos.devolver(self.con, ids)
            self.refrescar_todo(ids[0])

    def alta_masiva(self):
        dialogo = AltaMasiva(self.con, self.ubicacion_para_nuevo(), self.f_tipo.currentData(), self)
        dialogo.exec()
        if dialogo.creados:
            self.refrescar_todo(dialogo.creados[-1])

    def editar_tipos(self):
        editor = EditorTipos(self.con, self)
        editor.exec()
        if editor.hubo_cambios:
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

    # ------------------------------------------------------------ etiquetas e informes

    def imprimir_etiquetas(self):
        DialogoEtiquetas(self.con, self.ubicacion_para_nuevo(), self).exec()

    def _pedir_pdf(self, nombre: str) -> str | None:
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar informe", nombre, "PDF (*.pdf)")
        return destino or None

    def _abrir(self, ruta: str):
        QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))

    def abrir_manual(self):
        """El PDF está junto al .exe; sin empaquetar se genera al vuelo desde docs/."""
        pdf = rutas.carpeta_programa() / "Manual de usuario.pdf"
        fuente = rutas.carpeta_programa() / "docs" / "Manual_de_usuario.md"
        if not pdf.exists() and fuente.exists():
            pdf = Path(tempfile.gettempdir()) / "Manual de usuario (Bibliotecario Virtual).pdf"
            informes.markdown_a_pdf(fuente.read_text(encoding="utf-8"), pdf, "Manual de usuario")
        if pdf.exists():
            self._abrir(str(pdf))
        else:
            comun.aviso(self, "No se encuentra el archivo «Manual de usuario.pdf» junto al programa.")

    def informe_inventario(self, destino: str | None = None, abrir: bool = True):
        ubic = self.ubicacion_para_nuevo()
        nombre = ubicaciones.obtener(self.con, ubic).codigo if ubic else "casa"
        destino = destino or self._pedir_pdf(f"inventario_{nombre}.pdf")
        if destino:
            informes.inventario(self.con, ubic, destino)
            abrir and self._abrir(destino)

    def informe_prestados(self, destino: str | None = None, abrir: bool = True):
        destino = destino or self._pedir_pdf("prestados.pdf")
        if destino:
            informes.prestados(self.con, destino)
            abrir and self._abrir(destino)

    def informe_busqueda(self, destino: str | None = None, abrir: bool = True):
        destino = destino or self._pedir_pdf("busqueda.pdf")
        if destino:
            partes = [self.ruta_actual.text()]
            if self.busqueda.text().strip():
                partes.append(f"búsqueda «{self.busqueda.text().strip()}»")
            # Se respeta el orden en que se ve la tabla.
            filas = [self.modelo.resultado(self.ordenador.mapToSource(self.ordenador.index(i, 0)).row())
                     for i in range(self.ordenador.rowCount())]
            informes.resultados(filas, " · ".join(partes), destino)
            abrir and self._abrir(destino)

    # ------------------------------------------------------------ copias de seguridad

    def copia_manual(self, destino: str | None = None):
        if destino is None:
            nombre = f"BibliotecarioVirtual_copia_{date.today():%Y%m%d}.zip"
            destino, _ = QFileDialog.getSaveFileName(self, "Guardar copia de seguridad", nombre, "ZIP (*.zip)")
            if not destino:
                return
        try:
            copias.copia_manual(self.con, destino)
        except OSError as e:
            comun.error(self, f"No se ha podido hacer la copia: {e}")
            return
        comun.aviso(self, f"Copia de seguridad guardada en:\n{destino}\n\n"
                          "Incluye los datos, las portadas y las preferencias.")

    def restaurar_copia(self):
        dialogo = DialogoRestaurar(self)
        if not dialogo.exec() or not dialogo.elegida:
            return
        if not comun.confirmar(self, "¿Sustituir los datos actuales por los de la copia elegida?\n\n"
                                     "Se guardará antes una copia del estado actual."):
            return
        try:
            copias.restaurar(self.con, dialogo.elegida)
        except (copias.ErrorCopia, OSError, sqlite3.Error) as e:
            if not conexion_abierta(self.con):
                # Falló después de cerrar la conexión: los datos anteriores siguen intactos,
                # pero hay que volver a abrirlos reiniciando el programa.
                self.restaurado = True
                comun.error(self, f"No se ha podido restaurar: {e}\n\nTus datos anteriores no se han "
                                  "modificado. El programa se reiniciará.")
                reiniciar()
                return
            comun.error(self, f"No se ha podido restaurar: {e}")
            return
        self.restaurado = True  # la conexión ya está cerrada: no se hace copia al salir
        comun.aviso(self, "Copia restaurada. El programa se reiniciará ahora.")
        reiniciar()

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
        for accion in (self.acc_editar, self.acc_mover, self.acc_prestar, self.acc_devolver, self.acc_borrar):
            menu.addAction(accion)
        menu.exec(self.tabla.viewport().mapToGlobal(posicion))
