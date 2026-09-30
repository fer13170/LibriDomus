"""Utilidades de interfaz compartidas por todas las ventanas."""

import sys
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import (QLibraryInfo, QLocale, QObject, QProcess, QRunnable, QThreadPool,
                            QTranslator, Qt, Signal, Slot)
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget

from .. import NOMBRE

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"


def preparar_aplicacion(app: QApplication) -> None:
    """Tema, escala, fuente, icono y traducción al español de los textos propios de Qt."""
    from ..servicios import configuracion
    from . import tema

    app.setApplicationName(NOMBRE)
    ajustes = configuracion.cargar()
    tema.aplicar(app, ajustes["tema"], ajustes["escala"], ajustes["fuente"])
    app.setWindowIcon(icono_app())
    traductor = QTranslator(app)
    if traductor.load(QLocale("es_ES"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(traductor)
    QLocale.setDefault(QLocale("es_ES"))


class _Senales(QObject):
    """Vive en el hilo de la interfaz: al conectar las señales a sus métodos, Qt entrega
    los resultados del hilo de trabajo en el hilo de la interfaz (conexión en cola)."""

    terminado = Signal(object)
    fallido = Signal(object)

    def __init__(self, al_terminar, al_fallar):
        super().__init__()
        self.al_terminar, self.al_fallar = al_terminar, al_fallar
        self.terminado.connect(self._ok)
        self.fallido.connect(self._ko)

    @Slot(object)
    def _ok(self, valor):
        _tareas_vivas.discard(self)
        self.al_terminar(valor)

    @Slot(object)
    def _ko(self, error):
        _tareas_vivas.discard(self)
        self.al_fallar(error)


class _Tarea(QRunnable):
    def __init__(self, funcion, senales):
        super().__init__()
        self.funcion, self.senales = funcion, senales

    def run(self):
        try:
            resultado = self.funcion()
        except Exception as error:  # noqa: BLE001 - el error se entrega a la interfaz
            self.senales.fallido.emit(error)
        else:
            self.senales.terminado.emit(resultado)


_tareas_vivas: set = set()


def en_segundo_plano(funcion: Callable[[], object], al_terminar: Callable[[object], None],
                     al_fallar: Callable[[Exception], None]) -> None:
    """Ejecuta ``funcion`` en otro hilo (p. ej. una consulta a Internet) sin congelar la ventana.

    ``al_terminar`` y ``al_fallar`` se llaman después en el hilo de la interfaz.
    Las pruebas sustituyen esta función por una versión que lo hace todo en el acto.
    """
    senales = _Senales(al_terminar, al_fallar)
    _tareas_vivas.add(senales)  # evita que Python lo destruya antes de recibir la respuesta
    QThreadPool.globalInstance().start(_Tarea(funcion, senales))


def reiniciar() -> None:
    """Vuelve a lanzar el programa y cierra el actual (tras restaurar una copia)."""
    if getattr(sys, "frozen", False):
        programa, argumentos = sys.executable, sys.argv[1:]
    else:
        programa, argumentos = sys.executable, sys.argv
    QProcess.startDetached(programa, argumentos)
    QApplication.quit()


def icono_app() -> QIcon:
    return QIcon(str(RECURSOS / "icono.png"))


def boton(texto: str, icono: str = "", tipo: str = "", tooltip: str = "") -> QPushButton:
    """Botón con icono del tema. ``tipo``: '' (normal), 'primario', 'peligro', 'plano' o 'enlace'."""
    from . import tema

    b = QPushButton(texto)
    if tipo:
        b.setObjectName(tipo)
    if icono:
        tono = {"primario": "primario_texto", "peligro": "peligro", "enlace": "primario"}.get(tipo, "texto")
        b.setIcon(tema.icono(icono, tono))
        b.setProperty("icono_tema", (icono, tono))  # para recolorearlo si cambia el tema
    if tooltip:
        b.setToolTip(tooltip)
    b.setAutoDefault(False)
    return b


def recolorear_botones(raiz: QWidget) -> None:
    """Tras cambiar de tema, vuelve a pintar los iconos de los botones creados con ``boton``."""
    from . import tema

    for b in raiz.findChildren(QPushButton):
        datos = b.property("icono_tema")
        if datos:
            b.setIcon(tema.icono(*datos))


def _mensaje(padre, icono, texto: str, botones, defecto=None) -> QMessageBox:
    """Cuadro de mensaje con texto SIEMPRE plano: los datos del usuario (títulos con «<», etc.)
    nunca se interpretan como HTML."""
    caja = QMessageBox(icono, NOMBRE, texto, botones, padre)
    caja.setTextFormat(Qt.TextFormat.PlainText)
    if defecto is not None:
        caja.setDefaultButton(defecto)
    return caja


def error(padre: QWidget | None, mensaje: str) -> None:
    _mensaje(padre, QMessageBox.Icon.Warning, mensaje, QMessageBox.StandardButton.Ok).exec()


def aviso(padre: QWidget | None, mensaje: str) -> None:
    _mensaje(padre, QMessageBox.Icon.Information, mensaje, QMessageBox.StandardButton.Ok).exec()


def confirmar(padre: QWidget | None, mensaje: str) -> bool:
    caja = _mensaje(padre, QMessageBox.Icon.Question, mensaje,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
    return caja.exec() == QMessageBox.StandardButton.Yes


def preguntar(texto: str, detalle: str, opciones: list[str], padre: QWidget | None = None) -> int | None:
    """Pregunta con botones propios. Devuelve el índice de la opción elegida (None si se cierra)."""
    caja = _mensaje(padre, QMessageBox.Icon.Warning, texto, QMessageBox.StandardButton.NoButton)
    caja.setInformativeText(detalle)
    botones = [caja.addButton(o, QMessageBox.ButtonRole.AcceptRole if i == 0 else QMessageBox.ButtonRole.RejectRole)
               for i, o in enumerate(opciones)]
    caja.setDefaultButton(botones[0])
    caja.exec()
    pulsado = caja.clickedButton()
    return botones.index(pulsado) if pulsado in botones else None


@contextmanager
def ocupado(ventana: QWidget | None = None, mensaje: str = "Trabajando…"):
    """Cursor de espera y mensaje en la barra de estado durante una operación larga."""
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    barra = ventana.statusBar() if ventana is not None and hasattr(ventana, "statusBar") else None
    if barra is not None:
        barra.showMessage(mensaje)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()
        if barra is not None:
            barra.clearMessage()
