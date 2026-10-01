"""Ventana principal: ubicaciones a la izquierda, lista en el centro y ficha a la derecha."""

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QSizePolicy,
                               QSplitter, QStackedWidget, QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import NOMBRE, VERSION, rutas
from ..datos import elementos, tipos, ubicaciones
from ..datos.ubicaciones import ErrorUbicacion
from ..servicios import busqueda, configuracion, copias, informes
from ..servicios.busqueda import Filtros
from . import comun, tema
from .alta_masiva import AltaMasiva
from .arbol_ubicaciones import ID_SIN_UBICACION, ID_TODAS, ArbolUbicaciones
from .comun import reiniciar
from .dialogo_copias import DialogoRestaurar
from .dialogo_etiquetas import DialogoEtiquetas
from .editor_tipos import EditorTipos
from .editor_ubicaciones import DialogoNuevaUbicacion, EditorUbicaciones
from .capa_fluida import CapaFluida
from .ficha_elemento import FichaElemento
from .modelo_resultados import COLUMNAS, DelegadoRuta, ModeloResultados
from .panel_detalle import PanelDetalle
from .preferencias import Preferencias
from .selector_ubicacion import elegir_ubicacion

ANCHOS_COLUMNAS = [150, 260, 170, 56, 260, 90, 100]


def conexion_abierta(con: sqlite3.Connection) -> bool:
    try:
        con.execute("SELECT 1")
        return True
    except sqlite3.ProgrammingError:
        return False


class EstadoVacio(QWidget):
    """Pantalla que sustituye a la tabla cuando no hay nada que mostrar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logo = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.titulo = QLabel(objectName="titulo_seccion", alignment=Qt.AlignmentFlag.AlignCenter)
        self.texto = QLabel(objectName="suave", alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.texto.setMaximumWidth(tema.px(460))
        self.botones = QHBoxLayout()
        capa = QVBoxLayout(self)
        capa.addStretch(2)
        capa.addWidget(self.logo)
        capa.addWidget(self.titulo)
        capa.addWidget(self.texto, alignment=Qt.AlignmentFlag.AlignHCenter)
        capa.addSpacing(tema.px(12))
        capa.addLayout(self.botones)
        capa.addStretch(3)

    def configurar(self, logo: bool, icono: str, titulo: str, texto: str, botones: list) -> None:
        if logo:
            imagen = QPixmap(str(comun.RECURSOS / "logo.png"))
            self.logo.setPixmap(imagen.scaledToWidth(tema.px(170), Qt.TransformationMode.SmoothTransformation))
        else:
            self.logo.setPixmap(tema.icono(icono, "borde_fuerte", tema.px(56)).pixmap(tema.px(56)))
        self.titulo.setText(titulo)
        self.texto.setText(texto)
        while self.botones.count():
            item = self.botones.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.botones.addStretch()
        for b in botones:
            self.botones.addWidget(b)
        self.botones.addStretch()


class VentanaPrincipal(QMainWindow):
    def __init__(self, con: sqlite3.Connection):
        super().__init__()
        self.con = con
        self.restaurado = False
        self.iconos_acciones: list[tuple[QAction, str, str]] = []
        self.setWindowTitle(NOMBRE)
        self.setWindowIcon(comun.icono_app())
        self.resize(tema.px(1360), tema.px(800))

        self._crear_acciones()
        self._crear_lateral()
        self._crear_centro()
        self.detalle = PanelDetalle(con)

        self.divisor = QSplitter()
        self.divisor.setChildrenCollapsible(False)
        for w in (self.lateral, self.centro, self.detalle):
            self.divisor.addWidget(w)
        self.divisor.setStretchFactor(1, 1)
        self.divisor.setSizes([tema.px(280), tema.px(780), tema.px(330)])
        self.centro.setMinimumWidth(tema.px(420))
        self.setCentralWidget(self.divisor)

        self._crear_barra()
        self._crear_menus()
        self._crear_selector_modo()
        self.detalle.setVisible(bool(configuracion.obtener("panel_detalle")))
        self.acc_panel.setChecked(self.detalle.isVisible())

        self.temporizador = QTimer(self, singleShot=True, interval=250)
        self.temporizador.timeout.connect(self.refrescar_resultados)
        self.busqueda.textChanged.connect(lambda _t: self.temporizador.start())
        self.filtro_arbol.textChanged.connect(self.arbol.filtrar)
        self.arbol.ubicacion_cambiada.connect(lambda _id: self.refrescar_resultados())
        self.tabla.doubleClicked.connect(lambda _i: self.editar())
        self.tabla.customContextMenuRequested.connect(self._menu_contextual)
        self.tabla.selectionModel().selectionChanged.connect(lambda *_: self._seleccion_cambiada())
        self.detalle.editar.connect(self.editar)
        self.detalle.mover.connect(self.mover)
        self.detalle.prestar.connect(self.prestar)
        self.detalle.devolver.connect(self.devolver)
        self.detalle.borrar.connect(self.borrar)
        self.detalle.ir_a_ubicacion.connect(self.mostrar_ubicacion)
        tema.avisador.cambiado.connect(self._al_cambiar_tema)

        self._aplicar_iconos()
        self.aplicar_modo(configuracion.obtener("modo"))
        self.refrescar_resultados()

    # ------------------------------------------------------------ construcción

    def _accion(self, texto: str, icono: str, funcion, atajo=None, ayuda: str = "", tono: str = "texto") -> QAction:
        accion = QAction(texto, self)
        if atajo is not None:
            accion.setShortcut(atajo)
        if ayuda:
            accion.setToolTip(ayuda)
            accion.setStatusTip(ayuda)
        accion.triggered.connect(lambda _c=False: funcion())
        if icono:
            self.iconos_acciones.append((accion, icono, tono))
        return accion

    def _crear_acciones(self):
        A = self._accion
        self.acc_nuevo = A("Nuevo", "plus", lambda: self.nuevo(), QKeySequence.StandardKey.New,
                           "Añadir un elemento a la colección (Ctrl+N)", "primario")
        # El botón destacado de la barra lleva el icono en blanco: acción propia sin atajo.
        self.acc_nuevo_barra = A("Nuevo", "plus", lambda: self.nuevo(), None,
                                 "Añadir un elemento a la colección (Ctrl+N)", "primario_texto")
        self.acc_alta_masiva = A("Alta masiva", "list-plus", self.alta_masiva, QKeySequence("Ctrl+Shift+N"),
                                 "Registrar muchos elementos seguidos en la misma balda o caja")
        self.acc_editar = A("Editar", "pencil", self.editar, QKeySequence("F2"), "Editar la ficha (F2)")
        self.acc_mover = A("Mover a…", "folder-input", self.mover, QKeySequence("Ctrl+M"),
                           "Mover a otra ubicación (también puedes arrastrar al árbol)")
        self.acc_borrar = A("Borrar", "trash-2", self.borrar, QKeySequence.StandardKey.Delete, tono="peligro")
        self.acc_prestar = A("Prestar a…", "handshake", self.prestar)
        self.acc_devolver = A("Marcar como devuelto", "undo-2", self.devolver)
        self.acc_ubicaciones = A("Casa", "house", self.editar_ubicaciones, ayuda="Plantas, habitaciones, "
                                 "muebles, baldas y cajas de la casa")
        self.acc_ubicaciones_menu = A("Ubicaciones de la casa…", "house", self.editar_ubicaciones)
        self.acc_tipos = A("Tipos de elemento y campos…", "sliders-horizontal", self.editar_tipos)
        self.acc_etiquetas = A("Etiquetas", "qr-code", self.imprimir_etiquetas, QKeySequence("Ctrl+E"),
                               "Imprimir etiquetas con código, contenido y QR para cajas y baldas")
        self.acc_inventario = A("Inventario de la ubicación seleccionada…", "file-text", self.informe_inventario)
        self.acc_inf_prestados = A("Elementos prestados…", "handshake", self.informe_prestados)
        self.acc_inf_busqueda = A("Resultado de la búsqueda actual…", "list", self.informe_busqueda)
        self.acc_copia = A("Hacer copia de seguridad…", "archive", self.copia_manual)
        self.acc_restaurar = A("Restaurar copia de seguridad…", "rotate-ccw", self.restaurar_copia)
        self.acc_preferencias = A("Preferencias…", "settings", self.preferencias, QKeySequence("Ctrl+,"),
                                  "Apariencia, tamaño de letra, copias e ISBN")
        self.acc_buscar = A("Buscar", "", lambda: (self.busqueda.setFocus(), self.busqueda.selectAll()),
                            QKeySequence.StandardKey.Find)
        self.addAction(self.acc_buscar)
        self.acc_mas_grande = A("Aumentar tamaño", "zoom-in", lambda: self.cambiar_escala(+1), QKeySequence("Ctrl++"))
        self.acc_mas_pequeno = A("Reducir tamaño", "zoom-out", lambda: self.cambiar_escala(-1), QKeySequence("Ctrl+-"))
        self.acc_tamano_normal = A("Tamaño normal", "", lambda: self.cambiar_escala(0), QKeySequence("Ctrl+0"))
        for accion in (self.acc_mas_grande, self.acc_mas_pequeno, self.acc_tamano_normal):
            self.addAction(accion)
        self.acc_panel = A("Panel de detalle", "panel-right", lambda: self.mostrar_panel(self.acc_panel.isChecked()),
                           QKeySequence("F9"), "Mostrar u ocultar la ficha a la derecha (F9)")
        self.acc_panel.setCheckable(True)
        # Modo sencillo / avanzado, con los mismos atajos que la calculadora de Windows.
        self.grupo_modo = QActionGroup(self)
        self.acciones_modo: dict[str, QAction] = {}
        for clave, texto_, atajo, ayuda in (
                ("sencillo", "Modo sencillo", "Alt+1", "Solo los campos y opciones básicos"),
                ("avanzado", "Modo avanzado", "Alt+2", "Todos los campos, filtros y opciones")):
            accion = A(texto_, "", lambda c=clave: self.cambiar_modo(c), QKeySequence(atajo), ayuda)
            accion.setCheckable(True)
            self.grupo_modo.addAction(accion)
            self.acciones_modo[clave] = accion

    def _crear_lateral(self):
        self.arbol = ArbolUbicaciones(self.con, contar=True, especiales=True, al_mover=self._mover_ubicacion,
                                      al_soltar_elementos=self.mover_a)
        self.arbol.setObjectName("lateral")
        self.arbol.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.arbol.customContextMenuRequested.connect(self._menu_arbol)
        self.filtro_arbol = QLineEdit(placeholderText="Filtrar ubicaciones…", clearButtonEnabled=True)
        self.b_editar_casa = comun.boton("", "settings", "plano", "Editar las ubicaciones de la casa")
        self.b_editar_casa.clicked.connect(self.editar_ubicaciones)
        cabecera = QHBoxLayout()
        cabecera.addWidget(QLabel("UBICACIONES", objectName="encabezado"))
        cabecera.addStretch()
        cabecera.addWidget(self.b_editar_casa)
        ayuda = QLabel("Arrastra para ordenar las plantas y ubicaciones, o suelta aquí elementos para moverlos.",
                       objectName="suave", wordWrap=True)
        self.lateral = QWidget(objectName="lateral")
        self.lateral.setMinimumWidth(tema.px(250))
        self.lateral.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        capa = QVBoxLayout(self.lateral)
        capa.setContentsMargins(tema.px(12), tema.px(12), tema.px(6), tema.px(10))
        capa.setSpacing(tema.px(8))
        capa.addLayout(cabecera)
        capa.addWidget(self.filtro_arbol)
        capa.addWidget(self.arbol, 1)
        capa.addWidget(ayuda)

    def _crear_centro(self):
        # Tabla
        self.modelo = ModeloResultados(self)
        self.tabla = QTableView()
        # La tabla usa el modelo directamente (ordena el propio modelo): un intermediario duplicaba
        # las consultas celda a celda y hacía lento seleccionarlo todo con decenas de miles de filas.
        self.tabla.setModel(self.modelo)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(-1, Qt.SortOrder.AscendingOrder)  # orden de la búsqueda (relevancia)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setWordWrap(False)
        self.tabla.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tabla.setItemDelegateForColumn(4, DelegadoRuta(self.tabla))  # rutas: se ve el final
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.setDragEnabled(True)
        self.tabla.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # el título ocupa lo que sobra
        cabecera.setStretchLastSection(False)
        cabecera.setMinimumSectionSize(tema.px(50))
        cabecera.setHighlightSections(False)
        cabecera.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        cabecera.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        cabecera.customContextMenuRequested.connect(self._menu_columnas)
        for columna in configuracion.obtener("columnas_ocultas"):
            if 0 < columna < len(ANCHOS_COLUMNAS) and columna != 1:
                self.tabla.setColumnHidden(columna, True)
        self._ajustar_tabla()

        # Título, contador y filtros
        self.ruta_actual = QLabel(objectName="titulo_seccion", textFormat=Qt.TextFormat.PlainText)
        self.contador = QLabel(objectName="contador")
        titulo = QHBoxLayout()
        titulo.addWidget(self.ruta_actual)
        titulo.addStretch()
        titulo.addWidget(self.contador)

        self.vacio = EstadoVacio()
        self.pila = QStackedWidget()
        self.pila.addWidget(self.tabla)
        self.pila.addWidget(self.vacio)

        self.centro = QWidget()
        capa = QVBoxLayout(self.centro)
        capa.setContentsMargins(tema.px(18), tema.px(14), tema.px(18), tema.px(10))
        capa.setSpacing(tema.px(10))
        capa.addLayout(titulo)
        self.barra_filtros = self._crear_filtros()
        capa.addWidget(self.barra_filtros)
        capa.addWidget(self.pila, 1)

    def _ajustar_tabla(self):
        self.tabla.verticalHeader().setDefaultSectionSize(tema.px(34))
        self.tabla.setIconSize(QSize(tema.px(18), tema.px(18)))
        for columna, ancho in enumerate(ANCHOS_COLUMNAS):
            self.tabla.setColumnWidth(columna, tema.px(ancho))

    def _crear_filtros(self) -> QWidget:
        self.f_tipo = QComboBox()
        self.f_etiqueta = QComboBox()
        self.f_estado = QComboBox()
        self.f_idioma = QComboBox()
        self.f_prestados = QCheckBox("Prestados")
        self.f_pendientes = QCheckBox("Pendientes")
        self.f_pendientes.setToolTip("Solo lo que no está marcado como leído, visto, escuchado…")
        self.f_limpiar = comun.boton("Quitar filtros", "filter-x", "plano")
        self._llenar_filtros()
        panel = QWidget()
        capa = CapaFluida(panel, tema.px(8))  # pasa a otra línea si no cabe
        self.icono_filtro = QLabel()
        capa.addWidget(self.icono_filtro)
        for combo in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for w in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma, self.f_prestados,
                  self.f_pendientes, self.f_limpiar):
            capa.addWidget(w)
        for combo in (self.f_tipo, self.f_etiqueta, self.f_estado, self.f_idioma):
            combo.currentIndexChanged.connect(lambda _i: self.refrescar_resultados())
        for casilla in (self.f_prestados, self.f_pendientes):
            casilla.toggled.connect(lambda _v: self.refrescar_resultados())
        self.f_limpiar.clicked.connect(self.quitar_filtros)
        return panel

    def _llenar_filtros(self):
        """Rellena los desplegables de filtro conservando lo que estuviera elegido."""
        def llenar(combo: QComboBox, primero: str, opciones: list[tuple[str, object, str]]):
            actual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(primero, None)
            for texto_, dato, icono in opciones:
                if icono:
                    combo.addItem(tema.icono(icono, "primario"), texto_, dato)
                else:
                    combo.addItem(texto_, dato)
            indice = combo.findData(actual)
            combo.setCurrentIndex(indice if indice >= 0 else 0)
            combo.blockSignals(False)

        llenar(self.f_tipo, "Todos los tipos",
               [(t.nombre, t.id, t.icono) for t in tipos.listar(self.con, con_campos=False)])
        llenar(self.f_etiqueta, "Todas las etiquetas",
               [(e, e, "tag") for e in elementos.nombres_etiquetas(self.con)])
        llenar(self.f_estado, "Cualquier estado", [(e, e, "") for e in elementos.ESTADOS])
        usados = [f[0] for f in self.con.execute(
            "SELECT DISTINCT idioma FROM elemento WHERE idioma <> '' ORDER BY idioma COLLATE ES")]
        llenar(self.f_idioma, "Cualquier idioma", [(i, i, "") for i in usados])

    def _hay_filtros(self) -> bool:
        return any([self.f_tipo.currentIndex() > 0, self.f_etiqueta.currentIndex() > 0,
                    self.f_estado.currentIndex() > 0, self.f_idioma.currentIndex() > 0,
                    self.f_prestados.isChecked(), self.f_pendientes.isChecked(), self.busqueda.text().strip()])

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

    def _crear_barra(self):
        barra = self.addToolBar("Principal")
        barra.setObjectName("barra_principal")
        barra.setMovable(False)
        barra.setFloatable(False)
        barra.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        barra.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.barra = barra

        self.logo = QLabel()
        barra.addWidget(self.logo)
        barra.addWidget(QLabel(NOMBRE, objectName="titulo_app"))
        espacio = QWidget()
        espacio.setFixedWidth(tema.px(18))
        barra.addWidget(espacio)

        self.busqueda = QLineEdit(objectName="busqueda", clearButtonEnabled=True)
        self.busqueda.setPlaceholderText('Buscar título, autor, etiqueta, ubicación…   (Ctrl+F)')
        self.busqueda.setToolTip('Sin acentos ni mayúsculas. "Frase exacta" entre comillas. '
                                 '-palabra para excluir.')
        self.busqueda.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.busqueda.setMaximumWidth(tema.px(480))
        self.accion_lupa = self.busqueda.addAction(tema.icono("search", "texto_suave"),
                                                   QLineEdit.ActionPosition.LeadingPosition)
        barra.addWidget(self.busqueda)
        separacion = QWidget()
        separacion.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        barra.addWidget(separacion)

        self.boton_nuevo = QToolButton(objectName="primario")
        self.boton_nuevo.setDefaultAction(self.acc_nuevo_barra)
        self.boton_nuevo.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.boton_nuevo.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.menu_nuevo = QMenu(self)
        self.boton_nuevo.setMenu(self.menu_nuevo)
        self._llenar_menu_nuevo()
        barra.addWidget(self.boton_nuevo)
        barra.addAction(self.acc_alta_masiva)
        barra.addSeparator()
        barra.addAction(self.acc_ubicaciones)
        barra.addAction(self.acc_etiquetas)
        self.boton_informes = QToolButton()
        self.boton_informes.setText("Informes")
        self.boton_informes.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.boton_informes.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_informes = QMenu(self)
        for accion in (self.acc_inventario, self.acc_inf_prestados, self.acc_inf_busqueda):
            menu_informes.addAction(accion)
        self.boton_informes.setMenu(menu_informes)
        self.accion_boton_informes = barra.addWidget(self.boton_informes)  # para ocultarlo en modo sencillo
        barra.addSeparator()
        self.ir_codigo = QLineEdit(placeholderText="Ir a código", clearButtonEnabled=True)
        self.ir_codigo.setToolTip("Escribe o pega el código de una etiqueta (p. ej. PB-SAL-EA-B3) y pulsa Intro")
        self.ir_codigo.setFixedWidth(tema.px(150))
        self.accion_qr = self.ir_codigo.addAction(tema.icono("qr-code", "texto_suave"),
                                                  QLineEdit.ActionPosition.LeadingPosition)
        self.ir_codigo.returnPressed.connect(self.ir_a_codigo)
        barra.addWidget(self.ir_codigo)
        barra.addAction(self.acc_panel)
        barra.addAction(self.acc_preferencias)
        for accion in (self.acc_panel, self.acc_preferencias):
            barra.widgetForAction(accion).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def _menu_columnas(self, posicion):
        """Clic derecho en la cabecera: mostrar u ocultar columnas (se recuerda)."""
        menu = QMenu(self)
        for columna, nombre in enumerate(COLUMNAS):
            accion = menu.addAction(nombre)
            accion.setCheckable(True)
            accion.setChecked(not self.tabla.isColumnHidden(columna))
            accion.setEnabled(columna != 1)  # el título siempre se ve
            accion.toggled.connect(lambda visible, c=columna: self._mostrar_columna(c, visible))
        menu.exec(self.tabla.horizontalHeader().mapToGlobal(posicion))

    def _mostrar_columna(self, columna: int, visible: bool):
        self.tabla.setColumnHidden(columna, not visible)
        ajustes = configuracion.cargar()
        ajustes["columnas_ocultas"] = [c for c in range(len(COLUMNAS)) if self.tabla.isColumnHidden(c)]
        configuracion.guardar(ajustes)

    def _llenar_menu_nuevo(self):
        self.menu_nuevo.clear()
        for t in tipos.listar(self.con, con_campos=False):
            accion = self.menu_nuevo.addAction(tema.icono(t.icono or "package", "primario"), t.nombre)
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
        self.menu_catalogo.addAction(self.acc_ubicaciones_menu)
        self.menu_catalogo.addAction(self.acc_tipos)

        informes_menu = self.menuBar().addMenu("&Informes")
        informes_menu.addAction(self.acc_etiquetas)
        informes_menu.addSeparator()
        for accion in (self.acc_inventario, self.acc_inf_prestados, self.acc_inf_busqueda):
            informes_menu.addAction(accion)

        ver = self.menuBar().addMenu("&Ver")
        for accion in self.acciones_modo.values():
            ver.addAction(accion)
        ver.addSeparator()
        grupo = QActionGroup(self)
        self.acciones_tema: dict[str, QAction] = {}
        actual = configuracion.obtener("tema")
        for clave, nombre in tema.TEMAS:
            accion = ver.addAction(f"Tema {nombre.lower()}" if clave != "sistema" else "Tema según Windows")
            accion.setCheckable(True)
            accion.setChecked(clave == actual)
            accion.triggered.connect(lambda _c=False, t=clave: self.cambiar_tema(t))
            grupo.addAction(accion)
            self.acciones_tema[clave] = accion
        ver.addSeparator()
        for accion in (self.acc_mas_grande, self.acc_mas_pequeno, self.acc_tamano_normal):
            ver.addAction(accion)
        ver.addSeparator()
        ver.addAction(self.acc_panel)

        self.menu_ayuda = self.menuBar().addMenu("Ay&uda")
        manual = self.menu_ayuda.addAction("Manual de usuario")
        manual.setShortcut(QKeySequence("F1"))
        manual.triggered.connect(self.abrir_manual)
        carpeta = self.menu_ayuda.addAction("Abrir la carpeta de datos")
        carpeta.triggered.connect(lambda: self._abrir(str(rutas.carpeta_datos())))
        acerca = self.menu_ayuda.addAction(f"Acerca de {NOMBRE}…")
        acerca.triggered.connect(lambda: comun.aviso(
            self, f"{NOMBRE} {VERSION}\n\nDónde está cada libro, disco, álbum o carpeta de tu casa.\n"
                  "Los datos están en la carpeta «datos» junto al programa.\n\n"
                  "Iconos: Lucide (licencia ISC)."))

    # ------------------------------------------------------------ aspecto

    def _aplicar_iconos(self):
        """Pinta (o repinta tras cambiar de tema) los iconos que dependen de los colores."""
        for accion, nombre, tono in self.iconos_acciones:
            accion.setIcon(tema.icono(nombre, tono))
        self.boton_informes.setIcon(tema.icono("file-text"))
        self.accion_lupa.setIcon(tema.icono("search", "texto_suave"))
        self.accion_qr.setIcon(tema.icono("qr-code", "texto_suave"))
        self.icono_filtro.setPixmap(tema.icono("filter", "texto_suave").pixmap(tema.px(16)))
        logo = QPixmap(str(comun.RECURSOS / "icono.png"))
        self.logo.setPixmap(logo.scaled(tema.px(34), tema.px(34), Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
        tamano = QSize(tema.px(18), tema.px(18))
        self.barra.setIconSize(tamano)
        self.arbol.setIconSize(tamano)
        self._ajustar_tabla()
        comun.recolorear_botones(self)

    def _al_cambiar_tema(self):
        if not conexion_abierta(self.con):  # p. ej. tras restaurar una copia, mientras se reinicia
            return
        self._aplicar_iconos()
        self.arbol.cargar()
        self.arbol.filtrar(self.filtro_arbol.text())
        self._llenar_menu_nuevo()
        self._llenar_filtros()
        self.modelo.layoutChanged.emit()
        self.detalle.refrescar()
        self._actualizar_vacio()

    def cambiar_tema(self, clave: str):
        ajustes = configuracion.cargar()
        ajustes["tema"] = clave
        configuracion.guardar(ajustes)
        tema.aplicar(QApplication.instance(), clave, ajustes["escala"], ajustes["fuente"])

    def cambiar_escala(self, paso: int):
        """Ctrl++ / Ctrl+- / Ctrl+0: recorre los tamaños de interfaz disponibles."""
        valores = [v for _, v in tema.ESCALAS]
        ajustes = configuracion.cargar()
        actual = min(valores, key=lambda v: abs(v - float(ajustes["escala"])))
        if paso == 0:
            nueva = 1.0
        else:
            nueva = valores[max(0, min(len(valores) - 1, valores.index(actual) + paso))]
        ajustes["escala"] = nueva
        configuracion.guardar(ajustes)
        tema.aplicar(QApplication.instance(), ajustes["tema"], nueva, ajustes["fuente"])
        nombre = next(n for n, v in tema.ESCALAS if v == nueva)
        self.statusBar().showMessage(f"Tamaño de la interfaz: {nombre} ({round(nueva * 100)} %)", 4000)

    def mostrar_panel(self, visible: bool):
        self.detalle.setVisible(visible)
        self.acc_panel.setChecked(visible)
        ajustes = configuracion.cargar()
        ajustes["panel_detalle"] = visible
        configuracion.guardar(ajustes)

    def preferencias(self):
        dialogo = Preferencias(self)
        if dialogo.exec():
            actual = configuracion.obtener("tema")
            if actual in self.acciones_tema:
                self.acciones_tema[actual].setChecked(True)
            self.aplicar_modo(configuracion.obtener("modo"))

    # ------------------------------------------------------------ modo sencillo / avanzado

    def _crear_selector_modo(self):
        """Botón en la esquina inferior derecha que muestra el modo actual y permite cambiarlo."""
        self.boton_modo = QToolButton(objectName="boton_modo")
        self.boton_modo.setAutoRaise(True)
        self.boton_modo.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.boton_modo.setToolTip("Cambiar entre el modo sencillo y el avanzado (Alt+1 / Alt+2)")
        menu = QMenu(self)
        for accion in self.acciones_modo.values():
            menu.addAction(accion)
        self.boton_modo.setMenu(menu)
        self.statusBar().addPermanentWidget(self.boton_modo)

    def cambiar_modo(self, clave: str):
        ajustes = configuracion.cargar()
        ajustes["modo"] = clave
        configuracion.guardar(ajustes)
        self.aplicar_modo(clave)
        self.statusBar().showMessage(
            "Modo sencillo: se muestran solo los campos y opciones básicos." if clave == "sencillo" else
            "Modo avanzado: se muestran todos los campos, filtros y opciones.", 6000)

    def aplicar_modo(self, clave: str):
        """El modo sencillo oculta filtros y opciones poco habituales. No cambia ningún dato:
        todo sigue accesible desde los menús o pasando al modo avanzado."""
        avanzado = clave == "avanzado"
        self.modo = "avanzado" if avanzado else "sencillo"
        self.acciones_modo[self.modo].setChecked(True)
        self.boton_modo.setText("Modo avanzado" if avanzado else "Modo sencillo")
        avanzados = (self.f_etiqueta, self.f_estado, self.f_idioma, self.f_pendientes)
        if not avanzado and any([self.f_etiqueta.currentIndex() > 0, self.f_estado.currentIndex() > 0,
                                 self.f_idioma.currentIndex() > 0, self.f_pendientes.isChecked()]):
            # Un filtro oculto pero activo escondería resultados sin que se vea por qué.
            for combo in (self.f_etiqueta, self.f_estado, self.f_idioma):
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)
            self.f_pendientes.blockSignals(True)
            self.f_pendientes.setChecked(False)
            self.f_pendientes.blockSignals(False)
            self.refrescar_resultados()
        for w in avanzados:
            w.setVisible(avanzado)
        self.accion_boton_informes.setVisible(avanzado)  # los informes siguen en el menú Informes
        self.acc_tipos.setVisible(avanzado)

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
            titulo = "Toda la colección"
        self.ruta_actual.setText(titulo)
        self._actualizar_contadores()
        if seleccionar is not None:
            self.seleccionar_elemento(seleccionar)
        self._seleccion_cambiada()

    def _actualizar_vacio(self):
        """Muestra la tabla o, si no hay nada, una pantalla que explica qué hacer."""
        self.barra_filtros.setVisible(bool(getattr(self, "total", 0)))  # sin nada, los filtros sobran
        if self.modelo.rowCount():
            self.pila.setCurrentWidget(self.tabla)
            return
        if not getattr(self, "total", 0):
            b1 = comun.boton("Configurar la casa", "house")
            b1.clicked.connect(self.editar_ubicaciones)
            b2 = comun.boton("Añadir el primer elemento", "plus", "primario")
            b2.clicked.connect(lambda: self.nuevo())
            b3 = comun.boton("Alta masiva", "list-plus")
            b3.clicked.connect(self.alta_masiva)
            self.vacio.configurar(True, "", f"Te damos la bienvenida a {NOMBRE}",
                                  "Empieza describiendo tu casa (plantas, habitaciones, muebles, baldas y cajas) "
                                  "y después registra lo que guardas en cada sitio.", [b1, b2, b3])
        elif self._hay_filtros():
            b = comun.boton("Quitar filtros y búsqueda", "filter-x")
            b.clicked.connect(self.quitar_filtros)
            self.vacio.configurar(False, "search", "No hay resultados",
                                  "Prueba con otras palabras o quita algún filtro.", [b])
        else:
            b = comun.boton("Añadir elemento aquí", "plus", "primario")
            b.clicked.connect(lambda: self.nuevo())
            self.vacio.configurar(False, "box", "Esta ubicación está vacía",
                                  "Añade algo aquí o arrastra elementos desde otra ubicación.", [b])
        self.pila.setCurrentWidget(self.vacio)

    def refrescar_elementos(self, ids: list[int], seleccionar: int | None = None):
        """Tras guardar, mover o prestar: solo se actualizan esas filas y los contadores.

        Con 90.000 elementos, recargarlo todo tardaba ~3 s en cada guardado.
        """
        if not ids or len(ids) > 900:
            self.refrescar_todo(seleccionar)
            return
        filtros = self.filtros_actuales()
        filtros.ids = list(ids)
        visibles = {r.id: r for r in busqueda.buscar(self.con, filtros)}
        for id_ in ids:
            if id_ in visibles:
                self.modelo.poner(visibles[id_])
            else:
                self.modelo.quitar(id_)  # ya no cumple la búsqueda o los filtros (p. ej. se movió)
        self.arbol.cargar()
        self.arbol.filtrar(self.filtro_arbol.text())
        self._llenar_filtros()
        self._actualizar_contadores()
        if seleccionar is not None:
            self.seleccionar_elemento(seleccionar)
        self._seleccion_cambiada()

    def _actualizar_contadores(self):
        self.total = self.con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
        n = self.modelo.rowCount()
        self.contador.setText(f"{n:,} elemento{'s' if n != 1 else ''}".replace(",", "."))
        self.statusBar().showMessage(f"Mostrando {n} de {self.total} elementos")
        self._actualizar_vacio()

    def refrescar_todo(self, seleccionar: int | None = None):
        self.arbol.cargar()
        self.arbol.filtrar(self.filtro_arbol.text())
        self._llenar_menu_nuevo()
        self._llenar_filtros()
        self.refrescar_resultados(seleccionar)

    def seleccionar_elemento(self, elemento_id: int) -> None:
        for fila in range(self.modelo.rowCount()):
            if self.modelo.resultado(fila).id == elemento_id:
                indice = self.modelo.index(fila, 1)
                self.tabla.selectRow(indice.row())
                self.tabla.scrollTo(indice)
                return

    def ids_seleccionados(self) -> list[int]:
        """Ids de las filas seleccionadas, leídos por rangos (Ctrl+A con 100.000 filas es inmediato).

        La tabla usa el modelo sin intermediarios: la fila que se ve es la misma fila del modelo.
        """
        filas: set[int] = set()
        for rango in self.tabla.selectionModel().selection():
            filas.update(range(rango.top(), rango.bottom() + 1))
        return [self.modelo.filas[f].id for f in sorted(filas) if f < len(self.modelo.filas)]

    def _seleccion_cambiada(self):
        ids = self.ids_seleccionados()
        n = len(ids)
        self.acc_editar.setEnabled(n == 1)
        for accion in (self.acc_mover, self.acc_borrar, self.acc_prestar, self.acc_devolver):
            accion.setEnabled(n >= 1)
        self.detalle.mostrar(ids)

    # compatibilidad con el nombre anterior
    _actualizar_acciones = _seleccion_cambiada

    # ------------------------------------------------------------ ubicaciones desde el árbol

    def mostrar_ubicacion(self, ubicacion_id: int):
        self.filtro_arbol.clear()
        self.arbol.seleccionar(ubicacion_id)

    def _mover_ubicacion(self, ubicacion_id: int, nuevo_padre_id: int | None, indice: int | None):
        """Arrastrar en el árbol: reordena plantas y ubicaciones. El orden se guarda en la base de datos."""
        try:
            with comun.ocupado(self, "Reorganizando ubicaciones…"):
                ubicaciones.mover(self.con, ubicacion_id, nuevo_padre_id, indice)
        except ErrorUbicacion as e:
            comun.error(self, str(e))
        self.arbol.cargar(ubicacion_id)
        self.refrescar_resultados()

    def desplazar_ubicacion(self, ubicacion_id: int, paso: int):
        u = ubicaciones.obtener(self.con, ubicacion_id)
        if u is None:
            return
        hermanos = [h.id for h in ubicaciones.hijos(self.con, u.padre_id)]
        nuevo = hermanos.index(u.id) + paso
        if 0 <= nuevo < len(hermanos):
            self._mover_ubicacion(u.id, u.padre_id, nuevo)

    def _menu_arbol(self, posicion):
        item = self.arbol.itemAt(posicion)
        if item is None:
            return
        self.arbol.setCurrentItem(item)
        ubic = self.ubicacion_para_nuevo()
        menu = QMenu(self)
        if ubic is not None:
            u = ubicaciones.obtener(self.con, ubic)
            hermanos = [h.id for h in ubicaciones.hijos(self.con, u.padre_id)]
            pos = hermanos.index(u.id)
            a = menu.addAction(tema.icono("plus", "primario"), "Añadir un elemento aquí")
            a.triggered.connect(lambda: self.nuevo())
            a = menu.addAction(tema.icono("list-plus"), "Alta masiva aquí")
            a.triggered.connect(self.alta_masiva)
            menu.addSeparator()
            a = menu.addAction(tema.icono("folder-open"), "Nueva ubicación dentro…")
            a.triggered.connect(lambda: self._nueva_ubicacion(ubic))
            a = menu.addAction(tema.icono("pencil"), "Editar esta ubicación…")
            a.triggered.connect(self.editar_ubicaciones)
            a = menu.addAction(tema.icono("arrow-up"), "Subir")
            a.setEnabled(pos > 0)
            a.triggered.connect(lambda: self.desplazar_ubicacion(ubic, -1))
            a = menu.addAction(tema.icono("arrow-down"), "Bajar")
            a.setEnabled(pos < len(hermanos) - 1)
            a.triggered.connect(lambda: self.desplazar_ubicacion(ubic, +1))
            menu.addSeparator()
            a = menu.addAction(tema.icono("qr-code"), "Imprimir etiqueta…")
            a.triggered.connect(self.imprimir_etiquetas)
        a = menu.addAction(tema.icono("file-text"), "Inventario en PDF…")
        a.triggered.connect(self.informe_inventario)
        menu.exec(self.arbol.viewport().mapToGlobal(posicion))

    def _nueva_ubicacion(self, padre_id: int):
        dialogo = DialogoNuevaUbicacion(self.con, padre_id, self)
        if dialogo.exec():
            self.arbol.cargar(dialogo.nuevo_id)

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
            self.refrescar_elementos(guardados, guardados[-1])

    def editar(self):
        ids = self.ids_seleccionados()
        if len(ids) != 1:
            return
        ficha = FichaElemento(self.con, elemento_id=ids[0], parent=self)
        if ficha.exec():
            self.refrescar_elementos(ids, ids[0])

    def mover(self):
        ids = self.ids_seleccionados()
        if not ids:
            return
        destino = elegir_ubicacion(self.con, self, titulo=f"Mover {len(ids)} elemento(s) a…")
        if destino is not None:
            self.mover_a(ids, destino)

    def mover_a(self, ids: list[int], destino: int | None):
        """Mueve elementos (también se usa al arrastrarlos desde la tabla al árbol)."""
        with comun.ocupado(self, f"Moviendo {len(ids)} elemento(s)…"):
            elementos.mover(self.con, ids, destino)
        ruta = ubicaciones.ruta_texto(self.con, destino) if destino else "Sin ubicación"
        self.refrescar_elementos(ids)
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
        self.refrescar_elementos(ids, ids[0])

    def devolver(self):
        ids = self.ids_seleccionados()
        if ids:
            elementos.devolver(self.con, ids)
            self.refrescar_elementos(ids, ids[0])

    def alta_masiva(self):
        dialogo = AltaMasiva(self.con, self.ubicacion_para_nuevo(), self.f_tipo.currentData(), self)
        dialogo.exec()
        if dialogo.creados:
            self.refrescar_elementos(dialogo.creados, dialogo.creados[-1])

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
            with comun.ocupado(self, f"Borrando {len(ids)} elemento(s)…"):
                elementos.borrar(self.con, ids)
                if len(ids) > 900:
                    self.refrescar_todo()
                    return
                for id_ in ids:
                    self.modelo.quitar(id_)
            self.arbol.cargar()
            self._actualizar_contadores()
            self._seleccion_cambiada()

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
            pdf = Path(tempfile.gettempdir()) / "Manual de usuario (LibriDomus).pdf"
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
            with comun.ocupado(self, "Generando el inventario…"):
                informes.inventario(self.con, ubic, destino, self._progreso_pdf)
            abrir and self._abrir(destino)

    def informe_prestados(self, destino: str | None = None, abrir: bool = True):
        destino = destino or self._pedir_pdf("prestados.pdf")
        if destino:
            with comun.ocupado(self, "Generando el informe…"):
                informes.prestados(self.con, destino, self._progreso_pdf)
            abrir and self._abrir(destino)

    def informe_busqueda(self, destino: str | None = None, abrir: bool = True):
        destino = destino or self._pedir_pdf("busqueda.pdf")
        if destino:
            partes = [self.ruta_actual.text()]
            if self.busqueda.text().strip():
                partes.append(f"búsqueda «{self.busqueda.text().strip()}»")
            # Se respeta el orden en que se ve la tabla.
            filas = list(self.modelo.filas)
            with comun.ocupado(self, "Generando el informe…"):
                informes.resultados(filas, " · ".join(partes), destino, self._progreso_pdf)
            abrir and self._abrir(destino)

    def _progreso_pdf(self, pagina: int, total: int | None):
        self.statusBar().showMessage(f"Generando PDF: página {pagina}" + (f" de {total}…" if total else "…"))
        QApplication.processEvents()

    # ------------------------------------------------------------ copias de seguridad

    def copia_manual(self, destino: str | None = None):
        if destino is None:
            nombre = f"LibriDomus_copia_{date.today():%Y%m%d}.zip"
            destino, _ = QFileDialog.getSaveFileName(self, "Guardar copia de seguridad", nombre, "ZIP (*.zip)")
            if not destino:
                return
        try:
            with comun.ocupado(self, "Haciendo la copia de seguridad…"):
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
            with comun.ocupado(self, "Comprobando y restaurando la copia…"):
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
        for accion in (self.acc_editar, self.acc_mover, self.acc_prestar, self.acc_devolver):
            menu.addAction(accion)
        menu.addSeparator()
        menu.addAction(self.acc_borrar)
        menu.exec(self.tabla.viewport().mapToGlobal(posicion))
