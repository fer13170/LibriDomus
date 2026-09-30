"""Utilidades de interfaz compartidas por todas las ventanas."""

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (QLibraryInfo, QLocale, QObject, QProcess, QRunnable, QThreadPool,
                            QTranslator, Signal, Slot)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from .. import NOMBRE

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"

ESTILO = """
QToolBar { spacing: 6px; padding: 4px; }
QLineEdit#busqueda { padding: 4px 8px; font-size: 11pt; min-width: 320px; }
QLabel#ruta { color: palette(link); }
QLabel#titulo_seccion { font-weight: bold; font-size: 11pt; }
QGroupBox { font-weight: bold; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QTreeWidget, QTableView { font-size: 10pt; }
"""


def preparar_aplicacion(app: QApplication) -> None:
    """Estilo, fuente, icono y traducción al español de los textos propios de Qt."""
    app.setApplicationName(NOMBRE)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(ESTILO)
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


def error(padre: QWidget | None, mensaje: str) -> None:
    QMessageBox.warning(padre, NOMBRE, mensaje)


def aviso(padre: QWidget | None, mensaje: str) -> None:
    QMessageBox.information(padre, NOMBRE, mensaje)


def confirmar(padre: QWidget | None, mensaje: str) -> bool:
    respuesta = QMessageBox.question(
        padre, NOMBRE, mensaje,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return respuesta == QMessageBox.StandardButton.Yes
