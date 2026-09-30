"""Pruebas de regresión de las correcciones del informe de robustez (docs/Informe_robustez.md)."""

import io
import json
import logging
import os
import sqlite3
import sys
import time
import zipfile

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from libridomus import rutas
from libridomus.datos import conexion, elementos, tipos, ubicaciones
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import aplicacion, comun
from libridomus.servicios import busqueda, configuracion, copias, isbn, registro
from libridomus.servicios.busqueda import Filtros


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mensajes(monkeypatch):
    registro_mensajes = []
    monkeypatch.setattr(comun, "confirmar", lambda _p, m: registro_mensajes.append(("confirmar", m)) or True)
    monkeypatch.setattr(comun, "aviso", lambda _p, m: registro_mensajes.append(("aviso", m)))
    monkeypatch.setattr(comun, "error", lambda _p, m: registro_mensajes.append(("error", m)))
    return registro_mensajes


def libro(con):
    return tipos.por_nombre(con, "Libro").id


# ======================================================================= C9: base de datos dañada

def test_base_dañada_o_truncada_da_error_comprensible(carpeta_datos):
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    aleatoria = carpeta_datos / "aleatoria.db"
    aleatoria.write_bytes(os.urandom(40000))
    with pytest.raises(conexion.BaseDatosDanada):
        conexion.abrir(aleatoria)
    buena = carpeta_datos / "buena.db"
    conexion.abrir(buena).close()
    datos = buena.read_bytes()
    truncada = carpeta_datos / "truncada.db"
    truncada.write_bytes(datos[: len(datos) // 2])
    with pytest.raises(conexion.BaseDatosDanada):
        conexion.abrir(truncada, comprobar_integridad=True)


def test_base_de_solo_lectura_se_detecta_al_abrir(carpeta_datos):
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    ruta = carpeta_datos / "ro.db"
    conexion.abrir(ruta).close()
    os.chmod(ruta, 0o444)
    try:
        with pytest.raises(conexion.BaseDatosSoloLectura):
            conexion.abrir(ruta, exigir_escritura=True)
    finally:
        os.chmod(ruta, 0o666)


def _estropear_base():
    ruta = rutas.ruta_base_datos()
    datos = ruta.read_bytes()
    ruta.write_bytes(datos[:1024] + os.urandom(len(datos) - 1024))


def test_arranque_con_base_dañada_restaura_la_ultima_copia(app, con, monkeypatch):
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="Salvado por la copia"))
    copias.copia_automatica(con, 5)
    con.close()
    _estropear_base()
    preguntas = []
    monkeypatch.setattr(comun, "preguntar", lambda texto, detalle, opciones: preguntas.append(opciones) or 0)
    nueva = aplicacion.abrir_datos()
    assert nueva is not None and preguntas[0][0] == "Restaurar la copia"
    assert [f[0] for f in nueva.execute("SELECT titulo FROM elemento")] == ["Salvado por la copia"]
    assert list(rutas.carpeta_datos().glob("biblioteca_danada_*.db")), "el archivo dañado se guarda aparte"
    nueva.close()


def test_arranque_con_base_dañada_sin_copias(app, con, monkeypatch):
    con.close()
    _estropear_base()
    monkeypatch.setattr(comun, "preguntar", lambda texto, detalle, opciones: 1)  # «Salir»
    assert aplicacion.abrir_datos() is None
    assert not list(rutas.carpeta_datos().glob("biblioteca_danada_*.db")), "si se sale, no se toca nada"
    monkeypatch.setattr(comun, "preguntar", lambda texto, detalle, opciones: 0)  # «Empezar con datos nuevos»
    nueva = aplicacion.abrir_datos()
    assert nueva is not None and nueva.execute("SELECT COUNT(*) FROM tipo_elemento").fetchone()[0] == 10
    assert list(rutas.carpeta_datos().glob("biblioteca_danada_*.db"))
    nueva.close()


# ======================================================================= A6: errores y registro

@pytest.fixture
def registro_limpio():
    for manejador in list(registro.registro.handlers):
        registro.registro.removeHandler(manejador)
        manejador.close()
    registro._configurado = False
    yield
    for manejador in list(registro.registro.handlers):
        registro.registro.removeHandler(manejador)
        manejador.close()
    registro._configurado = False


def test_error_en_una_accion_se_explica_y_se_registra(app, con, mensajes, registro_limpio, monkeypatch):
    registro.configurar()
    anterior = sys.excepthook
    aplicacion.instalar_gestor_errores()
    try:
        def accion_que_falla():
            raise sqlite3.OperationalError("database is locked")
        QTimer.singleShot(0, accion_que_falla)
        for _ in range(5):
            app.processEvents()
    finally:
        sys.excepthook = anterior
    assert mensajes and mensajes[-1][0] == "error"
    assert "en uso por otro programa" in mensajes[-1][1] and "registro.log" in mensajes[-1][1]
    for manejador in registro.registro.handlers:
        manejador.flush()
    texto = (rutas.carpeta_datos() / "registro.log").read_text(encoding="utf-8")
    assert "database is locked" in texto and "Traceback" in texto


def test_carpeta_inaccesible_no_se_confunde_con_base_danada(tmp_path):
    with pytest.raises(conexion.ErrorBaseDatos) as info:
        conexion.abrir(tmp_path / "no_existe" / "biblioteca.db")
    assert not isinstance(info.value, conexion.BaseDatosDanada)


@pytest.mark.parametrize("error, contiene", [
    (sqlite3.OperationalError("attempt to write a readonly database"), "solo lectura"),
    (sqlite3.OperationalError("database or disk is full"), "espacio libre"),
    (sqlite3.DatabaseError("file is not a database"), "dañada"),
    (ZeroDivisionError("x"), "error inesperado"),
])
def test_mensajes_para_el_usuario(error, contiene):
    assert contiene in registro.mensaje_para_usuario(error)


def test_una_sola_instancia_por_carpeta_de_datos(app, carpeta_datos):
    primero = aplicacion.bloquear_instancia()
    assert primero is not None
    try:
        assert aplicacion.bloquear_instancia() is None
    finally:
        primero.unlock()
    segundo = aplicacion.bloquear_instancia()
    assert segundo is not None
    segundo.unlock()


# ======================================================================= C11: preferencias

def test_preferencias_con_valores_invalidos_usan_valores_seguros():
    rutas.ruta_configuracion().write_text(json.dumps({
        "escala": "grande", "tema": 7, "fuente": None, "columnas_ocultas": "x", "panel_detalle": "no",
        "copias_a_conservar": -3, "etiquetas_titulos": 999, "desconocida": 1}), encoding="utf-8")
    a = configuracion.cargar()
    assert (a["escala"], a["tema"], a["fuente"], a["columnas_ocultas"], a["panel_detalle"]) == \
        (1.0, "claro", "Segoe UI", [5], True)
    assert a["copias_a_conservar"] == 1 and a["etiquetas_titulos"] == 12 and "desconocida" not in a
    rutas.ruta_configuracion().write_text(json.dumps({"escala": 50, "columnas_ocultas": [1, 2, 99, "3"]}),
                                          encoding="utf-8")
    a = configuracion.cargar()
    assert a["escala"] == 1.5 and a["columnas_ocultas"] == [2]  # nunca se oculta el título (1)


def test_preparar_aplicacion_con_config_absurda_no_falla(app):
    from libridomus.interfaz import tema
    rutas.ruta_configuracion().write_text(json.dumps({"escala": "grande"}), encoding="utf-8")
    comun.preparar_aplicacion(app)
    assert tema.estado.escala == 1.0
    tema.aplicar(app, "claro", 50, "Segoe UI")
    assert tema.estado.escala == 1.5


# ======================================================================= D10–D13: copias

def test_copia_con_esquema_falso_se_rechaza(con, tmp_path):
    falsa = tmp_path / "falsa.db"
    f = sqlite3.connect(falsa)
    f.executescript("CREATE TABLE elemento(x); CREATE TABLE ubicacion(x); CREATE TABLE tipo_elemento(x);"
                    "PRAGMA user_version=2;")
    f.close()
    with pytest.raises(copias.ErrorCopia, match="estructura"):
        copias.restaurar(con, falsa)
    assert con.execute("SELECT COUNT(*) FROM tipo_elemento").fetchone()[0] == 10  # sigue intacta


@pytest.mark.parametrize("sql", [
    "CREATE TRIGGER sabotaje AFTER INSERT ON elemento BEGIN DELETE FROM elemento; END",
    "CREATE VIEW espia AS SELECT * FROM elemento",
])
def test_copia_con_disparadores_o_vistas_se_rechaza(con, sql):
    copia = copias.copia_automatica(con, 5)
    t = sqlite3.connect(copia)
    t.execute(sql)
    t.commit()
    t.close()
    with pytest.raises(copias.ErrorCopia, match="modificada"):
        copias.restaurar(con, copia)


def test_copia_de_version_anterior_sigue_siendo_valida(tmp_path):
    antigua = tmp_path / "v1.db"
    a = sqlite3.connect(antigua)
    from libridomus.datos import esquema
    a.executescript(esquema.MIGRACION_1)
    a.execute("PRAGMA user_version = 1")
    a.commit()
    a.close()
    assert copias.validar_base_datos(antigua) == 1
    copias.probar_apertura(antigua)  # se migra sobre un duplicado sin dejar copias previas
    assert not list(rutas.carpeta_copias().glob("antes_de_migrar_*"))


def test_zip_bomba_se_rechaza_sin_descomprimirla(con, tmp_path):
    bomba = tmp_path / "bomba.zip"
    with zipfile.ZipFile(bomba, "w", zipfile.ZIP_DEFLATED) as z:
        with z.open("biblioteca.db", "w", force_zip64=True) as destino:
            for _ in range(200):
                destino.write(b"\0" * (1 << 20))
    inicio = time.perf_counter()
    with pytest.raises(copias.ErrorCopia, match="sospechoso"):
        copias.restaurar(con, bomba)
    assert time.perf_counter() - inicio < 2


def test_zip_solo_extrae_lo_que_es_de_libridomus(con, tmp_path):
    bd = copias.copia_automatica(con, 5).read_bytes()
    zip_ruta = tmp_path / "mezcla.zip"
    with zipfile.ZipFile(zip_ruta, "w") as z:
        z.writestr("biblioteca.db", bd)
        z.writestr("programa.exe", b"MZ...")
        z.writestr("portadas/../../fuera.jpg", b"x")
        z.writestr("portadas/sub/otra.jpg", b"x")
    copias.restaurar(con, zip_ruta)
    assert not list(rutas.carpeta_datos().rglob("programa.exe"))
    assert not list(rutas.carpeta_datos().parent.glob("fuera.jpg"))
    conexion.abrir().close()


def test_copia_manual_no_incluye_la_clave_de_google(con, tmp_path):
    configuracion.guardar({**configuracion.cargar(), "clave_google_books": "CLAVE-SECRETA"})
    destino = copias.copia_manual(con, tmp_path / "c.zip")
    with zipfile.ZipFile(destino) as z:
        contenido = z.read("config.json").decode("utf-8")
    assert "CLAVE-SECRETA" not in contenido and "clave_google_books" not in contenido


# ======================================================================= C8, C5, C6, B4, A8

def test_borrar_mas_de_32766_elementos(con):
    with conexion.transaccion(con):
        ids = [elementos.guardar(con, Elemento(tipo_id=libro(con), titulo=f"m{i}")) for i in range(33000)]
    assert elementos.borrar(con, ids) == 33000
    assert con.execute("SELECT COUNT(*) FROM elemento_fts").fetchone()[0] == 0


def test_filtrar_y_borrar_ubicacion_con_muchisimas_sububicaciones(con):
    caja = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Caja'").fetchone()[0]
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    raiz = ubicaciones.crear(con, pb, caja, "Contenedor")
    with conexion.transaccion(con):
        hijos = [con.execute("INSERT INTO ubicacion (padre_id, tipo_id, nombre, codigo) VALUES (?, ?, 'c', ?)",
                             (raiz, caja, f"X{i}")).lastrowid for i in range(33000)]
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="dentro", ubicacion_id=hijos[-1]))
    assert [r.titulo for r in busqueda.buscar(con, Filtros(ubicacion_id=raiz))] == ["dentro"]
    ubicaciones.borrar(con, raiz, destino_id=pb)
    assert ubicaciones.obtener(con, raiz) is None


def test_texto_con_sustitutos_sueltos_se_guarda_saneado(con):
    id_ = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="roto \ud800 fin"))
    assert elementos.obtener(con, id_).titulo == "roto ? fin"


def test_codigos_de_ubicaciones_muy_anidadas_tienen_longitud_limitada(con):
    caja = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Caja'").fetchone()[0]
    padre = ubicaciones.buscar_por_codigo(con, "PB").id
    for i in range(60):
        padre = ubicaciones.crear(con, padre, caja, f"Caja {i}")
    assert len(ubicaciones.obtener(con, padre).codigo) <= ubicaciones.LONGITUD_MAXIMA_CODIGO + 4
    codigos = [u.codigo for u in ubicaciones.todas(con)]
    assert len(codigos) == len(set(codigos))


def test_muchas_ubicaciones_con_el_mismo_nombre_se_crean_rapido(con):
    caja = con.execute("SELECT id FROM tipo_ubicacion WHERE nombre='Caja'").fetchone()[0]
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    inicio = time.perf_counter()
    with conexion.transaccion(con):
        for _ in range(1500):
            ubicaciones.crear(con, pb, caja, "Caja")
    assert time.perf_counter() - inicio < 10


def test_renombrar_la_casa_o_reordenar_plantas_no_reindexa_todo(con, monkeypatch):
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    casa = ubicaciones.obtener(con, ubicaciones.buscar_por_codigo(con, "CASA").id)
    for i in range(20):
        elementos.guardar(con, Elemento(tipo_id=libro(con), titulo=f"e{i}", ubicacion_id=pb))
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="en la casa", ubicacion_id=casa.id))
    llamadas = []
    original = busqueda.reindexar
    monkeypatch.setattr(busqueda, "reindexar", lambda c, i, r=None: llamadas.append(i) or original(c, i, r))
    ubicaciones.actualizar(con, casa.id, "Mi casa", casa.tipo_id, casa.codigo)
    assert len(llamadas) == 1  # solo lo guardado directamente en la casa
    assert busqueda.buscar(con, Filtros(texto="mi casa"))
    llamadas.clear()
    ubicaciones.mover(con, pb, casa.id, 0)  # solo reordenar
    u = ubicaciones.obtener(con, pb)
    ubicaciones.actualizar(con, pb, u.nombre, u.tipo_id, "PB2", "nueva descripción")  # sin cambiar el nombre
    assert llamadas == []


def test_limpieza_de_huerfanos_selectiva(con):
    a = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="A", personas=[("Compartida", "Autor"), ("Sola", "Autor")]))
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="B", personas=[("Compartida", "Autor")]))
    e = elementos.obtener(con, a)
    e.personas = [("Nueva", "Autor")]
    elementos.guardar(con, e)
    assert elementos.nombres_personas(con) == ["Compartida", "Nueva"]


def test_reindexar_todo_usa_transaccion(con):
    for i in range(300):
        elementos.guardar(con, Elemento(tipo_id=libro(con), titulo=f"r{i}"))
    inicio = time.perf_counter()
    assert busqueda.reindexar_todo(con) == 300
    assert time.perf_counter() - inicio < 5


# ======================================================================= D5–D7: ISBN

class _RespuestaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_isbn_rechaza_redirecciones_a_http():
    manejador = isbn._SoloHttps()
    with pytest.raises(isbn.ErrorConsulta, match="no segura"):
        manejador.redirect_request(None, None, 302, "Found", {}, "http://ejemplo.invalid/")
    with pytest.raises(isbn.ErrorConsulta, match="https"):
        isbn.descargar("http://openlibrary.org/isbn/1.json")


def test_isbn_limita_el_tamano_de_la_respuesta(monkeypatch):
    monkeypatch.setattr(isbn._ABRIDOR, "open", lambda *a, **k: _RespuestaFalsa(b"x" * (isbn.TAMANO_MAXIMO + 10)))
    with pytest.raises(isbn.ErrorConsulta, match="demasiado grande"):
        isbn.descargar("https://openlibrary.org/isbn/1.json")


@pytest.mark.parametrize("respuesta", [
    {"title": "T", "publishers": "no es una lista"}, {"title": "T", "authors": "no es una lista"},
    {"title": "T", "authors": [{"key": 123}]}, {"title": "T", "number_of_pages": "300"},
    {"title": {"objeto": 1}}, {"title": "T", "covers": ["x", None, -1]}, {"title": "T", "languages": ["spa"]},
    {"title": "T", "works": [{}]}, {"title": "T", "authors": [{"key": "/../../etc"}]}, [1, 2, 3], "texto",
])
def test_isbn_respuestas_malformadas_no_rompen_nada(monkeypatch, respuesta):
    pedidas = []
    monkeypatch.setattr(isbn, "descargar",
                        lambda url: pedidas.append(url) or (json.dumps(respuesta).encode() if "isbn/" in url else None))
    try:
        datos = isbn.consultar("9788483468463")
    except isbn.ErrorConsulta:
        return
    assert datos is None or isinstance(datos.titulo, str)
    assert all(u.startswith("https://") and ".." not in u for u in pedidas)


# ======================================================================= B2, B3: ventana principal

def test_seleccionar_todo_es_rapido_y_correcto(app, con, mensajes):
    from libridomus.interfaz.ventana_principal import VentanaPrincipal
    with conexion.transaccion(con):
        ids = [elementos.guardar(con, Elemento(tipo_id=libro(con), titulo=f"s{i}")) for i in range(3000)]
    v = VentanaPrincipal(con)
    inicio = time.perf_counter()
    v.tabla.selectAll()
    seleccionados = v.ids_seleccionados()
    assert time.perf_counter() - inicio < 1.5
    assert sorted(seleccionados) == sorted(ids) and len(v.detalle.ids) == 3000


def test_refresco_parcial_tras_editar_prestar_y_mover(app, con, mensajes, monkeypatch):
    from libridomus.interfaz import ventana_principal
    from libridomus.interfaz.ventana_principal import VentanaPrincipal
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    sot = ubicaciones.buscar_por_codigo(con, "SOT").id
    a = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="Aquí", ubicacion_id=pb))
    b = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="También", ubicacion_id=pb))
    v = VentanaPrincipal(con)
    v.arbol.seleccionar(pb)
    recargas = []
    monkeypatch.setattr(v, "refrescar_resultados", lambda *x: recargas.append(1))
    e = elementos.obtener(con, a)
    e.titulo = "Aquí (editado)"
    elementos.guardar(con, e)
    v.refrescar_elementos([a], a)
    assert v.modelo.resultado(v.modelo.fila_de(a)).titulo == "Aquí (editado)"
    v.mover_a([b], sot)  # sale de la planta baja: desaparece de la lista
    assert v.modelo.fila_de(b) is None and v.modelo.rowCount() == 1
    assert recargas == [], "no debe recargarse la lista entera"
    assert v.contador.text() == "1 elemento"


def test_recargar_el_arbol_no_recarga_la_lista(app, con, mensajes):
    from libridomus.interfaz.ventana_principal import VentanaPrincipal
    v = VentanaPrincipal(con)
    avisos = []
    v.arbol.ubicacion_cambiada.connect(avisos.append)
    v.arbol.cargar()
    assert avisos == []
    v.arbol.cargar(ubicaciones.buscar_por_codigo(con, "PA").id)
    assert avisos == [ubicaciones.buscar_por_codigo(con, "PA").id]


# ======================================================================= D3: HTML

def test_datos_del_usuario_no_se_interpretan_como_html(app, con):
    from PySide6.QtCore import Qt
    from libridomus.interfaz.panel_detalle import PanelDetalle
    id_ = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="<h1>ENORME</h1>", subtitulo="<u>s</u>",
                                          etiquetas=["<i>x</i>"], notas="<img src='file:///C:/x.jpg'>"))
    panel = PanelDetalle(con)
    panel.mostrar([id_])
    for etiqueta in panel.findChildren(QLabel):
        if any(m in etiqueta.text() for m in ("<h1>", "<u>s", "<i>x", "<img")):
            assert etiqueta.textFormat() == Qt.TextFormat.PlainText, etiqueta.text()


# ======================================================================= memoria de los informes grandes

def test_informes_grandes_se_maquetan_por_partes(app, con, tmp_path, monkeypatch):
    from libridomus.servicios import informes
    monkeypatch.setattr(informes, "FILAS_POR_PARTE", 50)
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    with conexion.transaccion(con):
        for i in range(120):
            elementos.guardar(con, Elemento(tipo_id=libro(con), titulo=f"i{i:03d}", ubicacion_id=pb))
    maquetadas = []
    original = informes.QTextDocument.setHtml
    monkeypatch.setattr(informes.QTextDocument, "setHtml", lambda self, h: maquetadas.append(h.count("<tr>")) or original(self, h))
    assert informes.inventario(con, None, tmp_path / "inv.pdf") == 120
    assert len(maquetadas) == 3 and max(maquetadas) <= 51  # 50 filas + la cabecera de la tabla
    with open(tmp_path / "inv.pdf", "rb") as f:
        assert f.read(5) == b"%PDF-"
    partes = informes._partes("<h1>t</h1>", [("Sección", busqueda.buscar(con, Filtros()), False, False)], "")
    assert sum("(continuación)" in p for p in partes) == 2
