"""Fase 1: pruebas de la interfaz sin mostrar ventanas (Qt en modo 'offscreen')."""

import pytest
from PySide6.QtWidgets import QApplication

from bibliotecario.datos import elementos, tipos, ubicaciones
from bibliotecario.interfaz import comun, editor_ubicaciones, ventana_principal
from bibliotecario.interfaz.arbol_ubicaciones import ID_SIN_UBICACION, ID_TODAS
from bibliotecario.interfaz.editor_ubicaciones import EditorUbicaciones
from bibliotecario.interfaz.ficha_elemento import FichaElemento
from bibliotecario.interfaz.ventana_principal import VentanaPrincipal


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mensajes(monkeypatch):
    """Sustituye los cuadros de diálogo modales: confirma siempre y guarda los avisos."""
    registro = []
    monkeypatch.setattr(comun, "confirmar", lambda _p, m: registro.append(("confirmar", m)) or True)
    monkeypatch.setattr(comun, "aviso", lambda _p, m: registro.append(("aviso", m)))
    monkeypatch.setattr(comun, "error", lambda _p, m: registro.append(("error", m)))
    return registro


def test_ficha_nuevo_libro_con_campos_propios(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    ficha = FichaElemento(con, tipo_id=libro.id, ubicacion_id=pb)
    ficha.titulo.setText("Gomorra")
    ficha.personas.filas[0][1].setText("Roberto Saviano")
    ficha.anio.setValue(2008)
    ficha.identificador.setText("978-84-8346-846-3")
    ficha.etiquetas.setText("mafia, ensayo")
    editorial = next(e for e in ficha.editores.values() if e.campo.clave == "editorial")
    editorial.widget.setText("Debolsillo")
    assert ficha.guardar()
    e = elementos.obtener(con, ficha.original.id)
    assert (e.titulo, e.anio, e.ubicacion_id) == ("Gomorra", 2008, pb)
    assert e.personas == [("Roberto Saviano", "Autor")]
    assert e.valores[editorial.campo.id] == "Debolsillo"


def test_ficha_sin_titulo_muestra_error(app, con, mensajes):
    ficha = FichaElemento(con)
    assert not ficha.guardar()
    assert mensajes and mensajes[-1][0] == "error"


def test_ficha_cambiar_tipo_conserva_campos_con_misma_clave(app, con, mensajes):
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Libro").id)
    next(e for e in ficha.editores.values() if e.campo.clave == "editorial").widget.setText("Planeta")
    ficha.tipo.setCurrentIndex(ficha.tipo.findData(tipos.por_nombre(con, "Partitura").id))
    editorial = next(e for e in ficha.editores.values() if e.campo.clave == "editorial")
    assert editorial.valor() == "Planeta"
    assert ficha.personas.roles == ["Compositor", "Arreglista"]


def test_ficha_tipo_personal_muestra_primero_periodo(app, con, mensajes):
    ficha = FichaElemento(con, tipo_id=tipos.por_nombre(con, "Álbum de fotos").id)
    orden = [ficha.contenido.itemAt(i).widget() for i in range(ficha.contenido.count())]
    assert orden.index(ficha.grupo_personal) < orden.index(ficha.grupo_ubicacion)
    assert orden.index(ficha.grupo_personal) == 1
    ficha.titulo.setText("Verano 1985")
    ficha.fecha_desde.setText("1985-07")
    ficha.fecha_hasta.setText("1985-08")
    ficha.personas.filas[0][1].setText("Ana")
    assert ficha.guardar()
    e = elementos.obtener(con, ficha.original.id)
    assert (e.fecha_desde, e.personas) == ("1985-07", [("Ana", "Aparece")])


def test_ficha_editar_conserva_prestamo(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    id_ = elementos.guardar(con, elementos.Elemento(tipo_id=libro.id, titulo="A", prestado_a="Pepe"))
    ficha = FichaElemento(con, elemento_id=id_)
    ficha.titulo.setText("A (2ª ed.)")
    assert ficha.guardar()
    assert elementos.obtener(con, id_).prestado_a == "Pepe"


def test_ficha_guardar_y_nuevo_mantiene_tipo_y_ubicacion(app, con, mensajes):
    disco = tipos.por_nombre(con, "Disco")
    sot = ubicaciones.buscar_por_codigo(con, "SOT").id
    ficha = FichaElemento(con, tipo_id=disco.id, ubicacion_id=sot)
    ficha.titulo.setText("Kind of Blue")
    ficha._guardar_y_nuevo()
    assert ficha.original is None and ficha.titulo.text() == ""
    assert ficha.tipo.currentData() == disco.id and ficha.ubicacion.valor() == sot
    ficha.titulo.setText("Blue Train")
    ficha._guardar_y_nuevo()
    assert con.execute("SELECT COUNT(*) FROM elemento WHERE ubicacion_id = ?", (sot,)).fetchone()[0] == 2


def test_ficha_isbn_repetido_pide_confirmacion(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    elementos.guardar(con, elementos.Elemento(tipo_id=libro.id, titulo="Uno", identificador="9788483468463"))
    ficha = FichaElemento(con, tipo_id=libro.id)
    ficha.titulo.setText("Otro ejemplar")
    ficha.identificador.setText("978-84-8346-846-3")
    assert ficha.guardar()
    assert any(tipo == "confirmar" and "9788483468463" in m for tipo, m in mensajes)


def test_ventana_principal_busca_y_filtra_por_arbol(app, con, mensajes):
    libro = tipos.por_nombre(con, "Libro")
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    elementos.guardar(con, elementos.Elemento(tipo_id=libro.id, titulo="Cien años de soledad", ubicacion_id=pb))
    elementos.guardar(con, elementos.Elemento(tipo_id=libro.id, titulo="Sin sitio"))
    v = VentanaPrincipal(con)
    assert v.arbol.id_actual() == ID_TODAS and v.modelo.rowCount() == 2
    v.busqueda.setText("anos")
    v.refrescar_resultados()
    assert [r.titulo for r in v.modelo.filas] == ["Cien años de soledad"]
    v.busqueda.clear()
    v.arbol.seleccionar(ID_SIN_UBICACION)
    assert [r.titulo for r in v.modelo.filas] == ["Sin sitio"]
    v.arbol.seleccionar(pb)
    assert [r.titulo for r in v.modelo.filas] == ["Cien años de soledad"]
    assert v.ubicacion_para_nuevo() == pb


def test_ventana_ir_a_codigo(app, con, mensajes):
    v = VentanaPrincipal(con)
    v.ir_codigo.setText("pa")
    v.ir_a_codigo()
    assert v.arbol.id_actual() == ubicaciones.buscar_por_codigo(con, "PA").id
    v.ir_codigo.setText("NOEXISTE")
    v.ir_a_codigo()
    assert mensajes[-1][0] == "aviso"


def test_ventana_mover_y_borrar_seleccion(app, con, mensajes, monkeypatch):
    libro = tipos.por_nombre(con, "Libro")
    ids = [elementos.guardar(con, elementos.Elemento(tipo_id=libro.id, titulo=t)) for t in ("A", "B")]
    buh = ubicaciones.buscar_por_codigo(con, "BUH").id
    monkeypatch.setattr(ventana_principal, "elegir_ubicacion", lambda *a, **k: buh)
    v = VentanaPrincipal(con)
    v.tabla.selectAll()
    assert sorted(v.ids_seleccionados()) == sorted(ids)
    v.mover()
    assert all(elementos.obtener(con, i).ubicacion_id == buh for i in ids)
    v.tabla.selectAll()
    v.borrar()
    assert con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 0


def test_editor_ubicaciones_crear_mover_borrar(app, con, mensajes, monkeypatch):
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    editor = EditorUbicaciones(con, pb)
    assert editor.arbol.id_actual() == pb
    # Alta mediante el diálogo (sin mostrarlo)
    dialogo = editor_ubicaciones.DialogoNuevaUbicacion(con, pb)
    assert dialogo.tipo.currentText() == "Habitación"  # tipo sugerido tras 'Planta'
    dialogo.nombre.setText("Salón")
    assert dialogo.codigo.placeholderText() == "PB-SAL"
    dialogo._aceptar()
    salon = dialogo.nuevo_id
    editor._recargar(salon)
    # Mover por arrastre (llamada directa a la función que usa el árbol)
    pa = ubicaciones.buscar_por_codigo(con, "PA").id
    editor._mover(salon, pa, 0)
    assert ubicaciones.obtener(con, salon).padre_id == pa
    # Editar nombre desde la ficha
    editor.arbol.seleccionar(salon)
    editor.nombre.setText("Sala")
    editor._guardar()
    assert ubicaciones.obtener(con, salon).nombre == "Sala"
    # Borrar con contenido: pide destino
    libro = tipos.por_nombre(con, "Libro")
    id_ = elementos.guardar(con, elementos.Elemento(tipo_id=libro.id, titulo="X", ubicacion_id=salon))
    monkeypatch.setattr(editor_ubicaciones, "elegir_ubicacion", lambda *a, **k: pb)
    editor.arbol.seleccionar(salon)
    editor._borrar()
    assert ubicaciones.obtener(con, salon) is None
    assert elementos.obtener(con, id_).ubicacion_id == pb
    assert editor.hubo_cambios


def test_editor_ubicaciones_subir_bajar(app, con, mensajes):
    casa = ubicaciones.buscar_por_codigo(con, "CASA").id
    buh = ubicaciones.buscar_por_codigo(con, "BUH").id
    editor = EditorUbicaciones(con, buh)
    editor._desplazar(-1)
    assert [u.nombre for u in ubicaciones.hijos(con, casa)] == ["Sótano", "Planta baja", "Buhardilla", "Planta alta"]
