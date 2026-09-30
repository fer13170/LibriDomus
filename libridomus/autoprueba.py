"""Autoprueba del ejecutable: ``LibriDomus.exe --autoprueba``.

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
    lineas: list[str] = [f"LibriDomus {VERSION}"]
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
    paso("Tema, iconos y logotipo", _probar_tema)
    paso("Ventanas", _probar_ventanas)
    paso("Portadas JPEG", _probar_jpeg)
    paso("HTTPS (SSL)", _probar_ssl)
    paso("PDF (etiquetas e informe)", _probar_pdf)

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


def _probar_tema():
    """Los iconos SVG necesitan el módulo QtSvg dentro del paquete."""
    from PySide6.QtWidgets import QApplication

    from .interfaz import comun, tema

    app = QApplication.instance() or QApplication(["autoprueba"])
    iconos = list(tema.ICONOS.glob("*.svg"))
    assert len(iconos) > 90, f"solo hay {len(iconos)} iconos"
    for nombre in ("oscuro", "claro"):
        tema.aplicar(app, nombre, 1.15, "Segoe UI")
        imagen = tema.icono("book", "primario", 32).pixmap(32).toImage()
        pintados = sum(1 for x in range(imagen.width()) for y in range(imagen.height())
                       if imagen.pixelColor(x, y).alpha() > 0)
        assert pintados > 20, "el icono SVG sale vacío (¿falta QtSvg en el paquete?)"
    assert not comun.icono_app().isNull(), "falta el icono de la aplicación"
    assert (comun.RECURSOS / "logo.png").exists(), "falta el logotipo"
    tema.aplicar(app, "claro", 1.0, "Segoe UI")
    return f"{len(iconos)} iconos; temas claro y oscuro"


def _probar_ventanas():
    """Construye (sin mostrarlas) las ventanas principales sobre una base de datos temporal."""
    from PySide6.QtWidgets import QApplication

    from .datos import conexion
    from .interfaz import comun
    from .interfaz.editor_ubicaciones import EditorUbicaciones
    from .interfaz.ficha_elemento import FichaElemento
    from .interfaz.ventana_principal import VentanaPrincipal

    app = QApplication.instance() or QApplication(["autoprueba"])
    comun.preparar_aplicacion(app)
    with tempfile.TemporaryDirectory() as carpeta:
        con = conexion.abrir(Path(carpeta) / "ventanas.db")
        try:
            ventanas = [VentanaPrincipal(con), FichaElemento(con), EditorUbicaciones(con)]
            for v in ventanas:
                v.close()
        finally:
            con.close()
    from PySide6.QtCore import QCoreApplication

    traducido = QCoreApplication.translate("QPlatformTheme", "Close")
    return f"{len(ventanas)} ventanas; 'Close' -> '{traducido}'"


def _probar_jpeg():
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(["autoprueba"])
    imagen = QImage(40, 60, QImage.Format.Format_RGB32)
    imagen.fill(QColor("red"))
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "prueba.jpg"
        assert imagen.save(str(ruta), "JPG", 85), "Qt no puede guardar JPEG (falta el plugin qjpeg)"
        assert not QImage(str(ruta)).isNull(), "Qt no puede leer JPEG"
    return "guardar y leer JPEG correcto"


def _probar_ssl():
    import ssl

    contexto = ssl.create_default_context()
    return f"{ssl.OPENSSL_VERSION}; {len(contexto.get_ca_certs()) or 'certificados del sistema'}"


def _probar_pdf():
    from PySide6.QtWidgets import QApplication

    from .datos import conexion
    from .servicios import etiquetas, informes

    QApplication.instance() or QApplication(["autoprueba"])
    with tempfile.TemporaryDirectory() as carpeta:
        con = conexion.abrir(Path(carpeta) / "pdf.db")
        try:
            ids = [f[0] for f in con.execute("SELECT id FROM ubicacion")]
            etiquetas.generar_pdf(con, ids, Path(carpeta) / "e.pdf")
            informes.inventario(con, None, Path(carpeta) / "i.pdf")
            tamanos = [(Path(carpeta) / n).stat().st_size for n in ("e.pdf", "i.pdf")]
        finally:
            con.close()
    assert all(t > 500 for t in tamanos)
    return f"etiquetas {tamanos[0]} B, inventario {tamanos[1]} B"


def _probar_qr():
    import segno

    salida = io.BytesIO()
    segno.make("PB-SAL-EA-B3").save(salida, kind="png", scale=4)
    return f"PNG de {len(salida.getvalue())} bytes"
