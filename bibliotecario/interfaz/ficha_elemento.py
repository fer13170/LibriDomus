"""Ficha de un elemento: alta y edición. El formulario se adapta al tipo elegido."""

import sqlite3

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..datos import elementos, tipos
from ..datos.elementos import Elemento, ErrorElemento
from ..datos.tipos import Campo, TipoElemento
from . import comun
from .selector_ubicacion import CampoUbicacion

VALIDADOR_NUMERO = QRegularExpression(r"^-?\d+([.,]\d+)?$")
VALIDADOR_FECHA = QRegularExpression(r"^\d{0,4}(-\d{0,2}(-\d{0,2})?)?$")
AYUDA_FECHA = "AAAA, AAAA-MM o AAAA-MM-DD"


def completador(palabras: list[str], parent=None) -> QCompleter:
    c = QCompleter(palabras, parent)
    c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    c.setFilterMode(Qt.MatchFlag.MatchContains)
    return c


class ListaPersonas(QWidget):
    """Filas 'nombre + rol' con botones para añadir y quitar."""

    def __init__(self, nombres: list[str], parent=None):
        super().__init__(parent)
        self.nombres = nombres
        self.roles: list[str] = []
        self.filas: list[tuple[QWidget, QLineEdit, QComboBox]] = []
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(0, 0, 0, 0)
        self.boton_anadir = QPushButton("➕ Añadir persona")
        self.boton_anadir.clicked.connect(lambda: self.anadir("", "").setFocus())
        self.capa.addWidget(self.boton_anadir, alignment=Qt.AlignmentFlag.AlignLeft)

    def establecer_roles(self, roles: list[str]) -> None:
        self.roles = roles
        for _, _, rol in self.filas:
            actual = rol.currentText()
            rol.clear()
            rol.addItems(roles)
            rol.setCurrentText(actual or (roles[0] if roles else ""))

    def anadir(self, nombre: str, rol: str) -> QLineEdit:
        fila = QWidget()
        capa = QHBoxLayout(fila)
        capa.setContentsMargins(0, 0, 0, 0)
        campo_nombre = QLineEdit(nombre, placeholderText="Nombre")
        campo_nombre.setCompleter(completador(self.nombres, campo_nombre))
        campo_rol = QComboBox(editable=True)
        campo_rol.addItems(self.roles)
        campo_rol.setCurrentText(rol or (self.roles[0] if self.roles else ""))
        campo_rol.setMinimumWidth(130)
        quitar = QPushButton("✕")
        quitar.setFixedWidth(28)
        quitar.setToolTip("Quitar")
        capa.addWidget(campo_nombre, 1)
        capa.addWidget(campo_rol)
        capa.addWidget(quitar)
        entrada = (fila, campo_nombre, campo_rol)
        self.filas.append(entrada)
        self.capa.insertWidget(self.capa.count() - 1, fila)
        quitar.clicked.connect(lambda: self._quitar(entrada))
        return campo_nombre

    def _quitar(self, entrada):
        self.filas.remove(entrada)
        entrada[0].deleteLater()

    def establecer(self, personas: list[tuple[str, str]]) -> None:
        for entrada in list(self.filas):
            self._quitar(entrada)
        for nombre, rol in personas:
            self.anadir(nombre, rol)
        if not personas:
            self.anadir("", "")

    def valor(self) -> list[tuple[str, str]]:
        return [(n.text().strip(), r.currentText().strip()) for _, n, r in self.filas if n.text().strip()]


class EditorCampo:
    """Crea el control adecuado para un campo propio y lee/escribe su valor como texto."""

    def __init__(self, campo: Campo):
        self.campo = campo
        t = campo.tipo_dato
        if t == "texto_largo":
            self.widget = QPlainTextEdit()
            self.widget.setMaximumHeight(90)
        elif t == "lista":
            self.widget = QComboBox()
            self.widget.addItems(["", *campo.opciones])
        elif t == "si_no":
            self.widget = QCheckBox()
        else:
            self.widget = QLineEdit()
            if t == "numero":
                self.widget.setValidator(QRegularExpressionValidator(VALIDADOR_NUMERO, self.widget))
            elif t == "fecha":
                self.widget.setPlaceholderText(AYUDA_FECHA)
                self.widget.setValidator(QRegularExpressionValidator(VALIDADOR_FECHA, self.widget))

    def establecer(self, valor: str) -> None:
        w = self.widget
        if isinstance(w, QPlainTextEdit):
            w.setPlainText(valor)
        elif isinstance(w, QComboBox):
            if valor and w.findText(valor) < 0:
                w.addItem(valor)  # valor antiguo que ya no está entre las opciones
            w.setCurrentText(valor)
        elif isinstance(w, QCheckBox):
            w.setChecked(valor == "Sí")
        else:
            w.setText(valor)

    def valor(self) -> str:
        w = self.widget
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        if isinstance(w, QCheckBox):
            return "Sí" if w.isChecked() else ""
        return w.text().strip()


class FichaElemento(QDialog):
    guardado = Signal(int)

    def __init__(self, con: sqlite3.Connection, elemento_id: int | None = None, tipo_id: int | None = None,
                 ubicacion_id: int | None = None, parent=None):
        super().__init__(parent)
        self.con = con
        self.tipos: list[TipoElemento] = tipos.listar(con)
        self.original: Elemento | None = elementos.obtener(con, elemento_id) if elemento_id else None
        self.editores: dict[int, EditorCampo] = {}
        self.setWindowTitle("Editar elemento" if self.original else "Nuevo elemento")
        self.resize(720, 760)

        # --- tipo
        self.tipo = QComboBox()
        for t in self.tipos:
            self.tipo.addItem(f"{t.icono}  {t.nombre}", t.id)

        # --- general
        self.titulo = QLineEdit()
        self.subtitulo = QLineEdit()
        self.personas = ListaPersonas(elementos.nombres_personas(con))
        self.anio = QSpinBox()
        self.anio.setRange(0, 9999)
        self.anio.setSpecialValueText("—")
        self.anio.setMaximumWidth(100)
        self.identificador = QLineEdit(placeholderText="ISBN, EAN, ISSN…")
        self.idioma = QComboBox(editable=True)
        self.idioma.addItems(["", *elementos.idiomas_usados(con)])
        self.estado = QComboBox()
        self.estado.addItems(["", *elementos.ESTADOS])
        self.valoracion = QComboBox()
        self.valoracion.addItems(["—", "★", "★★", "★★★", "★★★★", "★★★★★"])
        self.consumido = QCheckBox()
        self.etiquetas = QLineEdit(placeholderText="Separadas por comas")
        self.etiquetas.setCompleter(completador(elementos.nombres_etiquetas(con), self.etiquetas))
        self.ubicacion = CampoUbicacion(con)

        general = QFormLayout()
        general.addRow("Título *", self.titulo)
        general.addRow("Subtítulo", self.subtitulo)
        general.addRow("Personas", self.personas)
        fila = QHBoxLayout()
        fila.addWidget(self.anio)
        fila.addWidget(QLabel("  Idioma"))
        fila.addWidget(self.idioma, 1)
        general.addRow("Año", fila)
        general.addRow("Identificador", self.identificador)
        fila = QHBoxLayout()
        fila.addWidget(self.estado, 1)
        fila.addWidget(QLabel("  Valoración"))
        fila.addWidget(self.valoracion)
        fila.addWidget(self.consumido)
        general.addRow("Conservación", fila)
        general.addRow("Etiquetas", self.etiquetas)
        self.grupo_general = QGroupBox("General")
        self.grupo_general.setLayout(general)

        ubic = QVBoxLayout()
        ubic.addWidget(self.ubicacion)
        self.grupo_ubicacion = QGroupBox("Ubicación")
        self.grupo_ubicacion.setLayout(ubic)

        # --- personal
        self.fecha_desde = QLineEdit(placeholderText=AYUDA_FECHA)
        self.fecha_hasta = QLineEdit(placeholderText=AYUDA_FECHA)
        for w in (self.fecha_desde, self.fecha_hasta):
            w.setValidator(QRegularExpressionValidator(VALIDADOR_FECHA, w))
        self.lugar_evento = QLineEdit(placeholderText="Por ejemplo: Boda de Ana, Sevilla")
        personal = QFormLayout()
        fila = QHBoxLayout()
        fila.addWidget(self.fecha_desde)
        fila.addWidget(QLabel(" hasta "))
        fila.addWidget(self.fecha_hasta)
        personal.addRow("Periodo desde", fila)
        personal.addRow("Lugar / evento", self.lugar_evento)
        self.grupo_personal = QGroupBox("Periodo, lugar y evento")
        self.grupo_personal.setLayout(personal)

        # --- campos propios
        self.form_campos = QFormLayout()
        self.grupo_campos = QGroupBox()
        self.grupo_campos.setLayout(self.form_campos)

        # --- notas
        self.notas = QPlainTextEdit()
        self.notas.setMinimumHeight(80)
        notas = QVBoxLayout()
        notas.addWidget(self.notas)
        self.grupo_notas = QGroupBox("Notas")
        self.grupo_notas.setLayout(notas)

        self.contenido = QVBoxLayout()
        cuerpo = QWidget()
        cuerpo.setLayout(self.contenido)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setWidget(cuerpo)

        # --- botones
        self.boton_guardar = QPushButton("Guardar")
        self.boton_guardar.setDefault(True)
        self.boton_guardar_nuevo = QPushButton("Guardar y nuevo")
        self.boton_cancelar = QPushButton("Cancelar")
        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(self.boton_guardar_nuevo)
        botones.addWidget(self.boton_guardar)
        botones.addWidget(self.boton_cancelar)

        cabecera = QHBoxLayout()
        cabecera.addWidget(QLabel("Tipo:"))
        cabecera.addWidget(self.tipo, 1)
        capa = QVBoxLayout(self)
        capa.addLayout(cabecera)
        capa.addWidget(desplazable, 1)
        capa.addLayout(botones)

        self.boton_guardar.clicked.connect(lambda: self.guardar() and self.accept())
        self.boton_guardar_nuevo.clicked.connect(self._guardar_y_nuevo)
        self.boton_cancelar.clicked.connect(self.reject)
        self.tipo.currentIndexChanged.connect(lambda _i: self._aplicar_tipo())

        self._cargar(tipo_id, ubicacion_id)

    # ------------------------------------------------------------ tipo

    def tipo_actual(self) -> TipoElemento:
        return next(t for t in self.tipos if t.id == self.tipo.currentData())

    def _aplicar_tipo(self) -> None:
        t = self.tipo_actual()
        anteriores = {e.campo.clave: e.valor() for e in self.editores.values()}
        while self.form_campos.rowCount():
            self.form_campos.removeRow(0)
        self.editores.clear()
        for campo in t.campos:
            if campo.oculto:
                continue
            editor = EditorCampo(campo)
            if anteriores.get(campo.clave):
                editor.establecer(anteriores[campo.clave])
            self.editores[campo.id] = editor
            self.form_campos.addRow(campo.etiqueta, editor.widget)
        self.grupo_campos.setTitle(f"Datos de {t.nombre.lower()}")
        self.grupo_campos.setVisible(bool(self.editores))
        self.personas.establecer_roles(t.roles)
        self.consumido.setText(t.verbo_consumo)
        # Los tipos personales (álbumes, carpetas...) muestran primero el periodo y el lugar.
        orden = [self.grupo_general]
        orden += [self.grupo_personal, self.grupo_campos] if t.personal else [self.grupo_campos, self.grupo_personal]
        orden += [self.grupo_ubicacion, self.grupo_notas]
        for grupo in orden:
            self.contenido.removeWidget(grupo)
        for grupo in orden:
            self.contenido.addWidget(grupo)

    # ------------------------------------------------------------ carga / lectura

    def _cargar(self, tipo_id: int | None, ubicacion_id: int | None) -> None:
        e = self.original
        tipo_inicial = e.tipo_id if e else (tipo_id or self.tipos[0].id)
        self.tipo.blockSignals(True)
        self.tipo.setCurrentIndex(max(0, self.tipo.findData(tipo_inicial)))
        self.tipo.blockSignals(False)
        self._aplicar_tipo()
        if e is None:
            self.personas.establecer([])
            self.ubicacion.establecer(ubicacion_id)
            self.boton_guardar_nuevo.setVisible(True)
            return
        self.boton_guardar_nuevo.setVisible(False)
        self.titulo.setText(e.titulo)
        self.subtitulo.setText(e.subtitulo)
        self.personas.establecer(e.personas)
        self.anio.setValue(e.anio or 0)
        self.identificador.setText(e.identificador)
        self.idioma.setCurrentText(e.idioma)
        self.estado.setCurrentText(e.estado)
        self.valoracion.setCurrentIndex(e.valoracion)
        self.consumido.setChecked(e.consumido)
        self.etiquetas.setText(", ".join(e.etiquetas))
        self.ubicacion.establecer(e.ubicacion_id)
        self.fecha_desde.setText(e.fecha_desde)
        self.fecha_hasta.setText(e.fecha_hasta)
        self.lugar_evento.setText(e.lugar_evento)
        self.notas.setPlainText(e.notas)
        for campo_id, editor in self.editores.items():
            editor.establecer(e.valores.get(campo_id, ""))

    def leer(self) -> Elemento:
        """Construye un Elemento con lo que hay en pantalla (conservando lo que la ficha no muestra)."""
        base = self.original
        e = Elemento(
            id=base.id if base else None,
            tipo_id=self.tipo.currentData(),
            titulo=self.titulo.text(),
            subtitulo=self.subtitulo.text().strip(),
            anio=self.anio.value() or None,
            fecha_desde=self.fecha_desde.text(),
            fecha_hasta=self.fecha_hasta.text(),
            idioma=self.idioma.currentText().strip(),
            estado=self.estado.currentText(),
            valoracion=self.valoracion.currentIndex(),
            consumido=self.consumido.isChecked(),
            identificador=self.identificador.text(),
            lugar_evento=self.lugar_evento.text().strip(),
            ubicacion_id=self.ubicacion.valor(),
            notas=self.notas.toPlainText().strip(),
            personas=self.personas.valor(),
            etiquetas=[x for x in self.etiquetas.text().split(",")],
            valores={campo_id: ed.valor() for campo_id, ed in self.editores.items()},
        )
        if base:
            e.portada, e.prestado_a, e.fecha_prestamo = base.portada, base.prestado_a, base.fecha_prestamo
        return e

    # ------------------------------------------------------------ guardar

    def guardar(self) -> bool:
        e = self.leer()
        repetidos = [i for i in elementos.buscar_por_identificador(self.con, e.identificador) if i != e.id]
        if repetidos:
            otro = elementos.obtener(self.con, repetidos[0])
            identificador = elementos.normalizar_identificador(e.identificador)
            if not comun.confirmar(self, f"Ya hay un elemento con el identificador {identificador}:\n"
                                         f"«{otro.titulo}».\n\n¿Guardar igualmente?"):
                return False
        try:
            id_ = elementos.guardar(self.con, e)
        except ErrorElemento as error:
            comun.error(self, str(error))
            return False
        self.original = elementos.obtener(self.con, id_)
        self.guardado.emit(id_)
        return True

    def _guardar_y_nuevo(self) -> None:
        if not self.guardar():
            return
        # Se mantiene el tipo y la ubicación para dar de alta el siguiente rápidamente.
        tipo_id, ubicacion_id = self.tipo.currentData(), self.ubicacion.valor()
        self.original = None
        for w in (self.titulo, self.subtitulo, self.identificador, self.etiquetas,
                  self.fecha_desde, self.fecha_hasta, self.lugar_evento):
            w.clear()
        self.notas.clear()
        self.anio.setValue(0)
        self.estado.setCurrentIndex(0)
        self.valoracion.setCurrentIndex(0)
        self.consumido.setChecked(False)
        for editor in self.editores.values():
            editor.establecer("")
        self._cargar(tipo_id, ubicacion_id)
        self.titulo.setFocus()
