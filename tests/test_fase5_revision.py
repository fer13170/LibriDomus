"""Fase 5: pruebas de regresión de los errores encontrados en la revisión de código
y de la optimización de la ordenación."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from libridomus import rutas
from libridomus.datos import conexion, elementos, tipos
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun, ventana_principal
from libridomus.interfaz.alta_masiva import AltaMasiva
from libridomus.interfaz.ficha_elemento import FichaElemento
from libridomus.interfaz.ventana_principal import VentanaPrincipal
from libridomus.servicios import busqueda, copias, isbn, portadas
from libridomus.servicios.busqueda import Filtros


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mensajes(monkeypatch):
    registro = []
    monkeypatch.setattr(comun, "confirmar", lambda _p, m: registro.append(("confirmar", m)) or True)
    monkeypatch.setattr(comun, "aviso", lambda _p, m: registro.append(("aviso", m)))
    monkeypatch.setattr(comun, "error", lambda _p, m: registro.append(("error", m)))
    return registro


def portada_nueva() -> str:
    imagen = QImage(10, 10, QImage.Format.Format_RGB32)
    imagen.fill(QColor("red"))
    return portadas.guardar_imagen(imagen)


# ---------------------------------------------------------------- 1. campos ocultos

def test_guardar_ficha_conserva_valores_de_campos_ocultos(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    editorial = next(c for c in libro.campos if c.clave == "editorial")
    id_ = elementos.guardar(con, Elemento(tipo_id=libro.id, titulo="X", valores={editorial.id: "Anagrama"}))
    libro.campos = [c for c in libro.campos if c.id != editorial.id]  # quitar = ocultar
    tipos.guardar(con, libro)
    ficha = FichaElemento(con, elemento_id=id_)
    assert editorial.id not in ficha.editores
    ficha.notas.setPlainText("cambio")
    assert ficha.guardar()
    assert elementos.obtener(con, id_).valores[editorial.id] == "Anagrama"


def test_cambiar_de_tipo_no_arrastra_valores_del_tipo_anterior(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    paginas = next(c for c in libro.campos if c.clave == "paginas")
    id_ = elementos.guardar(con, Elemento(tipo_id=libro.id, titulo="X", valores={paginas.id: "300"}))
    ficha = FichaElemento(con, elemento_id=id_)
    ficha.tipo.setCurrentIndex(ficha.tipo.findData(tipos.por_nombre(con, "Disco").id))
    assert ficha.guardar()
    assert paginas.id not in elementos.obtener(con, id_).valores


# ---------------------------------------------------------------- 2. rutas con # y %

@pytest.fixture
def datos_con_simbolos(tmp_path, monkeypatch):
    carpeta = tmp_path / "Libros#2 al 100%" / "datos"
    monkeypatch.setenv("LIBRIDOMUS_DATOS", str(carpeta))
    con = conexion.abrir()
    yield con
    con.close()


def test_limpieza_respeta_copias_en_rutas_con_simbolos(app, datos_con_simbolos):
    con = datos_con_simbolos
    nombre = portada_nueva()
    id_ = elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="X", portada=nombre))
    copias.copia_automatica(con, 5)
    elementos.borrar(con, [id_])
    assert portadas.limpiar_huerfanas(con) == 0
    assert portadas.ruta(nombre)
    assert copias.validar_base_datos(next(rutas.carpeta_copias().glob("auto_*.db"))) >= 1


def test_copia_ilegible_impide_borrar_portadas(app, con):
    nombre = portada_nueva()
    (rutas.carpeta_copias() / "rota.db").write_bytes(b"basura" * 100)
    assert portadas.limpiar_huerfanas(con) == 0
    assert portadas.ruta(nombre)


# ---------------------------------------------------------------- 3. restauración atómica

def test_restaurar_que_falla_al_sustituir_deja_la_base_intacta(con, monkeypatch):
    elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="Original"))
    copia = copias.copia_automatica(con, 5)
    con.execute("UPDATE elemento SET titulo = 'Modificado'")

    def fallo(*_a):
        raise PermissionError("archivo bloqueado")
    monkeypatch.setattr(copias.os, "replace", fallo)
    with pytest.raises(PermissionError):
        copias.restaurar(con, copia)
    nueva = conexion.abrir()
    assert nueva.execute("SELECT titulo FROM elemento").fetchone()[0] == "Modificado"
    assert not list(rutas.carpeta_datos().glob("*.restaurando"))
    nueva.close()


def test_ventana_reinicia_si_la_restauracion_falla_con_la_conexion_cerrada(app, con, mensajes, monkeypatch):
    copia = copias.copia_automatica(con, 5)
    monkeypatch.setattr(copias.os, "replace", lambda *_a: (_ for _ in ()).throw(PermissionError("bloqueado")))
    reinicios = []
    monkeypatch.setattr(ventana_principal, "reiniciar", lambda: reinicios.append(True))
    monkeypatch.setattr(ventana_principal.DialogoRestaurar, "exec",
                        lambda self: setattr(self, "elegida", str(copia)) or 1)
    v = VentanaPrincipal(con)
    v.restaurar_copia()
    assert v.restaurado and reinicios == [True]
    assert "no se han modificado" in mensajes[-1][1]


# ---------------------------------------------------------------- 4. respuestas de ISBN atrasadas

@pytest.fixture
def respuestas_diferidas(monkeypatch):
    """Guarda las consultas en segundo plano para resolverlas cuando la prueba quiera."""
    pendientes = []
    monkeypatch.setattr(comun, "en_segundo_plano", lambda f, ok, ko: pendientes.append((f, ok, ko)))
    respuestas = {
        "https://openlibrary.org/isbn/9788483468463.json": json.dumps({"title": "Gomorra"}).encode()}
    monkeypatch.setattr(isbn, "descargar", lambda url, **_: respuestas.get(url))

    def resolver():
        for f, ok, _ko in pendientes:
            ok(f())
        pendientes.clear()
    return resolver


def test_alta_masiva_descarta_respuesta_de_isbn_anterior(app, con, mensajes, respuestas_diferidas):
    alta = AltaMasiva(con, None, tipos.por_nombre(con, "Libro").id)
    alta.identificador.setText("978-84-8346-846-3")
    alta.al_intro_identificador()
    alta.titulo.setText("Escrito a mano")
    assert alta.guardar_y_siguiente()           # se pasa al siguiente sin esperar
    alta.identificador.setText("84-406-2553-7")  # otro libro
    respuestas_diferidas()                       # llega tarde la respuesta del primero
    assert alta.titulo.text() == "" and alta.datos_isbn is None


def test_ficha_descarta_respuesta_si_cambio_el_isbn(app, con, mensajes, respuestas_diferidas):
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    ficha.identificador.setText("9788483468463")
    ficha.autocompletar()
    ficha.identificador.setText("8440625537")
    respuestas_diferidas()
    assert ficha.titulo.text() == "" and ficha.identificador.text() == "8440625537"
    assert ficha.boton_autocompletar.isEnabled()


def test_ficha_aplica_respuesta_vigente(app, con, mensajes, respuestas_diferidas):
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    ficha.identificador.setText("978-84-8346-846-3")
    ficha.autocompletar()
    respuestas_diferidas()
    assert ficha.titulo.text() == "Gomorra"


# ---------------------------------------------------------------- 5. solo exclusiones

def test_busqueda_solo_con_exclusiones(con):
    libro = tipos.por_nombre(con, "Libro").id
    for t in ("Hola mundo", "Adiós", "Hasta luego"):
        elementos.guardar(con, Elemento(tipo_id=libro, titulo=t))
    titulos = lambda q: sorted(r.titulo for r in busqueda.buscar(con, Filtros(texto=q)))  # noqa: E731
    assert titulos("-hola") == ["Adiós", "Hasta luego"]
    assert titulos("-hola -adios") == ["Hasta luego"]
    assert busqueda.construir_exclusion("-hola -adios") == '"hola"* OR "adios"*'
    assert busqueda.construir_exclusion("hola -adios") is None


# ---------------------------------------------------------------- ordenación de la tabla

def test_ordenar_columnas_y_mantener_orden_al_refrescar(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro").id
    for titulo, autor, anio in [("b", "Zoe", 2001), ("Á", "Álvaro", 1999), ("c", "Marta", 1850)]:
        elementos.guardar(con, Elemento(tipo_id=libro, titulo=titulo, anio=anio, personas=[(autor, "Autor")]))
    v = VentanaPrincipal(con)
    assert [r.titulo for r in v.modelo.filas] == ["Á", "b", "c"]    # sin acentos por defecto
    v.tabla.sortByColumn(3, Qt.SortOrder.AscendingOrder)
    assert [r.anio for r in v.modelo.filas] == [1850, 1999, 2001]
    v.tabla.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    assert [r.creadores for r in v.modelo.filas] == ["Zoe", "Marta", "Álvaro"]
    v.refrescar_resultados()
    assert [r.creadores for r in v.modelo.filas] == ["Zoe", "Marta", "Álvaro"]
