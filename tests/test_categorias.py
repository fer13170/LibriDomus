"""Versión 1.4: catálogo de categorías y propuesta automática a partir de los datos del ISBN."""

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from libridomus import rutas, texto
from libridomus.datos import categorias, conexion, elementos, esquema, tipos
from libridomus.datos.categorias import ErrorCategoria
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun
from libridomus.interfaz.alta_masiva import AltaMasiva
from libridomus.interfaz.categorias import DialogoElegirCategorias, EditorCategorias
from libridomus.interfaz.ficha_elemento import FichaElemento
from libridomus.interfaz.ventana_principal import VentanaPrincipal
from libridomus.servicios import busqueda, clasificar, importar
from libridomus.servicios.busqueda import Filtros
from libridomus.servicios.isbn import DatosLibro


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


def libro(con) -> int:
    return tipos.por_nombre(con, "Libro").id


# ---------------------------------------------------------------- catálogo

def test_catalogo_inicial_de_categorias(con):
    nombres = categorias.nombres(con)
    assert len(nombres) == 44
    for esperada in ("Novela histórica", "Historia del arte", "Humor", "Ciencia ficción", "Infantil y juvenil"):
        assert esperada in nombres
    assert nombres == sorted(nombres, key=texto.clave_orden)  # alfabético sin tener en cuenta las tildes


def test_crear_renombrar_y_borrar_categorias(con):
    nueva = categorias.crear(con, "  Juegos   de mesa ")
    assert categorias.buscar(con, "juegos de MESA").id == nueva
    with pytest.raises(ErrorCategoria, match="Ya existe"):
        categorias.crear(con, "historia DEL arte")  # sin importar mayúsculas ni acentos
    with pytest.raises(ErrorCategoria):
        categorias.crear(con, "   ")
    id_ = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="Catán", categorias=["Juegos de mesa"]))
    categorias.renombrar(con, nueva, "Juegos")
    assert elementos.obtener(con, id_).categorias == ["Juegos"]
    assert [r.id for r in busqueda.buscar(con, Filtros(texto="juegos"))] == [id_]  # el índice se actualiza
    assert categorias.borrar(con, nueva) == 1
    assert elementos.obtener(con, id_).categorias == []  # el elemento sigue, sin la categoría
    assert busqueda.buscar(con, Filtros(texto="juegos")) == []


def test_elemento_con_varias_categorias_busqueda_y_filtro(con):
    a = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="El nombre de la rosa",
                                        categorias=["Novela histórica", "novela negra y SUSPENSE", "Novela histórica"]))
    b = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="Gombrich", categorias=["Historia del arte"]))
    assert elementos.obtener(con, a).categorias == ["Novela histórica", "Novela negra y suspense"]
    historica = categorias.buscar(con, "Novela histórica").id
    assert [r.id for r in busqueda.buscar(con, Filtros(categoria_id=historica))] == [a]
    assert [r.id for r in busqueda.buscar(con, Filtros(texto="historia arte"))] == [b]
    assert busqueda.buscar(con, Filtros(ids=[a]))[0].categorias.count(",") == 1


def test_categoria_desconocida_se_crea_al_guardar(con):
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="X", categorias=["Astronomía"]))
    assert categorias.buscar(con, "astronomia") is not None


def test_migracion_3_en_una_base_de_datos_antigua(carpeta_datos):
    bruta = sqlite3.connect(rutas.ruta_base_datos())
    bruta.executescript(esquema.MIGRACION_1 + esquema.MIGRACION_2)
    bruta.execute("PRAGMA user_version = 2")
    bruta.commit()
    bruta.close()
    con = conexion.abrir()
    assert conexion.version(con) == 3
    assert len(categorias.nombres(con)) == 44
    con.close()


# ---------------------------------------------------------------- propuesta automática

@pytest.mark.parametrize("materias, esperadas", [
    (["FH - Obra De Misterio Y Suspense"], ["Novela negra y suspense"]),
    (["FA - Ficción Moderna Y Contemporánea"], ["Novela"]),
    (["FV - Ficción histórica", "FA - Ficción moderna"], ["Novela histórica"]),     # sobra «Novela»
    (["YFB - Ficción general (infantil/juvenil)", "2ADS - Español"], ["Infantil y juvenil"]),
    (["BGR - Biografía: realeza", "BT - Historias reales"], ["Biografías y memorias"]),
    (["AC - Historia del arte", "1D - Europa", "3JJP - Postguerra"], ["Historia del arte"]),
    (["Novelas rosas", "Novelas psicológicas"], ["Romántica"]),                      # BNE
    (["Fiction / Science Fiction / General"], ["Ciencia ficción"]),                  # Google Books
    (["Cocina española"], ["Gastronomía y cocina"]),
    (["Accessible book", "Protected DAISY"], []),                                    # ruido de Open Library
])
def test_proponer_categorias(con, materias, esperadas):
    assert clasificar.proponer(materias, categorias.nombres(con)) == esperadas


def test_no_se_proponen_categorias_que_el_usuario_ha_borrado(con):
    categorias.borrar(con, categorias.buscar(con, "Romántica").id)
    assert clasificar.proponer(["FR - Romántica"], categorias.nombres(con)) == []


def test_la_ficha_propone_categorias_del_isbn(app, con):
    f = FichaElemento(con, tipo_id=libro(con))
    f.aplicar_datos_isbn(DatosLibro(isbn="9791387512446", titulo="La inquilina",
                                    materias=["FH - Obra De Misterio Y Suspense"]))
    assert f.categorias.valor() == ["Novela negra y suspense"]
    assert f.guardar()
    assert elementos.obtener(con, f.original.id).categorias == ["Novela negra y suspense"]
    # Si el usuario ya ha elegido categoría, el ISBN no la cambia.
    g = FichaElemento(con, tipo_id=libro(con))
    g.categorias.establecer(["Humor"])
    g.aplicar_datos_isbn(DatosLibro(isbn="1", titulo="T", materias=["FH - Misterio"]))
    assert g.categorias.valor() == ["Humor"]


def test_la_ficha_sencilla_muestra_las_categorias(app, con):
    f = FichaElemento(con, tipo_id=libro(con))
    f.show()
    assert f.categorias.isVisible()


def test_alta_masiva_con_categoria_fija_y_del_isbn(app, con, mensajes):
    a = AltaMasiva(con, None, libro(con))
    a.categoria.setCurrentIndex(a.categoria.findData("Novela"))
    a.titulo.setText("Uno")
    assert a.guardar_y_siguiente()
    a.datos_isbn = DatosLibro(isbn="9788400000000", titulo="Dos", materias=["FU - Humor"])
    a.titulo.setText("Dos")
    assert a.guardar_y_siguiente()
    uno, dos = (elementos.obtener(con, i) for i in a.creados)
    assert uno.categorias == ["Novela"] and dos.categorias == ["Humor", "Novela"]


# ---------------------------------------------------------------- ventanas

def test_filtro_por_categoria_en_la_ventana(app, con, mensajes):
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="A", categorias=["Poesía"]))
    elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="B", categorias=["Teatro"]))
    v = VentanaPrincipal(con)
    v.show()
    assert v.f_categoria.isVisible()  # también en el modo sencillo
    v.f_categoria.setCurrentIndex(v.f_categoria.findText("Poesía"))
    assert v.modelo.rowCount() == 1 and v.modelo.resultado(0).titulo == "A"
    assert v.modelo.data(v.modelo.index(0, 7)) == "Poesía"  # columna Categoría
    v.quitar_filtros()
    assert v.modelo.rowCount() == 2


def test_editor_de_categorias(app, con, mensajes):
    id_ = elementos.guardar(con, Elemento(tipo_id=libro(con), titulo="A", categorias=["Poesía"]))
    e = EditorCategorias(con)
    assert e.nueva("Juegos de mesa") and not e.nueva("juegos DE mesa")
    assert ("error", "Ya existe la categoría «Juegos de mesa».") in mensajes
    e.cargar("Poesía")
    assert e.renombrar("Poesía y verso")
    assert elementos.obtener(con, id_).categorias == ["Poesía y verso"]
    e.cargar("Poesía y verso")
    assert e.borrar() and e.hubo_cambios
    assert any("Se quitará de 1 elemento" in m for _, m in mensajes)


def test_elegir_categorias_y_crear_una_nueva(app, con, mensajes):
    d = DialogoElegirCategorias(con, ["Novela"])
    assert d.elegidas() == ["Novela"]
    assert d.nueva("Juegos de mesa")
    assert sorted(d.elegidas()) == ["Juegos de mesa", "Novela"]  # la nueva queda marcada


# ---------------------------------------------------------------- importar

def test_importar_columna_de_genero(con):
    tabla = importar.Tabla(["Título", "Género"], [["A", "novela histórica, Humor"], ["B", "Astronomía"]])
    mapa = {n: importar.sugerir_destino(c, importar.destinos(con)) for n, c in enumerate(tabla.cabeceras)}
    assert mapa == {0: "titulo", 1: "categorias"}
    informe = importar.importar(con, tabla, mapa, libro(con))
    a, b = (elementos.obtener(con, i) for i in informe.creados)
    assert a.categorias == ["Humor", "Novela histórica"] and b.categorias == ["Astronomía"]
    assert informe.categorias_nuevas == ["Astronomía"]
