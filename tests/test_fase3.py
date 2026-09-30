"""Fase 3: ISBN (sin Internet: respuestas simuladas), portadas, préstamos y preferencias."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QInputDialog

from bibliotecario import rutas
from bibliotecario.datos import elementos, tipos, ubicaciones
from bibliotecario.datos.elementos import Elemento
from bibliotecario.interfaz import comun
from bibliotecario.interfaz.alta_masiva import AltaMasiva
from bibliotecario.interfaz.ficha_elemento import FichaElemento
from bibliotecario.interfaz.ventana_principal import VentanaPrincipal
from bibliotecario.servicios import busqueda, configuracion, isbn, portadas
from bibliotecario.servicios.busqueda import Filtros


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mensajes(monkeypatch):
    registro = []
    monkeypatch.setattr(comun, "confirmar", lambda _p, m: registro.append(("confirmar", m)) or True)
    monkeypatch.setattr(comun, "aviso", lambda _p, m: registro.append(("aviso", m)))
    monkeypatch.setattr(comun, "error", lambda _p, m: registro.append(("error", m)))
    # Las consultas "en segundo plano" se hacen en el acto para poder comprobarlas.
    def inmediato(funcion, al_terminar, al_fallar):
        try:
            resultado = funcion()
        except Exception as e:  # noqa: BLE001
            al_fallar(e)
        else:
            al_terminar(resultado)
    monkeypatch.setattr(comun, "en_segundo_plano", inmediato)
    return registro


def imagen_png(ancho=1200, alto=1600, color="red") -> bytes:
    imagen = QImage(ancho, alto, QImage.Format.Format_RGB32)
    imagen.fill(QColor(color))
    return portadas.a_png_bytes(imagen)


# Respuestas simuladas de Open Library para el ISBN de Gomorra
GOMORRA = "9788483468463"
RESPUESTAS = {
    f"https://openlibrary.org/isbn/{GOMORRA}.json": json.dumps({
        "title": "Gomorra", "publishers": ["Debolsillo"], "publish_date": "2009",
        "number_of_pages": 324, "languages": [{"key": "/languages/spa"}],
        "authors": [{"key": "/authors/OL1A"}], "covers": [123]}).encode(),
    "https://openlibrary.org/authors/OL1A.json": json.dumps({"name": "Roberto Saviano"}).encode(),
}


@pytest.fixture
def internet_simulado(monkeypatch):
    pedidas = []

    def descargar(url):
        pedidas.append(url)
        if url.startswith("https://covers.openlibrary.org/b/id/123"):
            return imagen_png(300, 450)
        return RESPUESTAS.get(url)  # None = 404

    monkeypatch.setattr(isbn, "descargar", descargar)
    return pedidas


# ---------------------------------------------------------------- ISBN

@pytest.mark.parametrize("texto, esperado", [
    ("978-84-8346-846-3", "9788483468463"),
    ("84-406-2553-7", "9788440625533"),       # ISBN-10 convertido a 13
    ("0-306-40615-2", "9780306406157"),
    ("080442957X", "9780804429573"),          # ISBN-10 con X
    ("978-84-8346-846-4", None),              # dígito de control incorrecto
    ("1234", None),
    ("", None),
])
def test_validar_isbn(texto, esperado):
    assert isbn.validar(texto) == esperado


def test_consulta_open_library(internet_simulado):
    datos = isbn.consultar("978-84-8346-846-3")
    assert (datos.titulo, datos.autores, datos.editorial, datos.anio, datos.paginas, datos.idioma) == \
        ("Gomorra", ["Roberto Saviano"], "Debolsillo", 2009, 324, "Español")
    assert datos.portada and datos.fuente == "Open Library"


def test_consulta_no_encontrado_y_google_solo_con_clave(internet_simulado, monkeypatch):
    assert isbn.consultar("84-406-2553-7") is None
    assert not any("googleapis" in u for u in internet_simulado)
    RESPUESTAS_GOOGLE = json.dumps({"items": [{"volumeInfo": {
        "title": "La conexión gallega", "authors": ["Perfecto Conde"], "publishedDate": "1991-05",
        "language": "es", "pageCount": 399}}]}).encode()
    monkeypatch.setitem(RESPUESTAS, "https://www.googleapis.com/books/v1/volumes?q=isbn%3A9788440625533&key=CLAVE",
                        RESPUESTAS_GOOGLE)
    datos = isbn.consultar("84-406-2553-7", "CLAVE")
    assert (datos.titulo, datos.anio, datos.idioma, datos.fuente) == ("La conexión gallega", 1991, "Español", "Google Books")


def test_sin_conexion_da_error_comprensible(monkeypatch):
    def sin_red(url):
        raise isbn.ErrorConsulta("No hay conexión a Internet o el servicio no responde.")
    monkeypatch.setattr(isbn, "descargar", sin_red)
    with pytest.raises(isbn.ErrorConsulta):
        isbn.consultar(GOMORRA)
    with pytest.raises(ValueError):
        isbn.consultar("12345")


# ---------------------------------------------------------------- portadas

def test_portada_se_reduce_y_se_guarda_en_jpeg(app):
    nombre = portadas.guardar_desde_bytes(imagen_png(1200, 1600))
    ruta = portadas.ruta(nombre)
    guardada = QImage(str(ruta))
    assert ruta.suffix == ".jpg" and max(guardada.width(), guardada.height()) == portadas.LADO_MAXIMO
    portadas.borrar(nombre)
    assert portadas.ruta(nombre) is None


def test_imagen_no_valida(app):
    with pytest.raises(portadas.ErrorPortada):
        portadas.guardar_desde_bytes(b"esto no es una imagen")


def test_limpiar_portadas_huerfanas(app, con):
    usada = portadas.guardar_desde_bytes(imagen_png(10, 10))
    huerfana = portadas.guardar_desde_bytes(imagen_png(10, 10))
    elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="X", portada=usada))
    assert portadas.limpiar_huerfanas(con) == 1
    assert portadas.ruta(usada) and portadas.ruta(huerfana) is None


def test_portada_de_elemento_borrado_se_limpia_al_arrancar(app, con):
    nombre = portadas.guardar_desde_bytes(imagen_png(10, 10))
    id_ = elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="X", portada=nombre))
    elementos.borrar(con, [id_])
    assert portadas.ruta(nombre)            # no se borra en el acto...
    portadas.limpiar_huerfanas(con)
    assert portadas.ruta(nombre) is None    # ...sino en la limpieza del arranque


def test_limpieza_respeta_portadas_de_las_copias(app, con):
    from bibliotecario.servicios import copias
    nombre = portadas.guardar_desde_bytes(imagen_png(10, 10))
    id_ = elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="X", portada=nombre))
    copias.copia_automatica(con, 10)
    elementos.borrar(con, [id_])
    assert portadas.limpiar_huerfanas(con) == 0
    assert portadas.ruta(nombre)  # la copia la necesita si se restaura


# ---------------------------------------------------------------- ficha

def test_ficha_autocompleta_sin_pisar_lo_escrito(app, con, mensajes, internet_simulado):
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    ficha.titulo.setText("Gomorra (mi título)")
    ficha.identificador.setText("978-84-8346-846-3")
    ficha.autocompletar()
    assert ficha.titulo.text() == "Gomorra (mi título)"          # no se pisa
    assert ficha.personas.valor() == [("Roberto Saviano", "Autor")]
    assert ficha.anio.value() == 2009 and ficha.idioma.currentText() == "Español"
    editorial = next(e for e in ficha.editores.values() if e.campo.clave == "editorial")
    paginas = next(e for e in ficha.editores.values() if e.campo.clave == "paginas")
    assert editorial.valor() == "Debolsillo" and paginas.valor() == "324"
    assert ficha.portada.nombre and ficha.boton_autocompletar.isEnabled()
    assert ficha.guardar()
    assert portadas.ruta(elementos.obtener(con, ficha.original.id).portada)


def test_ficha_autocompletar_isbn_invalido_o_no_encontrado(app, con, mensajes, internet_simulado):
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    ficha.identificador.setText("123")
    ficha.autocompletar()
    assert mensajes[-1][0] == "error"
    ficha.identificador.setText("84-406-2553-7")
    ficha.autocompletar()
    assert mensajes[-1][0] == "aviso" and "No se ha encontrado" in mensajes[-1][1]


def test_ficha_consulta_desactivada(app, con, mensajes, internet_simulado):
    configuracion.guardar({**configuracion.cargar(), "consultar_isbn": False})
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    ficha.identificador.setText(GOMORRA)
    ficha.autocompletar()
    assert internet_simulado == [] and "desactivada" in mensajes[-1][1]


def test_ficha_cancelar_borra_portada_nueva(app, con, mensajes):
    ficha = FichaElemento(con)
    ficha.portada.poner_bytes(imagen_png(20, 20))
    nombre = ficha.portada.nombre
    assert portadas.ruta(nombre)
    ficha.reject()
    assert portadas.ruta(nombre) is None


def test_ficha_cambiar_portada_limpia_las_descartadas(app, con, mensajes):
    vieja = portadas.guardar_desde_bytes(imagen_png(20, 20))
    id_ = elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="X", portada=vieja))
    ficha = FichaElemento(con, elemento_id=id_)
    ficha.portada.poner_bytes(imagen_png(30, 30, "blue"))
    probada = ficha.portada.nombre
    ficha.portada.poner_bytes(imagen_png(40, 40, "green"))
    nueva = ficha.portada.nombre
    assert ficha.guardar()
    assert portadas.ruta(probada) is None and portadas.ruta(nueva)   # la probada se borra ya
    assert elementos.obtener(con, id_).portada == nueva
    portadas.limpiar_huerfanas(con)
    assert portadas.ruta(vieja) is None                               # la anterior, al arrancar


def test_ficha_prestamo_con_fecha_de_hoy_y_devuelto(app, con, mensajes):
    from datetime import date
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    ficha.titulo.setText("Prestable")
    ficha.prestado_a.setText("Lucía")
    assert ficha.guardar()
    e = elementos.obtener(con, ficha.original.id)
    assert (e.prestado_a, e.fecha_prestamo) == ("Lucía", date.today().isoformat())
    assert busqueda.buscar(con, Filtros(texto="lucia"))  # se encuentra buscando a quién se prestó
    ficha.boton_devuelto.click()
    assert ficha.guardar()
    assert elementos.obtener(con, e.id).prestado_a == ""


# ---------------------------------------------------------------- ventana principal

def test_prestar_y_devolver_desde_la_lista(app, con, mensajes, monkeypatch):
    libro = tipos.por_nombre(con, "Libro").id
    ids = [elementos.guardar(con, Elemento(tipo_id=libro, titulo=t)) for t in ("A", "B")]
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("Pepe", True)))
    v = VentanaPrincipal(con)
    v.tabla.selectAll()
    v.prestar()
    assert all(elementos.obtener(con, i).prestado_a == "Pepe" for i in ids)
    v.f_prestados.setChecked(True)
    assert len(v.modelo.filas) == 2
    v.tabla.selectAll()
    v.devolver()
    assert len(v.modelo.filas) == 0


def test_tooltip_de_portada_en_la_lista(app, con, mensajes):
    nombre = portadas.guardar_desde_bytes(imagen_png(20, 20))
    elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="Con portada", portada=nombre))
    v = VentanaPrincipal(con)
    ayuda = v.modelo.data(v.modelo.index(0, 1), Qt.ItemDataRole.ToolTipRole)
    assert "<img" in ayuda and nombre in ayuda


# ---------------------------------------------------------------- alta masiva con ISBN

def test_alta_masiva_con_isbn_completa_y_guarda_portada(app, con, mensajes, internet_simulado):
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    alta = AltaMasiva(con, pb, tipos.por_nombre(con, "Libro").id)
    alta.identificador.setText("978-84-8346-846-3")
    alta.al_intro_identificador()
    assert alta.titulo.text() == "Gomorra" and alta.personas.text() == "Roberto Saviano"
    assert "Open Library" in alta.estado_consulta.text()
    assert alta.guardar_y_siguiente()
    e = elementos.obtener(con, alta.creados[0])
    editorial = next(c for c in tipos.campos(con, e.tipo_id) if c.clave == "editorial")
    assert e.valores[editorial.id] == "Debolsillo" and e.idioma == "Español" and portadas.ruta(e.portada)
    assert alta.datos_isbn is None


def test_alta_masiva_isbn_editado_descarta_datos(app, con, mensajes, internet_simulado):
    alta = AltaMasiva(con, None, tipos.por_nombre(con, "Libro").id)
    alta.identificador.setText(GOMORRA)
    alta.al_intro_identificador()
    alta.identificador.textEdited.emit("otro")
    assert alta.datos_isbn is None


# ---------------------------------------------------------------- configuración

def test_configuracion_guardar_cargar_y_archivo_danado():
    ajustes = configuracion.cargar()
    assert ajustes["copias_a_conservar"] == 10
    configuracion.guardar({**ajustes, "copias_a_conservar": 3, "desconocida": 1})
    assert configuracion.cargar()["copias_a_conservar"] == 3
    assert "desconocida" not in json.loads(rutas.ruta_configuracion().read_text(encoding="utf-8"))
    rutas.ruta_configuracion().write_text("{roto", encoding="utf-8")
    assert configuracion.cargar()["copias_a_conservar"] == 10
