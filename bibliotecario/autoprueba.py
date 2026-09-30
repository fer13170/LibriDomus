"""Autoprueba del ejecutable: ``BibliotecarioVirtual.exe --autoprueba``.

Comprueba que el paquete trae todo lo necesario (Qt, SQLite con FTS5, segno) y
que la base de datos se crea y migra bien. Como el .exe no tiene consola, el
resultado se escribe en ``datos/autoprueba.txt`` y en el código de salida (0 = bien).
"""

import io
import sqlite3
import tempfile
import traceback
from pathlib import Path

from . import VERSION, rutas


def ejecutar() -> int:
    lineas: list[str] = [f"Bibliotecario Virtual {VERSION}"]
    ok = True

    def paso(nombre, funcion):
        nonlocal ok
        try:
            detalle = funcion()
            lineas.append(f"[OK]    {nombre}{': ' + str(detalle) if detalle else ''}")
        except Exception:  # noqa: BLE001 - queremos informar de cualquier fallo
            ok = False
            lineas.append(f"[FALLO] {nombre}\n{traceback.format_exc()}")

    paso("SQLite", lambda: sqlite3.sqlite_version)
    paso("FTS5 sin acentos", _probar_fts)
    paso("Base de datos nueva", _probar_base_datos)
    paso("Qt", _probar_qt)
    paso("QR (segno)", _probar_qr)

    lineas.append("RESULTADO: " + ("CORRECTO" if ok else "CON ERRORES"))
    texto = "\n".join(lineas)
    try:
        (rutas.carpeta_datos() / "autoprueba.txt").write_text(texto, encoding="utf-8")
    except OSError:
        pass
    try:
        print(texto)
    except Exception:  # noqa: BLE001 - sin consola, print puede fallar
        pass
    return 0 if ok else 1


def _probar_fts():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE VIRTUAL TABLE t USING fts5(x, tokenize='unicode61 remove_diacritics 2', prefix='2 3')"
    )
    con.execute("INSERT INTO t VALUES ('Gabriel García Márquez')")
    filas = con.execute("SELECT x FROM t WHERE t MATCH 'garc* AND marquez'").fetchall()
    assert filas, "la búsqueda sin acentos no encuentra nada"
    return "búsqueda 'garc* marquez' correcta"


def _probar_base_datos():
    from .datos import conexion

    with tempfile.TemporaryDirectory() as carpeta:
        con = conexion.abrir(Path(carpeta) / "prueba.db")
        try:
            plantas = con.execute(
                "SELECT COUNT(*) FROM ubicacion u JOIN tipo_ubicacion t ON t.id = u.tipo_id"
                " WHERE t.nombre = 'Planta'"
            ).fetchone()[0]
            tipos = con.execute("SELECT COUNT(*) FROM tipo_elemento").fetchone()[0]
            assert plantas == 4 and tipos == 10
            return f"esquema v{conexion.version(con)}, {plantas} plantas, {tipos} tipos de elemento"
        finally:
            con.close()


def _probar_qt():
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["autoprueba"])
    assert app is not None
    return f"Qt {qVersion()}"


def _probar_qr():
    import segno

    salida = io.BytesIO()
    segno.make("PB-SAL-EA-B3").save(salida, kind="png", scale=4)
    return f"PNG de {len(salida.getvalue())} bytes"
