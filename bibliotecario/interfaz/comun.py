"""Utilidades de interfaz compartidas por todas las ventanas."""

from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
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
