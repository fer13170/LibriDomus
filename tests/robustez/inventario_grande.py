"""Inventario PDF de toda la casa sobre la base de 100.000 elementos (tiempo y memoria)."""

import os
import time

from comun_robustez import carpeta_datos, memoria_mb

datos = carpeta_datos("rendimiento_100k")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from libridomus.datos import conexion  # noqa: E402
from libridomus.servicios import informes  # noqa: E402

con = conexion.abrir()
print("Memoria antes: %.0f MB" % memoria_mb()[0])
inicio = time.perf_counter()
n = informes.inventario(con, None, datos / "inventario_completo.pdf")
print(f"Inventario de {n:,} elementos: {time.perf_counter() - inicio:.1f} s; memoria actual %.0f MB, pico %.0f MB"
      % memoria_mb())
documento = QPdfDocument()
documento.load(str(datos / "inventario_completo.pdf"))
print(f"Páginas: {documento.pageCount()}; tamaño: {os.path.getsize(datos / 'inventario_completo.pdf') / 2**20:.1f} MB")
salida = os.environ.get("CAPTURAS")
if salida:
    for pagina in (0, 60):
        documento.render(pagina, QSize(1240, 1754)).save(os.path.join(salida, f"inventario_p{pagina + 1}.png"))
