"""Rendimiento con 100.000 elementos y 1.000 ubicaciones.

Uso:  .venv\\Scripts\\python tests\\robustez\\rendimiento_100k.py
"""

import os
import random
import shutil
import sys
import time

from comun_robustez import carpeta_datos, medir, memoria_mb

datos = carpeta_datos("rendimiento_100k")
shutil.rmtree(datos, ignore_errors=True)
datos.mkdir(parents=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from libridomus.datos import conexion, elementos, tipos, ubicaciones  # noqa: E402
from libridomus.datos.elementos import Elemento  # noqa: E402
from libridomus.interfaz import comun  # noqa: E402
from libridomus.servicios import busqueda, copias, etiquetas, informes  # noqa: E402
from libridomus.servicios.busqueda import Filtros  # noqa: E402

comun.preparar_aplicacion(app)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
random.seed(7)
con = conexion.abrir()
T = {f["nombre"]: f["id"] for f in con.execute("SELECT id, nombre FROM tipo_ubicacion")}

baldas = []


def crear_casa():
    with conexion.transaccion(con):
        for planta in ("SOT", "PB", "PA", "BUH"):
            p = ubicaciones.buscar_por_codigo(con, planta).id
            for h in range(6):
                hab = ubicaciones.crear(con, p, T["Habitación"], f"Habitación {h}")
                for e in range(8):
                    est = ubicaciones.crear(con, hab, T["Estantería"], f"Estantería {e}")
                    for b in range(4):
                        baldas.append(ubicaciones.crear(con, est, T["Balda"], f"Balda {b}"))


medir("Crear 993 ubicaciones", crear_casa)
tps = [t.id for t in tipos.listar(con)]
palabras = ("amor guerra historia casa sombra viaje noche mar tiempo ciudad vida muerte río luz sol libro "
            "jardín invierno verano camino puerta silencio memoria fuego agua tierra aire").split()
autores = [f"{n} {a}" for n in ("Ana", "Luis", "María", "José", "Carmen", "Pedro", "Lucía", "Javier", "Elena", "Pablo")
           for a in ("García", "Pérez", "López", "Martínez", "Sánchez", "Gómez", "Ruiz", "Díaz")]


def cargar():
    with conexion.transaccion(con):
        for i in range(N):
            elementos.guardar(con, Elemento(
                tipo_id=random.choice(tps), titulo=" ".join(random.sample(palabras, 3)).capitalize() + f" {i}",
                ubicacion_id=random.choice(baldas), anio=random.randint(1900, 2025),
                personas=[(random.choice(autores), "Autor")], etiquetas=[random.choice(palabras)],
                notas="Nota de prueba " * random.randint(0, 5)))


medir(f"Alta de {N:,} elementos (una transacción)", cargar)
print(f"   Tamaño BD: {os.path.getsize(datos / 'biblioteca.db') / 2**20:.1f} MB")

medir("Buscar todo sin filtros", lambda: len(busqueda.buscar(con, Filtros())))
n = medir("Buscar 'garc amor' (FTS)", lambda: len(busqueda.buscar(con, Filtros(texto="garc amor"))))
print(f"   resultados: {n}")
medir("Buscar 'a' (prefijo de 1 letra, muchos resultados)", lambda: len(busqueda.buscar(con, Filtros(texto="a"))))
medir("Buscar solo exclusión '-amor'", lambda: len(busqueda.buscar(con, Filtros(texto="-amor"))))
pb = ubicaciones.buscar_por_codigo(con, "PB").id
medir("Filtrar por planta (subárbol de 250 ubicaciones)", lambda: len(busqueda.buscar(con, Filtros(ubicacion_id=pb))))
medir("Contar elementos por ubicación", lambda: ubicaciones.contar_elementos(con))

from libridomus.interfaz.ventana_principal import VentanaPrincipal  # noqa: E402

v = medir("Abrir ventana principal", lambda: VentanaPrincipal(con))
v.resize(1400, 850)
medir("Mostrar ventana (pintar)", lambda: (v.show(), app.processEvents()))
medir("Ordenar por Personas", lambda: v.tabla.sortByColumn(2, Qt.SortOrder.AscendingOrder))
medir("Seleccionar todo (Ctrl+A)", lambda: (v.tabla.selectAll(), app.processEvents()))
medir("Filtrar árbol 'balda 3'", lambda: v.arbol.filtrar("balda 3"))
v.arbol.filtrar("")
medir("Escribir en el buscador y refrescar", lambda: (v.busqueda.setText("historia"), v.refrescar_resultados()))

hab = ubicaciones.hijos(con, pb)[0]
medir("Renombrar habitación (reindexa ~4.000)", lambda: ubicaciones.actualizar(con, hab.id, "Salón grande", hab.tipo_id, hab.codigo))
medir("Mover planta entera (reindexa ~25.000)", lambda: ubicaciones.mover(con, pb, ubicaciones.buscar_por_codigo(con, "CASA").id, 3))
casa = ubicaciones.obtener(con, ubicaciones.buscar_por_codigo(con, "CASA").id)
medir("Renombrar la casa (reindexa los 100.000)", lambda: ubicaciones.actualizar(con, casa.id, "Mi casa", casa.tipo_id, casa.codigo))
medir("Reindexar todo", lambda: busqueda.reindexar_todo(con))
ids = [f[0] for f in con.execute("SELECT id FROM elemento LIMIT 10000")]
medir("Mover 10.000 elementos a otra balda", lambda: elementos.mover(con, ids, baldas[0]))
medir("Borrar 10.000 elementos", lambda: elementos.borrar(con, ids))
medir("Copia automática", lambda: copias.copia_automatica(con, 10))
medir("Copia manual ZIP", lambda: copias.copia_manual(con, datos / "copia.zip"))
medir("Etiquetas PDF de las 993 ubicaciones", lambda: etiquetas.generar_pdf(con, [u.id for u in ubicaciones.todas(con)], datos / "e.pdf"))
medir("Inventario PDF de una habitación (~3.600)", lambda: informes.inventario(con, hab.id, datos / "i1.pdf"))
paginas = medir("Inventario PDF de TODA la casa (~90.000)", lambda: informes.inventario(con, None, datos / "i2.pdf"))
print(f"   tamaño PDF: {os.path.getsize(datos / 'i2.pdf') / 2**20:.1f} MB")
medir("Comprobación de integridad SQLite", lambda: con.execute("PRAGMA integrity_check").fetchone()[0])
print("Memoria final:", "%.0f MB (pico %.0f MB)" % memoria_mb())
