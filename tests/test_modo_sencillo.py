"""Modo sencillo y modo avanzado: ficha, alta masiva y ventana principal."""

import json

import pytest
from PySide6.QtWidgets import QApplication

from libridomus import rutas
from libridomus.datos import elementos, tipos
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun
from libridomus.interfaz.alta_masiva import AltaMasiva
from libridomus.interfaz.ficha_elemento import FichaElemento
from libridomus.interfaz.ventana_principal import VentanaPrincipal
from libridomus.servicios import configuracion


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


def poner_modo(modo: str) -> None:
    ajustes = configuracion.cargar()
    ajustes["modo"] = modo
    configuracion.guardar(ajustes)


def id_tipo(con, nombre: str) -> int:
    return next(t.id for t in tipos.listar(con, con_campos=False) if t.nombre == nombre)


# ---------------------------------------------------------------- configuración

def test_modo_sencillo_por_defecto_y_valor_invalido(carpeta_datos):
    assert configuracion.obtener("modo") == "sencillo"
    assert not configuracion.modo_avanzado()
    rutas.ruta_configuracion().write_text(json.dumps({"modo": "experto"}), encoding="utf-8")
    assert configuracion.obtener("modo") == "sencillo"  # un valor inválido no rompe nada
    poner_modo("avanzado")
    assert configuracion.modo_avanzado()


# ---------------------------------------------------------------- ficha

def test_ficha_sencilla_oculta_lo_avanzado_y_mas_campos_lo_muestra(app, con):
    f = FichaElemento(con, tipo_id=id_tipo(con, "Libro"))
    f.show()
    assert f.titulo.isVisible() and f.personas.isVisible() and f.identificador.isVisible()
    assert f.ubicacion.isVisible() and f.notas.isVisible()
    for w in (f.subtitulo, f.idioma, f.estado, f.etiquetas, f.grupo_prestamo, f.grupo_campos, f.grupo_personal):
        assert not w.isVisible()
    assert f.boton_mas.isVisible() and f.boton_mas.text() == "Más campos"
    f.alternar_mas_campos()
    for w in (f.subtitulo, f.idioma, f.estado, f.etiquetas, f.grupo_prestamo, f.grupo_campos, f.grupo_personal):
        assert w.isVisible()
    assert f.boton_mas.text() == "Menos campos"


def test_ficha_sencilla_muestra_lo_que_ya_tiene_datos_y_no_lo_borra(app, con):
    libro = id_tipo(con, "Libro")
    editorial = next(c.id for c in tipos.listar(con)[0].campos if c.clave == "editorial")
    id_ = elementos.guardar(con, Elemento(tipo_id=libro, titulo="El Quijote", subtitulo="Primera parte",
                                          etiquetas=["clásicos"], valores={editorial: "Cátedra"},
                                          prestado_a="Ana", fecha_prestamo="2026-01-02"))
    f = FichaElemento(con, elemento_id=id_)
    f.show()
    assert f.subtitulo.isVisible() and f.etiquetas.isVisible()
    assert f.grupo_prestamo.isVisible() and f.grupo_campos.isVisible()
    assert not f.idioma.isVisible() and not f.estado.isVisible()  # vacíos: siguen ocultos
    assert f.guardar()
    e = elementos.obtener(con, id_)
    assert (e.subtitulo, e.etiquetas, e.valores[editorial], e.prestado_a) == \
        ("Primera parte", ["clásicos"], "Cátedra", "Ana")


def test_ficha_sencilla_guarda_campos_ocultos_rellenados_por_isbn(app, con):
    from libridomus.servicios.isbn import DatosLibro

    f = FichaElemento(con, tipo_id=id_tipo(con, "Libro"))
    f.aplicar_datos_isbn(DatosLibro(isbn="9788437604947", titulo="Cien años de soledad", autores=["G. García"],
                                    editorial="Cátedra", anio=1967, idioma="Español", fuente="prueba"))
    assert f.guardar()
    e = elementos.obtener(con, f.original.id)
    assert e.idioma == "Español" and "Cátedra" in e.valores.values()


def test_tipo_personal_muestra_periodo_en_modo_sencillo(app, con):
    f = FichaElemento(con, tipo_id=id_tipo(con, "Álbum de fotos"))
    f.show()
    assert f.grupo_personal.isVisible()


def test_ficha_avanzada_lo_muestra_todo_sin_boton(app, con):
    poner_modo("avanzado")
    f = FichaElemento(con, tipo_id=id_tipo(con, "Libro"))
    f.show()
    assert f.subtitulo.isVisible() and f.grupo_campos.isVisible() and f.grupo_prestamo.isVisible()
    assert not f.boton_mas.isVisible()


def test_alta_masiva_sencilla_oculta_etiquetas_y_conservacion(app, con):
    a = AltaMasiva(con)
    a.show()
    assert not a.etiquetas.isVisible() and not a.estado.isVisible()
    poner_modo("avanzado")
    b = AltaMasiva(con)
    b.show()
    assert b.etiquetas.isVisible() and b.estado.isVisible()


# ---------------------------------------------------------------- ventana principal

def test_cambiar_de_modo_en_la_ventana(app, con, mensajes):
    v = VentanaPrincipal(con)
    v.show()
    assert v.modo == "sencillo" and v.acciones_modo["sencillo"].isChecked()
    assert v.boton_modo.text() == "Modo sencillo"
    assert not v.acc_tipos.isVisible()
    v.cambiar_modo("avanzado")
    assert configuracion.obtener("modo") == "avanzado"
    assert v.acc_tipos.isVisible() and v.accion_boton_informes.isVisible()
    # Un filtro avanzado activo se quita al volver al modo sencillo (si no, escondería resultados).
    elementos.guardar(con, Elemento(tipo_id=id_tipo(con, "Libro"), titulo="A", estado="Bueno"))
    elementos.guardar(con, Elemento(tipo_id=id_tipo(con, "Libro"), titulo="B"))
    v.refrescar_todo()
    v.f_estado.setCurrentIndex(v.f_estado.findData("Bueno"))
    assert v.modelo.rowCount() == 1
    v.cambiar_modo("sencillo")
    assert v.f_estado.currentIndex() == 0 and v.modelo.rowCount() == 2
    assert not v.f_estado.isVisible() and v.f_tipo.isVisible()
