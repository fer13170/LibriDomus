"""Varias instancias a la vez sobre la misma base de datos y cortes bruscos (proceso matado).

Uso:  .venv\\Scripts\\python tests\\robustez\\concurrencia_cortes.py
"""

import collections
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from comun_robustez import RAIZ, carpeta_datos

PYTHON = sys.executable
AQUI = Path(__file__).resolve().parent


def trabajador(modo: str, segundos: float, semilla: int) -> None:
    """Se ejecuta en un proceso hijo: hace operaciones sin parar y cuenta los errores por tipo."""
    sys.path.insert(0, str(RAIZ))
    from libridomus.datos import conexion, elementos, tipos, ubicaciones
    from libridomus.datos.elementos import Elemento
    from libridomus.servicios import busqueda
    from libridomus.servicios.busqueda import Filtros

    random.seed(semilla)
    con = conexion.abrir()
    libro = tipos.por_nombre(con, "Libro").id
    ubics = [u.id for u in ubicaciones.todas(con) if u.padre_id is not None]
    errores: collections.Counter = collections.Counter()
    hechas = 0
    fin = time.time() + segundos
    while time.time() < fin:
        try:
            if modo == "escritor":
                elementos.guardar(con, Elemento(tipo_id=libro, titulo=f"p{semilla}-{hechas}",
                                                ubicacion_id=random.choice(ubics), personas=[("Autor X", "Autor")]))
            elif modo == "movedor":
                ids = [f[0] for f in con.execute("SELECT id FROM elemento ORDER BY random() LIMIT 20")]
                elementos.mover(con, ids, random.choice(ubics))
                u = random.choice(ubics)
                ubicaciones.mover(con, u, ubicaciones.obtener(con, u).padre_id, 0)
            elif modo == "lector":
                busqueda.buscar(con, Filtros(texto=random.choice(["autor", "p1", "p2", "x"])))
            elif modo == "copias":
                from libridomus.servicios import copias
                copias.copia_automatica(con, 3)
            hechas += 1
        except Exception as e:  # noqa: BLE001
            errores[f"{type(e).__name__}: {str(e)[:60]}"] += 1
    print(f"{modo}#{semilla}: {hechas} operaciones; errores: {dict(errores) or 'ninguno'}", flush=True)


def trabajador_corte(semilla: int) -> None:
    """Escribe sin parar (lotes en transacción, mover y renombrar) hasta que lo maten."""
    sys.path.insert(0, str(RAIZ))
    from libridomus.datos import conexion, elementos, tipos, ubicaciones
    from libridomus.datos.elementos import Elemento

    random.seed(semilla)
    con = conexion.abrir()
    libro = tipos.por_nombre(con, "Libro").id
    ubics = [u.id for u in ubicaciones.todas(con) if u.padre_id is not None]
    n = 0
    while True:
        with conexion.transaccion(con):
            for _i in range(50):
                elementos.guardar(con, Elemento(tipo_id=libro, titulo=f"corte {semilla}-{n}", notas="x" * 2000,
                                                ubicacion_id=random.choice(ubics)))
                n += 1
        u = ubicaciones.obtener(con, random.choice(ubics))
        ubicaciones.actualizar(con, u.id, u.nombre + "·", u.tipo_id, u.codigo)


def comprobar(ruta: Path) -> str:
    c = sqlite3.connect(ruta)
    try:
        integridad = c.execute("PRAGMA integrity_check").fetchone()[0]
        n_elem = c.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
        n_fts = c.execute("SELECT COUNT(*) FROM elemento_fts").fetchone()[0]
        sin_indice = c.execute("SELECT COUNT(*) FROM elemento WHERE id NOT IN (SELECT rowid FROM elemento_fts)").fetchone()[0]
        fts_ok = c.execute("INSERT INTO elemento_fts(elemento_fts) VALUES('integrity-check')") and "ok"
    except sqlite3.DatabaseError as e:
        return f"ERROR: {e}"
    finally:
        c.close()
    return f"integridad={integridad}; elementos={n_elem}; índice={n_fts}; sin indexar={sin_indice}; fts={fts_ok}"


def preparar(carpeta: Path) -> None:
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    sys.path.insert(0, str(RAIZ))
    from libridomus.datos import conexion, ubicaciones
    con = conexion.abrir()
    tipo = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre = 'Balda'").fetchone()[0]
    for i in range(30):
        ubicaciones.crear(con, ubicaciones.buscar_por_codigo(con, "PB").id, tipo, f"Balda {i}")
    con.close()


def lanzar(*argumentos) -> subprocess.Popen:
    return subprocess.Popen([PYTHON, str(Path(__file__)), *map(str, argumentos)], env=os.environ.copy(),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")


def main() -> None:
    # ---------------- 1. Concurrencia: 2 escritores + 1 movedor + 2 lectores + 1 haciendo copias, 25 s
    carpeta = carpeta_datos("concurrencia")
    preparar(carpeta)
    print("== Concurrencia: 6 procesos a la vez durante 25 s sobre la misma base de datos")
    procesos = [lanzar("hijo", m, 25, s) for m, s in
                [("escritor", 1), ("escritor", 2), ("movedor", 3), ("lector", 4), ("lector", 5), ("copias", 6)]]
    for p in procesos:
        salida, _ = p.communicate()
        print("   " + salida.strip().replace("\n", "\n   "))
    print("   Estado final:", comprobar(carpeta / "biblioteca.db"))

    # ---------------- 2. Cortes bruscos
    carpeta = carpeta_datos("cortes")
    preparar(carpeta)
    print("== Cortes bruscos: 15 veces se mata el proceso a mitad de escritura")
    random.seed(9)
    malos = 0
    for vuelta in range(15):
        p = lanzar("corte", vuelta)
        time.sleep(random.uniform(1.5, 4.0))
        p.kill()  # TerminateProcess en Windows: como un corte de luz para el proceso
        p.wait()
        estado = comprobar(carpeta / "biblioteca.db")
        if "integridad=ok" not in estado or "sin indexar=0" not in estado:
            malos += 1
        print(f"   corte {vuelta + 1:2d}: {estado}")
    restos = [p.name for p in carpeta.iterdir() if p.name.endswith(("-journal", "-wal"))]
    print(f"   Cortes con daños: {malos} de 15. Restos de diario tras el último corte: {restos or 'ninguno'}")
    # Al volver a abrir con la aplicación, SQLite deshace la transacción a medias del diario.
    sys.path.insert(0, str(RAIZ))
    from libridomus.datos import conexion
    c = conexion.abrir()
    c.close()
    print("   Tras reabrir con LibriDomus:", comprobar(carpeta / "biblioteca.db"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "hijo":
        trabajador(sys.argv[2], float(sys.argv[3]), int(sys.argv[4]))
    elif len(sys.argv) > 1 and sys.argv[1] == "corte":
        trabajador_corte(int(sys.argv[2]))
    else:
        main()
