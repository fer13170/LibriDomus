"""Pruebas de estrés, entradas extremas y seguridad. Cada prueba imprime OK / FALLO y el detalle.

Uso:  .venv\\Scripts\\python tests\\robustez\\estres_seguridad.py
"""

import io
import json
import os
import random
import shutil
import sqlite3
import time
import traceback
import zipfile

from comun_robustez import carpeta_datos, medir

datos = carpeta_datos("estres_seguridad")
shutil.rmtree(datos, ignore_errors=True)
datos.mkdir(parents=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtGui import Qt as QtGui_Qt  # noqa: E402  (mightBeRichText está en QtGui)
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication([])
from libridomus import rutas  # noqa: E402
from libridomus.datos import conexion, elementos, tipos, ubicaciones  # noqa: E402
from libridomus.datos.elementos import Elemento  # noqa: E402
from libridomus.interfaz import comun  # noqa: E402
from libridomus.servicios import busqueda, configuracion, copias, isbn, portadas  # noqa: E402
from libridomus.servicios.busqueda import Filtros  # noqa: E402

comun.preparar_aplicacion(app)
con = conexion.abrir()
LIBRO = tipos.por_nombre(con, "Libro").id
PB = ubicaciones.buscar_por_codigo(con, "PB").id
informe: list[str] = []


def prueba(nombre):
    def decorador(funcion):
        try:
            detalle = funcion()
            linea = f"[OK]    {nombre}" + (f" — {detalle}" if detalle else "")
        except AssertionError as e:
            linea = f"[FALLO] {nombre} — {e}"
        except Exception as e:  # noqa: BLE001
            linea = f"[ERROR] {nombre} — {type(e).__name__}: {e}"
            traceback.print_exc()
        print(linea, flush=True)
        informe.append(linea)
        return funcion
    return decorador


# ======================================================================= entradas extremas

@prueba("Fuzzing del buscador: 20.000 textos aleatorios (unicode, símbolos FTS, comillas)")
def _():
    random.seed(1)
    for t in ("Hola mundo", "García Márquez", "C++ y C#", "O'Brien", '"cita"', "año 1984"):
        elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo=t))
    alfabeto = list('abcñáéíóú ÁÉ"\'*-^:()[]{}+.,;~!@#$%&/\\|<>=?¿¡_0123456789NOTANDORNEAR') + \
        ["\u0301", "\u200b", "\u202e", "😀", "𝔸", "中文", "\x00", "\t", "\n", "ﬁ", "ß", "İ"]
    errores = []
    inicio = time.perf_counter()
    for _i in range(20000):
        texto = "".join(random.choice(alfabeto) for _ in range(random.randint(0, 25)))
        try:
            busqueda.buscar(con, Filtros(texto=texto))
        except Exception as e:  # noqa: BLE001
            errores.append((texto, repr(e)))
    assert not errores, f"{len(errores)} errores, p. ej. {errores[:3]}"
    return f"0 errores en {time.perf_counter() - inicio:.1f} s"


@prueba("Búsqueda con un texto pegado enorme (100.000 caracteres)")
def _():
    texto = " ".join(f"palabra{i}" for i in range(10000))[:100000]
    inicio = time.perf_counter()
    busqueda.buscar(con, Filtros(texto=texto))
    return f"{time.perf_counter() - inicio:.2f} s"


@prueba("Textos extremos: emoji, RTL, ancho cero, combinantes, nulos, 1 MB de notas, título de 100.000 caracteres")
def _():
    casos = {
        "emoji": "📚 Libro 😀 con emojis 👨‍👩‍👧",
        "rtl": "كتاب עברית \u202eoicifidom\u202c",
        "ancho_cero": "In\u200bvi\u200bsi\u200bble",
        "combinante": "Ga\u0301rci\u0301a",
        "nulo": "antes\x00después",
        "largo": "L" * 100_000,
    }
    for clave, titulo in casos.items():
        id_ = elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo=titulo, notas="n" * (1 << 20) if clave == "largo" else ""))
        leido = elementos.obtener(con, id_)
        assert leido.titulo == titulo.strip(), f"{clave}: el título no vuelve igual"
    assert busqueda.buscar(con, Filtros(texto="garcia")), "'García' con acento combinante no se encuentra con 'garcia'"
    return "se guardan y se leen intactos; 'García' con tilde combinante se encuentra"


@prueba("Texto con sustitutos UTF-16 sueltos (no representable en UTF-8)")
def _():
    try:
        elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo="roto \ud800"))
    except UnicodeEncodeError as e:
        raise AssertionError(f"UnicodeEncodeError no controlado ({e.reason}). Desde la interfaz no debería "
                             "poder llegar, pero no está controlado en la capa de datos") from e


@prueba("Un elemento con 500 personas y 500 etiquetas")
def _():
    e = Elemento(tipo_id=LIBRO, titulo="Obra colectiva", personas=[(f"Persona {i}", "Autor") for i in range(500)],
                 etiquetas=[f"etiqueta{i}" for i in range(500)])
    inicio = time.perf_counter()
    id_ = elementos.guardar(con, e)
    t = time.perf_counter() - inicio
    assert len(elementos.obtener(con, id_).personas) == 500
    r = [x for x in busqueda.buscar(con, Filtros(texto="persona 499")) if x.id == id_]
    assert r, "no se encuentra por la última persona"
    return f"guardado en {t:.2f} s"


@prueba("Árbol muy profundo: 200 niveles de ubicaciones anidadas")
def _():
    tipo = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Caja'").fetchone()[0]
    padre = PB
    inicio = time.perf_counter()
    for i in range(200):
        padre = ubicaciones.crear(con, padre, tipo, f"Caja {i}")
    t_crear = time.perf_counter() - inicio
    id_ = elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo="En lo más hondo", ubicacion_id=padre))
    ruta = ubicaciones.ruta_texto(con, padre)
    codigo = ubicaciones.obtener(con, padre).codigo
    assert ruta.count("›") == 200
    inicio = time.perf_counter()
    ubicaciones.actualizar(con, PB, "Planta baja", ubicaciones.obtener(con, PB).tipo_id, "PB")
    t_reindex = time.perf_counter() - inicio
    return (f"crear {t_crear:.2f} s; ruta de {len(ruta)} caracteres; código de {len(codigo)} caracteres "
            f"(«{codigo[:40]}…»); renombrar la planta {t_reindex:.2f} s")


@prueba("Árbol muy ancho: 5.000 cajas dentro de la misma balda")
def _():
    tipo = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Caja'").fetchone()[0]
    balda = ubicaciones.crear(con, PB, con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Balda'").fetchone()[0],
                              "Balda ancha")
    inicio = time.perf_counter()
    with conexion.transaccion(con):
        for i in range(5000):
            ubicaciones.crear(con, balda, tipo, "Caja")  # mismo nombre: fuerza sufijos de código
    t = time.perf_counter() - inicio
    codigos = {u.codigo for u in ubicaciones.hijos(con, balda)}
    assert len(codigos) == 5000, "códigos repetidos"
    from libridomus.interfaz.arbol_ubicaciones import ArbolUbicaciones
    inicio = time.perf_counter()
    ArbolUbicaciones(con, contar=True, especiales=True)
    t_arbol = time.perf_counter() - inicio
    inicio = time.perf_counter()
    ultima = ubicaciones.hijos(con, balda)[-1]
    ubicaciones.mover(con, ultima.id, balda, 0)
    t_mover = time.perf_counter() - inicio
    return f"crear 5.000 con el mismo nombre {t:.1f} s; cargar árbol {t_arbol:.2f} s; reordenar una {t_mover:.2f} s"


@prueba("Fechas: 5.000 valores aleatorios en «Desde/Hasta» se validan sin excepciones inesperadas")
def _():
    random.seed(3)
    inesperadas = []
    for _i in range(5000):
        f = "".join(random.choice("0123456789-/ .ab") for _ in range(random.randint(0, 12)))
        try:
            elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo="fecha", fecha_desde=f))
        except elementos.ErrorElemento:
            pass
        except Exception as e:  # noqa: BLE001
            inesperadas.append((f, repr(e)))
    assert not inesperadas, inesperadas[:3]


@prueba("Año fuera de rango y valoración inválida se rechazan con mensaje")
def _():
    for extra in ({"anio": -5}, {"anio": 100000}, {"valoracion": 9}):
        try:
            elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo="x", **extra))
            raise AssertionError(f"se aceptó {extra}")
        except elementos.ErrorElemento:
            pass


# ======================================================================= interfaz y HTML

@prueba("HTML en los datos del usuario: ¿se interpreta en la interfaz?")
def _():
    titulo = "<h1 style='font-size:60px;color:red'>ENORME</h1><a href='https://ejemplo.invalid'>pulsa</a>"
    id_ = elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo=titulo, personas=[("<b>Negrita</b>", "Autor")],
                                          etiquetas=["<i>x</i>"], notas="<img src='file:///C:/Windows/web/wallpaper/Windows/img0.jpg'>"))
    from libridomus.interfaz.panel_detalle import PanelDetalle
    panel = PanelDetalle(con)
    panel.mostrar([id_])
    interpretados = [l.text()[:40] for l in panel.findChildren(QLabel)
                     if l.textFormat() != Qt.TextFormat.PlainText and QtGui_Qt.mightBeRichText(l.text())
                     and ("<h1" in l.text() or "<img" in l.text() or "<i>x" in l.text())]
    assert not interpretados, (f"{len(interpretados)} textos del usuario se muestran como HTML en el panel de "
                               f"detalle (título, notas, etiquetas): {interpretados}")


# ======================================================================= ISBN / red

@prueba("Respuestas de Open Library con tipos inesperados no provocan errores no controlados")
def _():
    respuestas = [
        {"title": "T", "publishers": "no es una lista"},
        {"title": "T", "authors": "no es una lista"},
        {"title": "T", "authors": [{"key": 123}]},
        {"title": "T", "number_of_pages": "300 páginas"},
        {"title": {"objeto": 1}},
        {"title": "T", "covers": ["x", None, -1]},
        {"title": "T", "languages": ["spa"]},
        {"title": "T", "works": [{}]},
        [1, 2, 3],
    ]
    fallos = []
    original = isbn.descargar
    for r in respuestas:
        isbn.descargar = lambda url, r=r: json.dumps(r).encode() if "isbn/" in url else None
        try:
            isbn.consultar("9788483468463")
        except (isbn.ErrorConsulta, ValueError):
            pass
        except Exception as e:  # noqa: BLE001
            fallos.append(f"{json.dumps(r)[:45]} -> {type(e).__name__}")
    isbn.descargar = original
    assert not fallos, (f"{len(fallos)} de {len(respuestas)} respuestas malformadas dan excepciones no controladas "
                        f"(en la interfaz se ve «Error inesperado»): {fallos}")


@prueba("TLS: se rechazan certificados caducados, autofirmados y de otro dominio")
def _():
    aceptados = []
    for url in ("https://expired.badssl.com/", "https://self-signed.badssl.com/", "https://wrong.host.badssl.com/"):
        try:
            isbn.descargar(url)
            aceptados.append(url)
        except isbn.ErrorConsulta:
            pass
    assert not aceptados, f"acepta certificados inválidos: {aceptados}"
    return "los tres se rechazan"


@prueba("Redirección de HTTPS a HTTP (degradación)")
def _():
    import urllib.request
    try:
        with urllib.request.urlopen("https://httpbin.org/redirect-to?url=http%3A%2F%2Fexample.com%2F", timeout=15) as r:
            final = r.geturl()
    except Exception as e:  # noqa: BLE001
        return f"no se pudo comprobar ({type(e).__name__})"
    assert not final.startswith("http://"), f"urllib sigue la redirección a {final} (texto sin cifrar)"


@prueba("Portada «bomba»: PNG de 30.000 × 30.000 píxeles (pesa poco comprimido)")
def _():
    imagen = QImage(30000, 30000, QImage.Format.Format_Mono)
    if imagen.isNull():
        return "no se puede ni crear para la prueba"
    imagen.fill(0)
    datos_png = portadas.a_png_bytes(imagen)
    del imagen
    inicio = time.perf_counter()
    try:
        portadas.guardar_desde_bytes(datos_png)
        resultado = "se acepta y se reduce"
    except portadas.ErrorPortada:
        resultado = "se rechaza de forma controlada (límite de memoria de imágenes de Qt)"
    return f"PNG de {len(datos_png) / 1024:.0f} KB: {resultado} en {time.perf_counter() - inicio:.1f} s"


@prueba("Descarga sin límite de tamaño")
def _():
    import inspect
    fuente = inspect.getsource(isbn.descargar)
    assert ".read(" in fuente and "read()" not in fuente.replace(" ", ""), \
        "descargar() lee la respuesta entera sin límite (respuesta.read()): un servidor malicioso o interceptado podría agotar la memoria"


# ======================================================================= copias y restauración

def zip_con(entradas: dict) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, contenido in entradas.items():
            z.writestr(nombre, contenido)
    buf.seek(0)
    return buf


@prueba("ZIP malicioso con rutas «../» (zip slip) al restaurar")
def _():
    global con
    bd = copias.copia_automatica(con, 50).read_bytes()
    victima = datos.parent / "ZIPSLIP_victima.txt"
    victima.unlink(missing_ok=True)
    zip_ruta = datos / "malicioso.zip"
    zip_ruta.write_bytes(zip_con({"biblioteca.db": bd, "../ZIPSLIP_victima.txt": "x",
                                  "../../ZIPSLIP_victima.txt": "x", "portadas/../../../ZIPSLIP_victima.txt": "x",
                                  "portadas/ok.jpg": b"no-imagen"}).getvalue())
    copias.restaurar(con, zip_ruta)
    con = conexion.abrir()
    escapados = list(datos.parent.rglob("ZIPSLIP_victima.txt")) + list(datos.parent.parent.glob("ZIPSLIP_victima.txt"))
    assert not escapados, f"se escribieron archivos fuera de la carpeta temporal: {escapados}"
    return "zipfile de Python neutraliza las rutas «..»: nada sale de la carpeta temporal"


@prueba("Copia «válida» pero con un esquema falso (tablas sin las columnas esperadas)")
def _():
    global con
    falsa = datos / "falsa.db"
    falsa.unlink(missing_ok=True)
    f = sqlite3.connect(falsa)
    f.executescript("CREATE TABLE elemento(x); CREATE TABLE ubicacion(x); CREATE TABLE tipo_elemento(x); PRAGMA user_version=2;")
    f.close()
    try:
        copias.restaurar(con, falsa)
    except copias.ErrorCopia as e:
        return f"rechazada: {e}"
    con = conexion.abrir()
    try:
        busqueda.buscar(con, Filtros())
        return "se acepta y funciona"
    except sqlite3.Error as e:
        # volver al estado anterior para seguir probando
        previa = sorted(rutas.carpeta_copias().glob("antes_de_restaurar_*.db"))[-1]
        copias.restaurar(con, previa)
        con = conexion.abrir()
        raise AssertionError(f"se restaura sin protestar y después el programa falla: {type(e).__name__}: {e}") from e


@prueba("Copia con un disparador (trigger) malicioso que borra datos")
def _():
    global con
    copia = copias.copia_automatica(con, 50)
    t = sqlite3.connect(copia)
    t.execute("CREATE TRIGGER sabotaje AFTER INSERT ON elemento BEGIN DELETE FROM elemento WHERE id <> NEW.id; END")
    t.commit()
    t.close()
    copias.restaurar(con, copia)
    con = conexion.abrir()
    antes = con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
    elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo="nuevo"))
    despues = con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0]
    con.execute("DROP TRIGGER sabotaje")
    assert despues == antes + 1, (f"un trigger escondido en una copia ajena se ejecuta: había {antes} elementos, "
                                  f"tras añadir uno quedan {despues}")


@prueba("ZIP «bomba»: biblioteca.db de 1 GB de ceros comprimida")
def _():
    ruta = datos / "bomba.zip"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        with z.open("biblioteca.db", "w", force_zip64=True) as dest:
            bloque = b"\0" * (1 << 20)
            for _i in range(1024):
                dest.write(bloque)
    tam = ruta.stat().st_size
    inicio = time.perf_counter()
    try:
        copias.restaurar(con, ruta)
        resultado = "¡aceptada!"
    except copias.ErrorCopia as e:
        resultado = f"rechazada ({e})"
    return (f"ZIP de {tam / 2**20:.1f} MB: {resultado}, pero antes se descomprimió entero (1 GB en disco temporal) "
            f"en {time.perf_counter() - inicio:.1f} s; no hay límite de tamaño")


# ======================================================================= arranque con datos dañados

@prueba("Arranque con biblioteca.db dañada (bytes aleatorios)")
def _():
    carpeta = datos.parent / "danada"
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir()
    (carpeta / "biblioteca.db").write_bytes(os.urandom(50000))
    try:
        conexion.abrir(carpeta / "biblioteca.db")
    except conexion.ErrorBaseDatos as e:
        return f"mensaje controlado: {e}"
    except sqlite3.DatabaseError as e:
        raise AssertionError(f"sqlite3.DatabaseError («{e}») no se convierte en ErrorBaseDatos: interfaz/aplicacion.py "
                             "solo captura ErrorBaseDatos, así que el programa se cierra sin explicar nada") from e


@prueba("Arranque con biblioteca.db truncada a la mitad (p. ej. copia interrumpida)")
def _():
    carpeta = datos.parent / "truncada"
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir()
    original = rutas.ruta_base_datos().read_bytes()
    (carpeta / "biblioteca.db").write_bytes(original[: len(original) // 2])
    try:
        c = conexion.abrir(carpeta / "biblioteca.db")
        c.execute("SELECT COUNT(*) FROM elemento_fts").fetchone()
        resultado = c.execute("PRAGMA quick_check").fetchone()[0]
        c.close()
        assert resultado == "ok", f"abre sin avisar pero la base está dañada (quick_check: {resultado[:60]}…)"
    except conexion.ErrorBaseDatos as e:
        return f"mensaje controlado: {e}"
    except sqlite3.DatabaseError as e:
        raise AssertionError(f"sqlite3.DatabaseError no controlado: {e}") from e


@prueba("Arranque con biblioteca.db de solo lectura")
def _():
    carpeta = datos.parent / "solo_lectura"
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir()
    shutil.copy2(rutas.ruta_base_datos(), carpeta / "biblioteca.db")
    os.chmod(carpeta / "biblioteca.db", 0o444)
    try:
        c = conexion.abrir(carpeta / "biblioteca.db")
        try:
            elementos.guardar(c, Elemento(tipo_id=LIBRO, titulo="x"))
            return "se puede escribir (¿?)"
        except sqlite3.OperationalError as e:
            raise AssertionError(f"abre sin avisar y falla al guardar con sqlite3.OperationalError («{e}»), que la "
                                 "ficha no captura: el usuario pulsa Guardar y no pasa nada") from e
        finally:
            c.close()
    finally:
        os.chmod(carpeta / "biblioteca.db", 0o666)


@prueba("Preferencias manipuladas (escala='grande', escala=50, tema=7, fuente=null)")
def _():
    malas = [{"escala": "grande"}, {"escala": 50}, {"tema": 7}, {"fuente": None}, {"columnas_ocultas": "x"},
             {"panel_detalle": "no"}]
    fallos = []
    for mala in malas:
        rutas.ruta_configuracion().write_text(json.dumps(mala), encoding="utf-8")
        try:
            comun.preparar_aplicacion(app)
            from libridomus.interfaz.ventana_principal import VentanaPrincipal
            VentanaPrincipal(con).close()
            from libridomus.interfaz import tema
            if tema.estado.escala > 2:
                fallos.append(f"{mala}: se acepta una escala de {tema.estado.escala:.0f} (interfaz gigante e inutilizable)")
        except Exception as e:  # noqa: BLE001
            fallos.append(f"{mala}: {type(e).__name__}")
    rutas.ruta_configuracion().unlink()
    comun.preparar_aplicacion(app)
    assert not fallos, "; ".join(fallos)


@prueba("Límite de variables de SQLite: borrar 40.000 elementos seleccionados de una vez")
def _():
    with conexion.transaccion(con):
        ids = [elementos.guardar(con, Elemento(tipo_id=LIBRO, titulo=f"masivo {i}")) for i in range(40000)]
    try:
        elementos.borrar(con, ids)
    except sqlite3.OperationalError as e:
        raise AssertionError(f"«{e}»: con más de 32.766 elementos seleccionados, Borrar falla") from e
    return "correcto"


@prueba("Límite de variables de SQLite: borrar una ubicación con 40.000 sububicaciones")
def _():
    tipo = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Caja'").fetchone()[0]
    raiz = ubicaciones.crear(con, PB, tipo, "Contenedor gigante")
    with conexion.transaccion(con):
        for i in range(40000):
            ubicaciones.crear(con, raiz, tipo, f"C{i}", codigo=f"GIG{i}")
    try:
        ubicaciones.borrar(con, raiz)
        return "correcto (caso poco realista)"
    except sqlite3.OperationalError as e:
        raise AssertionError(f"«{e}» (caso muy poco realista: 40.000 cajas)") from e


print("\n==== RESUMEN ====")
for linea in informe:
    print(linea)
