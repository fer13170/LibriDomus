"""Utilidades comunes de las pruebas: cada prueba usa una carpeta de datos temporal."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # las pruebas de interfaz no abren ventanas


@pytest.fixture(autouse=True)
def carpeta_datos(tmp_path, monkeypatch):
    carpeta = tmp_path / "datos"
    monkeypatch.setenv("LIBRIDOMUS_DATOS", str(carpeta))
    return carpeta


@pytest.fixture(autouse=True)
def cerrar_ventanas():
    """Tras cada prueba se destruyen las ventanas creadas: si no, siguen conectadas a los
    cambios de tema y cada prueba se vuelve más lenta que la anterior."""
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for ventana in app.topLevelWidgets():
        ventana.close()
        ventana.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def con(carpeta_datos):
    from libridomus.datos import conexion

    conexion_bd = conexion.abrir()
    yield conexion_bd
    conexion_bd.close()
