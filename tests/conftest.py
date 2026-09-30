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
    monkeypatch.setenv("BV_DATOS", str(carpeta))
    return carpeta


@pytest.fixture
def con(carpeta_datos):
    from bibliotecario.datos import conexion

    conexion_bd = conexion.abrir()
    yield conexion_bd
    conexion_bd.close()
