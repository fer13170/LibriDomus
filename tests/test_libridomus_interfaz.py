"""LibriDomus: aspecto (tema, escala, fuente, iconos), orden de las plantas, migración 2,
columnas configurables y panel de detalle."""

import re
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from libridomus import rutas
from libridomus.datos import conexion, elementos, esquema, tipos, ubicaciones
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun, tema
from libridomus.interfaz.editor_tipos import ICONOS_TIPO
from libridomus.interfaz.editor_ubicaciones import ICONOS_UBICACION
from libridomus.interfaz.preferencias import Preferencias
from libridomus.interfaz.ventana_principal import VentanaPrincipal
from libridomus.servicios import configuracion

CODIGO = Path(__file__).resolve().parent.parent / "libridomus"


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


@pytest.fixture(autouse=True)
def tema_por_defecto(app):
    yield
    tema.aplicar(app, "claro", 1.0, "Segoe UI")


def plantas(con) -> list[str]:
    casa = ubicaciones.buscar_por_codigo(con, "CASA").id
    return [u.nombre for u in ubicaciones.hijos(con, casa)]


# ---------------------------------------------------------------- orden de las plantas

def test_orden_de_plantas_desde_el_menu_del_arbol_persiste(app, con, mensajes):
    v = VentanaPrincipal(con)
    buhardilla = ubicaciones.buscar_por_codigo(con, "BUH").id
    v.desplazar_ubicacion(buhardilla, -1)
    v.desplazar_ubicacion(buhardilla, -1)
    v.desplazar_ubicacion(buhardilla, -1)
    v.desplazar_ubicacion(buhardilla, -1)  # ya es la primera: no hace nada
    assert plantas(con) == ["Buhardilla", "Sótano", "Planta baja", "Planta alta"]
    con.close()
    otra = conexion.abrir()  # al volver a abrir el programa se conserva el orden
    assert plantas(otra) == ["Buhardilla", "Sótano", "Planta baja", "Planta alta"]
    otra.close()


def test_orden_de_plantas_arrastrando_en_el_arbol_principal(app, con, mensajes):
    v = VentanaPrincipal(con)
    assert v.arbol.al_mover is not None  # el árbol principal admite arrastrar para ordenar
    casa = ubicaciones.buscar_por_codigo(con, "CASA").id
    sotano = ubicaciones.buscar_por_codigo(con, "SOT").id
    v._mover_ubicacion(sotano, casa, 3)  # lo que hace el árbol al soltar el Sótano al final
    assert plantas(con) == ["Planta baja", "Planta alta", "Buhardilla", "Sótano"]
    assert v.arbol.id_actual() == sotano


def test_el_arbol_muestra_las_plantas_en_su_orden(app, con, mensajes):
    ubicaciones.mover(con, ubicaciones.buscar_por_codigo(con, "PA").id, ubicaciones.buscar_por_codigo(con, "CASA").id, 0)
    v = VentanaPrincipal(con)
    casa_item = next(i for i in v.arbol.todos_los_items() if i.text(0) == "Casa")
    assert [casa_item.child(n).text(0) for n in range(casa_item.childCount())] == \
        ["Planta alta", "Sótano", "Planta baja", "Buhardilla"]


# ---------------------------------------------------------------- migración 2

def test_migracion_2_cambia_emojis_por_iconos(carpeta_datos):
    ruta = rutas.ruta_base_datos()
    bruta = sqlite3.connect(ruta)
    bruta.executescript(esquema.MIGRACION_1)
    bruta.execute("INSERT INTO tipo_ubicacion (nombre, prefijo, orden) VALUES ('Caja', 'CAJ', 0), ('Baúl', 'BAU', 1)")
    bruta.execute("INSERT INTO tipo_elemento (nombre, icono) VALUES ('Libro', '📖'), ('Propio', '🎲')")
    bruta.execute("PRAGMA user_version = 1")
    bruta.commit()
    bruta.close()
    con = conexion.abrir()
    assert conexion.version(con) == esquema.VERSION_ESQUEMA  # migra hasta la última versión
    assert dict(con.execute("SELECT nombre, icono FROM tipo_ubicacion").fetchall()) == {"Caja": "box", "Baúl": "map-pin"}
    assert dict(con.execute("SELECT nombre, icono FROM tipo_elemento").fetchall()) == {"Libro": "book", "Propio": "🎲"}
    assert list(rutas.carpeta_copias().glob("antes_de_migrar_v1_*.db"))  # copia previa a migrar
    con.close()


def test_base_nueva_trae_iconos_de_ubicacion(con):
    iconos = dict(con.execute("SELECT nombre, icono FROM tipo_ubicacion").fetchall())
    assert iconos["Planta"] == "layers" and iconos["Balda"] == "rows-3"


# ---------------------------------------------------------------- iconos

def test_todos_los_iconos_citados_existen():
    citados = set(ICONOS_TIPO) | set(ICONOS_UBICACION)
    citados |= {f[2] for f in __import__("libridomus.datos.semillas", fromlist=["x"]).TIPOS_UBICACION}
    citados |= {d["icono"] for d in __import__("libridomus.datos.semillas", fromlist=["x"]).TIPOS_ELEMENTO}
    citados |= set(re.findall(r"THEN '([a-z0-9-]+)'", esquema.MIGRACION_2)) | {"map-pin"}
    no_iconos = {"texto", "texto_suave", "primario", "primario_texto", "peligro", "plano", "enlace", "acento",
                 "borde_fuerte", "seleccion_texto", "icono"}
    patron = re.compile(r'(?:icono|boton|_accion|A)\((?:[^()]|\([^()]*\))*\)')
    for archivo in (CODIGO / "interfaz").glob("*.py"):
        for llamada in patron.findall(archivo.read_text(encoding="utf-8")):
            for cadena in re.findall(r'"([a-z0-9]+(?:-[a-z0-9]+)*)"', llamada):
                if cadena not in no_iconos:
                    citados.add(cadena)
    faltan = sorted(n for n in citados if not tema.existe_icono(n))
    assert not faltan, f"Iconos que no están en recursos/iconos: {faltan}"


def test_icono_desconocido_se_dibuja_como_texto(app):
    assert not tema.icono("🎲").isNull()
    assert not tema.icono("book", "primario").isNull()


# ---------------------------------------------------------------- tema, escala y fuente

def test_aplicar_tema_oscuro_escala_y_fuente(app):
    tema.aplicar(app, "oscuro", 1.3, "Arial")
    assert tema.estado.nombre == "oscuro"
    assert app.font().family() == "Arial" and abs(app.font().pointSizeF() - tema.PUNTOS_BASE * 1.3) < 0.01
    assert tema.color("fondo") == tema.PALETAS["oscuro"]["fondo"]
    assert tema.PALETAS["oscuro"]["fondo"] in app.styleSheet()
    assert tema.px(10) == 13


def test_ventana_cambia_escala_y_tema_y_lo_recuerda(app, con, mensajes):
    v = VentanaPrincipal(con)
    v.cambiar_escala(+1)
    assert configuracion.obtener("escala") == 1.15 and tema.estado.escala == 1.15
    v.cambiar_escala(+1)
    v.cambiar_escala(+1)
    v.cambiar_escala(+1)
    v.cambiar_escala(+1)
    assert configuracion.obtener("escala") == 1.5  # no pasa del máximo
    v.cambiar_escala(0)
    assert configuracion.obtener("escala") == 1.0
    v.cambiar_tema("oscuro")
    assert configuracion.obtener("tema") == "oscuro" and tema.estado.nombre == "oscuro"


def test_preferencias_vista_previa_y_cancelar(app, con):
    p = Preferencias()
    p.tema.setCurrentIndex(p.tema.findData("oscuro"))
    assert tema.estado.nombre == "oscuro"          # se ve al momento
    p.reject()
    assert tema.estado.nombre == "claro"            # cancelar deshace
    p = Preferencias()
    p.escala.setValue(3)
    p.guardar()
    assert configuracion.obtener("escala") == tema.ESCALAS[3][1]


# ---------------------------------------------------------------- columnas y panel de detalle

def test_columnas_ocultas_se_recuerdan(app, con, mensajes):
    v = VentanaPrincipal(con)
    assert v.tabla.isColumnHidden(5)  # Estado, oculta por defecto
    v._mostrar_columna(5, True)
    v._mostrar_columna(2, False)
    assert configuracion.obtener("columnas_ocultas") == [2]
    v2 = VentanaPrincipal(con)
    assert v2.tabla.isColumnHidden(2) and not v2.tabla.isColumnHidden(5)


def test_panel_de_detalle(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro").id
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    id_ = elementos.guardar(con, Elemento(tipo_id=libro, titulo="Gomorra", ubicacion_id=pb, prestado_a="Lucía",
                                          personas=[("Roberto Saviano", "Autor")]))
    elementos.guardar(con, Elemento(tipo_id=libro, titulo="Otro"))
    v = VentanaPrincipal(con)
    v.seleccionar_elemento(id_)
    textos = " ".join(w.text() for w in v.detalle.findChildren(type(v.ruta_actual)))
    assert "Gomorra" in textos and "Roberto Saviano" in textos and "Lucía" in textos and "Planta baja" in textos
    v.tabla.selectAll()
    assert v.detalle.ids == sorted(v.detalle.ids) and len(v.detalle.ids) == 2
    v.mostrar_panel(False)
    assert not v.detalle.isVisibleTo(v) and configuracion.obtener("panel_detalle") is False


def test_pantalla_vacia_y_sin_resultados(app, con, mensajes):
    v = VentanaPrincipal(con)
    assert v.pila.currentWidget() is v.vacio and "bienvenida" in v.vacio.titulo.text()
    assert not v.barra_filtros.isVisibleTo(v)
    elementos.guardar(con, Elemento(tipo_id=tipos.por_nombre(con, "Libro").id, titulo="Uno"))
    v.refrescar_todo()
    assert v.pila.currentWidget() is v.tabla
    v.busqueda.setText("zzzz")
    v.refrescar_resultados()
    assert v.pila.currentWidget() is v.vacio and v.vacio.titulo.text() == "No hay resultados"
