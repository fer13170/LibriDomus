"""Alta masiva: registrar muchos elementos seguidos en la misma ubicación.

Se fija la ubicación y el tipo; cada Intro guarda y deja el formulario listo para el siguiente.
"""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
                               QVBoxLayout)

from ..datos import elementos, tipos
from ..datos.elementos import Elemento, ErrorElemento
from ..servicios import configuracion, isbn, portadas
from ..servicios.isbn import DatosLibro
from ..servicios.portadas import ErrorPortada
from . import autocompletar, comun, tema
from .ficha_elemento import completador
from .selector_ubicacion import CampoUbicacion

# Tipos en los que normalmente hay código de barras (ISBN / EAN).
TIPOS_CON_CODIGO = {"Libro", "Revista / Cómic", "Disco", "Película", "Videojuego", "Partitura"}


class AltaMasiva(QDialog):
    def __init__(self, con: sqlite3.Connection, ubicacion_id: int | None = None, tipo_id: int | None = None,
                 parent=None):
        super().__init__(parent)
        self.con = con
        self.tipos = tipos.listar(con, con_campos=False)
        self.creados: list[int] = []
        self.sin_ubicacion_aceptado = False
        self.setWindowTitle("Alta masiva")
        self.resize(tema.px(900), tema.px(560))

        # --- lo que se mantiene fijo
        self.ubicacion = CampoUbicacion(con)
        self.ubicacion.establecer(ubicacion_id)
        self.tipo = QComboBox()
        for t in self.tipos:
            self.tipo.addItem(tema.icono(t.icono or "package", "primario"), t.nombre, t.id)
        if tipo_id is not None:
            self.tipo.setCurrentIndex(max(0, self.tipo.findData(tipo_id)))
        self.usar_codigo = QCheckBox("Empezar cada alta por el ISBN / EAN")
        fijos = QFormLayout()
        fijos.addRow("Guardar en:", self.ubicacion)
        fijos.addRow("Tipo:", self.tipo)
        fijos.addRow("", self.usar_codigo)
        grupo_fijos = QGroupBox("Para todos los elementos de esta sesión")
        grupo_fijos.setLayout(fijos)

        # --- lo que cambia en cada alta
        self.identificador = QLineEdit(placeholderText="ISBN / EAN (opcional)")
        self.titulo = QLineEdit()
        self.personas = QLineEdit(placeholderText="Varias personas separadas por ;")
        self.personas.setCompleter(completador(elementos.nombres_personas(con), self.personas))
        self.anio = QSpinBox()
        self.anio.setRange(0, 9999)
        self.anio.setSpecialValueText("—")
        self.anio.setMaximumWidth(100)
        self.etiquetas = QLineEdit(placeholderText="Separadas por comas (se mantienen entre altas)")
        self.etiquetas.setCompleter(completador(elementos.nombres_etiquetas(con), self.etiquetas))
        self.estado = QComboBox()
        self.estado.addItems(["", *elementos.ESTADOS])
        self.etiqueta_personas = QLabel()
        self.estado_consulta = QLabel()
        self.estado_consulta.setWordWrap(True)
        self.datos_isbn: DatosLibro | None = None
        variables = QFormLayout()
        variables.addRow("Identificador:", self.identificador)
        variables.addRow("Título *:", self.titulo)
        variables.addRow(self.etiqueta_personas, self.personas)
        variables.addRow("Año:", self.anio)
        variables.addRow("Etiquetas:", self.etiquetas)
        variables.addRow("Conservación:", self.estado)
        if not configuracion.modo_avanzado():  # modo sencillo: lo justo para ir rápido
            for w in (self.etiquetas, self.estado):
                variables.setRowVisible(w, False)
        self.form_variables = variables
        self.boton_guardar = QPushButton("Guardar y siguiente  (Intro)")
        self.boton_guardar.setDefault(True)
        variables.addRow("", self.boton_guardar)
        variables.addRow("", self.estado_consulta)
        grupo_variables = QGroupBox("Elemento")
        grupo_variables.setLayout(variables)

        # --- lista de lo registrado
        self.lista = QListWidget()
        self.contador = QLabel("0 elementos registrados en esta sesión")
        self.boton_deshacer = QPushButton("Deshacer el último")
        self.boton_deshacer.setEnabled(False)
        derecha = QVBoxLayout()
        derecha.addWidget(self.contador)
        derecha.addWidget(self.lista)
        derecha.addWidget(self.boton_deshacer)

        izquierda = QVBoxLayout()
        izquierda.addWidget(grupo_fijos)
        izquierda.addWidget(grupo_variables)
        izquierda.addStretch()
        cuerpo = QHBoxLayout()
        cuerpo.addLayout(izquierda, 3)
        cuerpo.addLayout(derecha, 2)
        cerrar = QPushButton("Terminar")
        cerrar.setAutoDefault(False)
        pie = QHBoxLayout()
        pie.addStretch()
        pie.addWidget(cerrar)
        capa = QVBoxLayout(self)
        capa.addLayout(cuerpo)
        capa.addLayout(pie)

        self.boton_guardar.clicked.connect(self.guardar_y_siguiente)
        self.boton_deshacer.clicked.connect(self.deshacer_ultimo)
        cerrar.clicked.connect(self.accept)
        self.tipo.currentIndexChanged.connect(lambda _i: self._aplicar_tipo(cambiar_codigo=True))
        self.usar_codigo.toggled.connect(lambda _v: self._aplicar_tipo(cambiar_codigo=False))
        # Intro en el identificador consulta el ISBN y pasa al título.
        self.identificador.returnPressed.connect(self.al_intro_identificador)
        self.identificador.textEdited.connect(lambda _t: setattr(self, "datos_isbn", None))
        for w in (self.titulo, self.personas, self.etiquetas):
            w.returnPressed.connect(self.guardar_y_siguiente)
        self._aplicar_tipo(cambiar_codigo=True)

    def tipo_actual(self):
        return next(t for t in self.tipos if t.id == self.tipo.currentData())

    def _aplicar_tipo(self, cambiar_codigo: bool) -> None:
        t = self.tipo_actual()
        if cambiar_codigo:
            self.usar_codigo.blockSignals(True)
            self.usar_codigo.setChecked(t.nombre in TIPOS_CON_CODIGO)
            self.usar_codigo.blockSignals(False)
        self.form_variables.setRowVisible(0, self.usar_codigo.isChecked())
        rol = t.roles[0] if t.roles else "Persona"
        self.etiqueta_personas.setText(f"{rol}:")
        self.primer_campo().setFocus()

    def primer_campo(self) -> QLineEdit:
        return self.identificador if self.usar_codigo.isChecked() else self.titulo

    def al_intro_identificador(self) -> None:
        """Intro en el ISBN: si es válido se consulta por Internet; si no, se pasa al título."""
        texto_isbn = self.identificador.text().strip()
        if not texto_isbn or isbn.validar(texto_isbn) is None or not configuracion.obtener("consultar_isbn"):
            self.titulo.setFocus()
            return
        self.estado_consulta.setText("Buscando datos del ISBN…")

        def acabar(vigente: bool):
            # Si el usuario ya está con otro elemento, no se le mueve el cursor ni se toca nada.
            if vigente:
                self.estado_consulta.setText("")
                self.titulo.setFocus()

        autocompletar.consultar(self, texto_isbn, self.aplicar_datos_isbn, acabar,
                                texto_actual=self.identificador.text)

    def aplicar_datos_isbn(self, datos: DatosLibro) -> None:
        self.datos_isbn = datos
        if not self.titulo.text().strip():
            self.titulo.setText(datos.titulo + (f": {datos.subtitulo}" if datos.subtitulo else ""))
        if datos.autores and not self.personas.text().strip():
            self.personas.setText("; ".join(datos.autores))
        if datos.anio and not self.anio.value():
            self.anio.setValue(datos.anio)
        extra = [datos.editorial, str(datos.anio or ""), "con portada" if datos.portada else "sin portada"]
        self.estado_consulta.setText(f"Encontrado en {datos.fuente}: " + " · ".join(x for x in extra if x))

    def _valores_extra(self, tipo_id: int) -> dict[int, str]:
        """Editorial y páginas obtenidas por ISBN, si el tipo tiene esos campos."""
        if not self.datos_isbn:
            return {}
        disponibles = {"editorial": self.datos_isbn.editorial, "paginas": str(self.datos_isbn.paginas or "")}
        return {c.id: disponibles[c.clave] for c in tipos.campos(self.con, tipo_id)
                if c.clave in disponibles and disponibles[c.clave]}

    def guardar_y_siguiente(self) -> bool:
        if self.ubicacion.valor() is None and not self.sin_ubicacion_aceptado:
            if not comun.confirmar(self, "No has elegido ubicación. ¿Guardar sin ubicación?"):
                return False
            self.sin_ubicacion_aceptado = True  # solo se pregunta una vez por sesión
        t = self.tipo_actual()
        rol = t.roles[0] if t.roles else "Persona"
        e = Elemento(
            tipo_id=t.id,
            titulo=self.titulo.text(),
            identificador=self.identificador.text() if self.usar_codigo.isChecked() else "",
            anio=self.anio.value() or None,
            personas=[(n, rol) for n in self.personas.text().split(";")],
            etiquetas=self.etiquetas.text().split(","),
            estado=self.estado.currentText(),
            ubicacion_id=self.ubicacion.valor(),
            valores=self._valores_extra(t.id),
            idioma=self.datos_isbn.idioma if self.datos_isbn else "",
        )
        repetidos = elementos.buscar_por_identificador(self.con, e.identificador)
        if repetidos and not comun.confirmar(
                self, f"Ya hay {len(repetidos)} elemento(s) con el identificador {e.identificador}. ¿Añadir otro?"):
            return False
        if self.datos_isbn and self.datos_isbn.portada:
            try:
                e.portada = portadas.guardar_desde_bytes(self.datos_isbn.portada)
            except ErrorPortada:
                e.portada = ""  # una portada defectuosa no impide el alta
        try:
            id_ = elementos.guardar(self.con, e)
        except ErrorElemento as error:
            portadas.borrar(e.portada)
            comun.error(self, str(error))
            self.titulo.setFocus()
            return False
        self.creados.append(id_)
        self._anotar(id_, e)
        # Se limpian los datos del elemento; tipo, ubicación, etiquetas y estado se mantienen.
        for w in (self.identificador, self.titulo, self.personas):
            w.clear()
        self.anio.setValue(0)
        self.datos_isbn = None
        self.estado_consulta.setText("")
        self.primer_campo().setFocus()
        return True

    def _anotar(self, id_: int, e: Elemento) -> None:
        texto_item = e.titulo
        if e.personas:
            texto_item += " — " + ", ".join(n for n, _ in e.personas)
        item = QListWidgetItem(texto_item)
        item.setData(Qt.ItemDataRole.UserRole, id_)
        self.lista.insertItem(0, item)
        self._actualizar_contador()

    def _actualizar_contador(self) -> None:
        self.contador.setText(f"{len(self.creados)} elementos registrados en esta sesión")
        self.boton_deshacer.setEnabled(bool(self.creados))

    def deshacer_ultimo(self) -> None:
        if not self.creados:
            return
        id_ = self.creados[-1]
        titulo = self.lista.item(0).text()
        if comun.confirmar(self, f"¿Borrar «{titulo}»?"):
            elementos.borrar(self.con, [id_])
            self.creados.pop()
            self.lista.takeItem(0)
            self._actualizar_contador()
