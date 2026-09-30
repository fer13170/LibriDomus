"""Sobre la base de 100.000 elementos ya creada por rendimiento_100k.py: memoria y latencia de un alta suelta."""

import os
import statistics
import time

from comun_robustez import carpeta_datos, medir, memoria_mb

datos = carpeta_datos("rendimiento_100k")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
print("Memoria al arrancar Python + Qt: %.0f MB" % memoria_mb()[0])
from libridomus.datos import conexion, elementos, tipos, ubicaciones  # noqa: E402
from libridomus.datos.elementos import Elemento  # noqa: E402
from libridomus.interfaz import comun  # noqa: E402

comun.preparar_aplicacion(app)
con = medir("Abrir la base de datos (arranque)", conexion.abrir)
print("   elementos:", con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0])
from libridomus.interfaz.ventana_principal import VentanaPrincipal  # noqa: E402

v = medir("Abrir la ventana principal con toda la colección", lambda: VentanaPrincipal(con))
v.resize(1400, 850)
v.show()
app.processEvents()
print("Memoria con la ventana abierta: %.0f MB (pico %.0f MB)" % memoria_mb())

libro = tipos.por_nombre(con, "Libro").id
balda = [u.id for u in ubicaciones.todas(con)][-1]
tiempos = []
for i in range(30):
    inicio = time.perf_counter()
    elementos.guardar(con, Elemento(tipo_id=libro, titulo=f"Alta suelta {i}", ubicacion_id=balda,
                                    personas=[("Autora Nueva", "Autor")], etiquetas=["nueva"]))
    tiempos.append(time.perf_counter() - inicio)
print(f"Guardar UN elemento con 100.000 en la colección: mediana {statistics.median(tiempos) * 1000:.0f} ms, "
      f"máximo {max(tiempos) * 1000:.0f} ms")
inicio = time.perf_counter()
v.refrescar_todo()
print(f"Refrescar la ventana después de guardar (lo que ve el usuario): {time.perf_counter() - inicio:.2f} s")
