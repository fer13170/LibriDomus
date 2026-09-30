"""Perfila Ctrl+A sobre la base de 100.000 elementos creada por rendimiento_100k.py."""

import cProfile
import os
import pstats
import time

from comun_robustez import carpeta_datos

carpeta_datos("rendimiento_100k")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from libridomus.datos import conexion  # noqa: E402
from libridomus.interfaz import comun  # noqa: E402

comun.preparar_aplicacion(app)
from libridomus.interfaz.ventana_principal import VentanaPrincipal  # noqa: E402

v = VentanaPrincipal(conexion.abrir())
v.resize(1400, 850)
v.show()
app.processEvents()
for vuelta in range(2):
    inicio = time.perf_counter()
    v.tabla.selectAll()
    t_sel = time.perf_counter() - inicio
    app.processEvents()
    t_total = time.perf_counter() - inicio
    print(f"vuelta {vuelta + 1}: selectAll {t_sel:.2f} s; con repintado {t_total:.2f} s")
    v.tabla.clearSelection()
    app.processEvents()

perfil = cProfile.Profile()
perfil.enable()
v.tabla.selectAll()
app.processEvents()
perfil.disable()
pstats.Stats(perfil).sort_stats("tottime").print_stats(8)
