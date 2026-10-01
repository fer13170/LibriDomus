"""Panel lateral derecho: ficha resumida del elemento seleccionado y acciones rápidas."""

import html
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from ..datos import elementos, tipos, ubicaciones
from ..servicios import portadas
from . import comun, tema


def _limpiar(capa) -> None:
    while capa.count():
        item = capa.takeAt(0)
        widget = item.widget()
        if widget:
            # Se oculta y se desengancha ya: deleteLater tarda un ciclo y dejaría restos pintados.
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout():
            _limpiar(item.layout())


def _etiqueta(texto: str, nombre: str = "", ajustar: bool = True, seleccionable: bool = True,
              html_propio: bool = False) -> QLabel:
    """Etiqueta de texto PLANO: lo que escribe el usuario nunca se interpreta como HTML.
    ``html_propio`` solo para textos que construye el programa con los datos ya escapados."""
    e = QLabel(texto)
    e.setTextFormat(Qt.TextFormat.RichText if html_propio else Qt.TextFormat.PlainText)
    if nombre:
        e.setObjectName(nombre)
    e.setWordWrap(ajustar)
    if seleccionable:
        e.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return e


class PanelDetalle(QWidget):
    editar = Signal()
    mover = Signal()
    prestar = Signal()
    devolver = Signal()
    borrar = Signal()
    ir_a_ubicacion = Signal(int)

    def __init__(self, con: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.con = con
        self.setObjectName("panel_detalle")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(tema.px(290))
        self.setMaximumWidth(tema.px(460))
        self.contenido = QWidget()
        self.capa = QVBoxLayout(self.contenido)
        self.capa.setContentsMargins(tema.px(18), tema.px(18), tema.px(18), tema.px(18))
        self.capa.setSpacing(tema.px(10))
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(self.contenido)
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        principal.addWidget(desplazable)
        self.ids: list[int] = []
        self.mostrar([])

    # ------------------------------------------------------------ contenido

    def mostrar(self, ids: list[int]) -> None:
        self.ids = list(ids)
        _limpiar(self.capa)
        if not ids:
            self._vacio()
        elif len(ids) > 1:
            self._varios(len(ids))
        else:
            e = elementos.obtener(self.con, ids[0])
            self._uno(e) if e else self._vacio()
        self.capa.addStretch()

    def refrescar(self) -> None:
        self.mostrar(self.ids)

    def _vacio(self) -> None:
        icono = QLabel()
        icono.setPixmap(tema.icono("book-open", "borde_fuerte", tema.px(48)).pixmap(tema.px(48)))
        icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.capa.addSpacing(tema.px(40))
        self.capa.addWidget(icono)
        mensaje = _etiqueta("Selecciona un elemento de la lista para ver aquí su ficha.", "suave", seleccionable=False)
        mensaje.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.capa.addWidget(mensaje)

    def _varios(self, n: int) -> None:
        self.capa.addWidget(_etiqueta(f"{n} elementos seleccionados", "titulo_panel"))
        self.capa.addWidget(_etiqueta("Puedes moverlos, prestarlos o borrarlos a la vez. "
                                      "También puedes arrastrarlos a una ubicación del árbol.", "suave"))
        self.capa.addLayout(self._botones(varios=True))

    def _uno(self, e: elementos.Elemento) -> None:
        tipo = tipos.obtener(self.con, e.tipo_id)

        # Portada o icono grande del tipo
        portada = QLabel()
        portada.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ruta = portadas.ruta(e.portada)
        if ruta:
            imagen = QPixmap(str(ruta))
            portada.setPixmap(imagen.scaled(tema.px(170), tema.px(230), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        else:
            marco = QFrame(objectName="portada")
            marco.setFixedSize(tema.px(120), tema.px(150))
            capa_marco = QVBoxLayout(marco)
            dibujo = QLabel()
            dibujo.setPixmap(tema.icono(tipo.icono or "package", "borde_fuerte", tema.px(44)).pixmap(tema.px(44)))
            dibujo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            capa_marco.addWidget(dibujo)
            portada = marco
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(portada)
        fila.addStretch()
        self.capa.addLayout(fila)

        # Tipo, título y personas
        chip = QHBoxLayout()
        chip.setSpacing(tema.px(6))
        icono_tipo = QLabel()
        icono_tipo.setPixmap(tema.icono(tipo.icono or "package", "primario", tema.px(16)).pixmap(tema.px(16)))
        chip.addWidget(icono_tipo)
        chip.addWidget(_etiqueta(tipo.nombre.upper(), "encabezado", ajustar=False))
        chip.addStretch()
        self.capa.addLayout(chip)
        self.capa.addWidget(_etiqueta(e.titulo, "titulo_panel"))
        if e.subtitulo:
            self.capa.addWidget(_etiqueta(e.subtitulo, "suave"))
        if e.personas:
            texto = "<br>".join(f"{html.escape(n)} <span style='color:{tema.color('texto_suave')}'>"
                                f"· {html.escape(r)}</span>" for n, r in e.personas)
            self.capa.addWidget(_etiqueta(texto, html_propio=True))
        if e.categorias:
            self.capa.addWidget(_etiqueta(" · ".join(e.categorias), "categoria"))

        # Préstamo destacado
        if e.prestado_a:
            aviso = _etiqueta(f"Prestado a <b>{html.escape(e.prestado_a)}</b>"
                              + (f" desde el {html.escape(e.fecha_prestamo)}" if e.fecha_prestamo else ""), "aviso",
                              html_propio=True)
            self.capa.addWidget(aviso)

        # Ubicación (enlace que lleva al árbol)
        self.capa.addWidget(_etiqueta("UBICACIÓN", "encabezado", seleccionable=False))
        if e.ubicacion_id:
            # Enlace (que se ajusta a varias líneas) para saltar a la ubicación en el árbol.
            ruta = html.escape(ubicaciones.ruta_texto(self.con, e.ubicacion_id))
            enlace = _etiqueta(f"<a href='#' style='color:{tema.color('primario')}; text-decoration:none'>"
                               f"{ruta}</a>", seleccionable=False, html_propio=True)
            enlace.setToolTip("Mostrar esta ubicación en el árbol")
            enlace.linkActivated.connect(lambda _h: self.ir_a_ubicacion.emit(e.ubicacion_id))
            fila_ruta = QHBoxLayout()
            pin = QLabel()
            pin.setPixmap(tema.icono("map-pin", "primario", tema.px(16)).pixmap(tema.px(16)))
            fila_ruta.addWidget(pin, 0, Qt.AlignmentFlag.AlignTop)
            fila_ruta.addWidget(enlace, 1)
            self.capa.addLayout(fila_ruta)
            u = ubicaciones.obtener(self.con, e.ubicacion_id)
            self.capa.addWidget(_etiqueta(f"Código {u.codigo}", "suave"))
        else:
            self.capa.addWidget(_etiqueta("Sin ubicación", "suave"))

        # Datos
        datos = []
        if e.anio:
            datos.append(("Año", str(e.anio)))
        if e.fecha_desde or e.fecha_hasta:
            datos.append(("Periodo", " – ".join(x for x in (e.fecha_desde, e.fecha_hasta) if x)))
        if e.lugar_evento:
            datos.append(("Lugar / evento", e.lugar_evento))
        if e.identificador:
            datos.append(("Identificador", e.identificador))
        if e.idioma:
            datos.append(("Idioma", e.idioma))
        if e.estado:
            datos.append(("Conservación", e.estado))
        if e.valoracion:
            datos.append(("Valoración", "★" * e.valoracion + "☆" * (5 - e.valoracion)))
        datos.append((tipo.verbo_consumo, "Sí" if e.consumido else "No"))
        for campo in tipo.campos:
            valor = e.valores.get(campo.id, "")
            if valor and not campo.oculto:
                datos.append((campo.etiqueta, valor))
        self.capa.addWidget(_etiqueta("DATOS", "encabezado", seleccionable=False))
        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(tema.px(12))
        rejilla.setVerticalSpacing(tema.px(4))
        for n, (nombre, valor) in enumerate(datos):
            rejilla.addWidget(_etiqueta(nombre, "suave", ajustar=False, seleccionable=False), n, 0,
                              Qt.AlignmentFlag.AlignTop)
            rejilla.addWidget(_etiqueta(valor), n, 1)
        rejilla.setColumnStretch(1, 1)
        self.capa.addLayout(rejilla)

        if e.etiquetas:
            fila_etiquetas = QHBoxLayout()
            fila_etiquetas.setSpacing(tema.px(4))
            for nombre in e.etiquetas[:8]:
                fila_etiquetas.addWidget(_etiqueta(nombre, "chip", ajustar=False, seleccionable=False))
            fila_etiquetas.addStretch()
            self.capa.addLayout(fila_etiquetas)
        if e.notas:
            self.capa.addWidget(_etiqueta("NOTAS", "encabezado", seleccionable=False))
            self.capa.addWidget(_etiqueta(e.notas))

        self.capa.addSpacing(tema.px(6))
        self.capa.addLayout(self._botones(varios=False, prestado=bool(e.prestado_a)))

    def _botones(self, varios: bool, prestado: bool = False) -> QVBoxLayout:
        capa = QVBoxLayout()
        capa.setSpacing(tema.px(6))
        if not varios:
            b = comun.boton("Editar ficha", "pencil", "primario")
            b.clicked.connect(self.editar.emit)
            capa.addWidget(b)
        fila = QHBoxLayout()
        b = comun.boton("Mover", "folder-input")
        b.clicked.connect(self.mover.emit)
        fila.addWidget(b)
        if prestado:
            b = comun.boton("Devuelto", "undo-2")
            b.clicked.connect(self.devolver.emit)
        else:
            b = comun.boton("Prestar", "handshake")
            b.clicked.connect(self.prestar.emit)
        fila.addWidget(b)
        capa.addLayout(fila)
        b = comun.boton("Borrar", "trash-2", "peligro")
        b.clicked.connect(self.borrar.emit)
        capa.addWidget(b)
        return capa
