"""Fase 2: filtros, alta masiva, arrastrar para mover y editor de tipos."""

import pytest
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtWidgets import QApplication

from libridomus.datos import elementos, tipos, ubicaciones
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun
from libridomus.interfaz.alta_masiva import AltaMasiva
from libridomus.interfaz.arbol_ubicaciones import ID_SIN_UBICACION
from libridomus.interfaz.editor_tipos import COL_OCULTO, COL_OPCIONES, EditorTipos
from libridomus.interfaz.modelo_resultados import MIME_ELEMENTOS
from libridomus.interfaz.ventana_principal import VentanaPrincipal


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


def codigo(con, c):
    return ubicaciones.buscar_por_codigo(con, c).id


# ---------------------------------------------------------------- filtros

def test_filtros_de_la_ventana_principal(app, con, mensajes):
    libro, disco = tipos.por_nombre(con, "Libro").id, tipos.por_nombre(con, "Disco").id
    elementos.guardar(con, Elemento(tipo_id=libro, titulo="Libro leído", consumido=True, idioma="Inglés",
                                    etiquetas=["favorito"]))
    elementos.guardar(con, Elemento(tipo_id=libro, titulo="Libro pendiente", estado="Regular"))
    elementos.guardar(con, Elemento(tipo_id=disco, titulo="Disco prestado", prestado_a="Luis"))
    v = VentanaPrincipal(con)
    titulos = lambda: sorted(r.titulo for r in v.modelo.filas)  # noqa: E731

    v.f_tipo.setCurrentIndex(v.f_tipo.findData(disco))
    assert titulos() == ["Disco prestado"]
    v.quitar_filtros()
    v.f_pendientes.setChecked(True)
    assert titulos() == ["Disco prestado", "Libro pendiente"]
    v.f_tipo.setCurrentIndex(v.f_tipo.findData(libro))
    assert titulos() == ["Libro pendiente"]
    v.quitar_filtros()
    v.f_etiqueta.setCurrentIndex(v.f_etiqueta.findData("favorito"))
    assert titulos() == ["Libro leído"]
    v.quitar_filtros()
    v.f_idioma.setCurrentIndex(v.f_idioma.findData("Inglés"))
    assert titulos() == ["Libro leído"]
    v.quitar_filtros()
    v.f_estado.setCurrentIndex(v.f_estado.findData("Regular"))
    assert titulos() == ["Libro pendiente"]
    v.quitar_filtros()
    v.f_prestados.setChecked(True)
    assert titulos() == ["Disco prestado"]
    v.quitar_filtros()
    assert len(titulos()) == 3


def test_filtros_se_conservan_al_refrescar(app, con, mensajes):
    disco = tipos.por_nombre(con, "Disco").id
    v = VentanaPrincipal(con)
    v.f_tipo.setCurrentIndex(v.f_tipo.findData(disco))
    v.refrescar_todo()
    assert v.f_tipo.currentData() == disco


# ---------------------------------------------------------------- arrastrar al árbol

def test_arrastrar_elementos_al_arbol_los_mueve(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro").id
    ids = [elementos.guardar(con, Elemento(tipo_id=libro, titulo=t)) for t in ("A", "B")]
    v = VentanaPrincipal(con)
    datos = v.modelo.mimeData([v.modelo.index(0, 0), v.modelo.index(1, 1)])
    assert bytes(datos.data(MIME_ELEMENTOS)).decode() == ",".join(map(str, sorted(ids)))
    # Lo que hace el árbol al soltar: llamar a la función de mover con los ids y el destino.
    v.mover_a(ids, codigo(con, "SOT"))
    assert all(elementos.obtener(con, i).ubicacion_id == codigo(con, "SOT") for i in ids)
    v.mover_a(ids[:1], None)
    assert elementos.obtener(con, ids[0]).ubicacion_id is None


def test_arbol_valida_destino_de_soltado(app, con, mensajes):
    v = VentanaPrincipal(con)
    arbol = v.arbol
    assert not arbol.seleccionar(ID_SIN_UBICACION)  # sin elementos no aparece "Sin ubicación"
    arbol.seleccionar(codigo(con, "PB"))
    punto = arbol.visualItemRect(arbol.currentItem()).center()
    assert arbol.destino_elementos(punto) == (True, codigo(con, "PB"))
    datos = QMimeData()
    datos.setData(MIME_ELEMENTOS, b"1")
    assert datos.hasFormat(MIME_ELEMENTOS)


# ---------------------------------------------------------------- alta masiva

def test_alta_masiva_registra_seguidos_y_mantiene_lo_fijo(app, con, mensajes):
    balda = codigo(con, "PB")
    libro = tipos.por_nombre(con, "Libro").id
    alta = AltaMasiva(con, balda, libro)
    assert alta.usar_codigo.isChecked()  # los libros empiezan por el ISBN
    alta.etiquetas.setText("cómic")
    alta.estado.setCurrentText("Bueno")
    for titulo, autor, isbn in [("Gomorra", "Roberto Saviano", "978-84-8346-846-3"),
                                ("María la jabalina", "Cristina Durán; Miguel Á. Giner", "")]:
        alta.identificador.setText(isbn)
        alta.titulo.setText(titulo)
        alta.personas.setText(autor)
        assert alta.guardar_y_siguiente()
        assert alta.titulo.text() == "" and alta.etiquetas.text() == "cómic"
    assert len(alta.creados) == 2 and alta.lista.count() == 2
    e = elementos.obtener(con, alta.creados[1])
    assert e.ubicacion_id == balda and e.etiquetas == ["cómic"] and e.estado == "Bueno"
    assert e.personas == [("Cristina Durán", "Autor"), ("Miguel Á. Giner", "Autor")]
    alta.deshacer_ultimo()
    assert elementos.obtener(con, e.id) is None and len(alta.creados) == 1


def test_alta_masiva_sin_titulo_no_guarda(app, con, mensajes):
    alta = AltaMasiva(con, codigo(con, "PB"), tipos.por_nombre(con, "Libro").id)
    assert not alta.guardar_y_siguiente()
    assert mensajes[-1][0] == "error"


def test_alta_masiva_tipo_personal_sin_codigo(app, con, mensajes):
    alta = AltaMasiva(con, None, tipos.por_nombre(con, "Álbum de fotos").id)
    assert not alta.usar_codigo.isChecked()
    assert alta.etiqueta_personas.text() == "Aparece:"
    alta.titulo.setText("Navidad 1990")
    assert alta.guardar_y_siguiente()
    alta.titulo.setText("Navidad 1991")
    assert alta.guardar_y_siguiente()
    # La pregunta de "sin ubicación" solo se hace una vez
    assert sum(1 for t, m in mensajes if t == "confirmar" and "sin ubicación" in m) == 1


# ---------------------------------------------------------------- editor de tipos

def test_editor_tipos_crear_tipo_con_campos(app, con, mensajes):
    ed = EditorTipos(con)
    ed.nuevo_tipo()
    ed.nombre.setText("Juego de mesa")
    ed.icono.setCurrentIndex(ed.icono.findData("dices"))
    ed.roles.setText("Autor; Ilustrador")
    ed.anadir_campo(tipos.Campo(None, "", "Jugadores", "texto"))
    ed.anadir_campo(tipos.Campo(None, "", "Duración", "lista"))
    ed.tabla.item(1, COL_OPCIONES).setText("Corta; Media; Larga")
    assert ed.guardar()
    t = tipos.por_nombre(con, "Juego de mesa")
    assert t.roles == ["Autor", "Ilustrador"] and t.icono == "dices"
    assert [(c.etiqueta, c.opciones) for c in t.campos] == [("Jugadores", []), ("Duración", ["Corta", "Media", "Larga"])]
    assert ed.hubo_cambios


def test_editor_tipos_ampliar_predefinido_reordenar_y_ocultar(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    ed = EditorTipos(con)
    ed._mostrar(libro.id)
    assert not ed.b_borrar.isEnabled()  # predefinido
    n = ed.tabla.rowCount()
    ed.anadir_campo(tipos.Campo(None, "", "Dedicatoria", "texto_largo"))
    ed.tabla.setCurrentCell(n, 0)
    ed.desplazar_campo(-1)
    ed.tabla.item(0, COL_OCULTO).setCheckState(Qt.CheckState.Checked)
    assert ed.guardar()
    campos = tipos.campos(con, libro.id, incluir_ocultos=True)
    assert [c.etiqueta for c in campos][-2:] == ["Dedicatoria", "Encuadernación"]
    assert campos[0].oculto and campos[0].clave == "editorial"


def test_editor_tipos_quitar_campo_lo_oculta_y_conserva_valores(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    editorial = next(c for c in libro.campos if c.clave == "editorial")
    id_ = elementos.guardar(con, Elemento(tipo_id=libro.id, titulo="X", valores={editorial.id: "Planeta"}))
    ed = EditorTipos(con)
    ed._mostrar(libro.id)
    ed.tabla.setCurrentCell(0, 0)
    ed.quitar_campo()
    assert ed.guardar()
    assert editorial.id not in [c.id for c in tipos.campos(con, libro.id)]
    assert elementos.obtener(con, id_).valores[editorial.id] == "Planeta"


def test_editor_tipos_errores(app, con, mensajes):
    ed = EditorTipos(con)
    ed.nuevo_tipo()
    assert not ed.guardar()  # sin nombre
    ed.nombre.setText("Libro")
    assert not ed.guardar()  # repetido
    ed.nombre.setText("Nuevo")
    ed.anadir_campo(tipos.Campo(None, "", "Color", "lista"))
    assert not ed.guardar()  # lista sin opciones
    assert all(t == "error" for t, _ in mensajes)


def test_borrar_tipo_propio_sin_uso(app, con, mensajes):
    ed = EditorTipos(con)
    ed.nuevo_tipo()
    ed.nombre.setText("Temporal")
    assert ed.guardar()
    assert ed.b_borrar.isEnabled()
    ed.borrar_tipo()
    assert tipos.por_nombre(con, "Temporal") is None
