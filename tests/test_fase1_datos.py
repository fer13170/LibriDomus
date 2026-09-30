"""Fase 1: catálogo de ubicaciones, tipos, elementos y búsqueda."""

import pytest

from bibliotecario import texto
from bibliotecario.datos import elementos, tipos, ubicaciones
from bibliotecario.datos.elementos import Elemento
from bibliotecario.servicios import busqueda
from bibliotecario.servicios.busqueda import Filtros


# ---------------------------------------------------------------- ayudas

def tipo_id(con, nombre):
    return con.execute("SELECT id FROM tipo_ubicacion WHERE nombre = ?", (nombre,)).fetchone()[0]


def planta(con, codigo):
    return ubicaciones.buscar_por_codigo(con, codigo).id


def libro(con):
    return tipos.por_nombre(con, "Libro")


@pytest.fixture
def casa(con):
    """Planta baja › Salón › Estantería A › Balda 1/2 y Sótano › Caja fotos."""
    pb = planta(con, "PB")
    salon = ubicaciones.crear(con, pb, tipo_id(con, "Habitación"), "Salón")
    est = ubicaciones.crear(con, salon, tipo_id(con, "Estantería"), "Estantería A")
    b1 = ubicaciones.crear(con, est, tipo_id(con, "Balda"), "Balda 1")
    b2 = ubicaciones.crear(con, est, tipo_id(con, "Balda"), "Balda 2")
    caja = ubicaciones.crear(con, planta(con, "SOT"), tipo_id(con, "Caja"), "Caja fotos")
    return {"pb": pb, "salon": salon, "est": est, "b1": b1, "b2": b2, "caja": caja}


def nuevo_libro(con, titulo, ubicacion_id=None, **extra):
    e = Elemento(tipo_id=libro(con).id, titulo=titulo, ubicacion_id=ubicacion_id, **extra)
    return elementos.guardar(con, e)


# ---------------------------------------------------------------- texto

@pytest.mark.parametrize("nombre, esperado", [
    ("Salón", "SAL"), ("Planta baja", "PB"), ("Estantería A", "EA"), ("Balda 3", "B3"), ("", "X"),
])
def test_abreviar(nombre, esperado):
    assert texto.abreviar(nombre) == esperado


def test_clave_orden_ignora_acentos():
    assert sorted(["Zeta", "Ávila", "abeja"], key=texto.clave_orden) == ["abeja", "Ávila", "Zeta"]


# ---------------------------------------------------------------- ubicaciones

def test_codigos_sugeridos_encadenan_la_ruta(con, casa):
    assert ubicaciones.obtener(con, casa["salon"]).codigo == "PB-SAL"
    assert ubicaciones.obtener(con, casa["est"]).codigo == "PB-SAL-EA"
    assert ubicaciones.obtener(con, casa["b1"]).codigo == "PB-SAL-EA-B1"


def test_codigo_duplicado_recibe_sufijo(con, casa):
    otro = ubicaciones.crear(con, casa["pb"], tipo_id(con, "Habitación"), "Salón")
    assert ubicaciones.obtener(con, otro).codigo == "PB-SAL2"


def test_codigo_manual_repetido_se_rechaza(con, casa):
    with pytest.raises(ubicaciones.ErrorUbicacion):
        ubicaciones.crear(con, casa["pb"], tipo_id(con, "Habitación"), "Cocina", codigo="pb-sal")


def test_ruta_texto_omite_la_casa(con, casa):
    assert ubicaciones.ruta_texto(con, casa["b2"]) == "Planta baja › Salón › Estantería A › Balda 2"
    assert ubicaciones.rutas_todas(con)[casa["b2"]] == "Planta baja › Salón › Estantería A › Balda 2"


def test_descendientes_incluye_todo_el_subarbol(con, casa):
    assert set(ubicaciones.descendientes(con, casa["salon"])) == {casa["salon"], casa["est"], casa["b1"], casa["b2"]}


def test_mover_con_contenido_y_reordenar(con, casa):
    ubicaciones.mover(con, casa["est"], planta(con, "PA"), 0)
    assert ubicaciones.obtener(con, casa["est"]).padre_id == planta(con, "PA")
    assert ubicaciones.obtener(con, casa["b1"]).padre_id == casa["est"]  # las baldas viajan con ella
    ubicaciones.mover(con, casa["b2"], casa["est"], 0)
    assert [u.nombre for u in ubicaciones.hijos(con, casa["est"])] == ["Balda 2", "Balda 1"]


def test_no_se_puede_mover_dentro_de_si_misma(con, casa):
    with pytest.raises(ubicaciones.ErrorUbicacion):
        ubicaciones.mover(con, casa["salon"], casa["b1"])


def test_borrar_con_elementos_exige_destino(con, casa):
    id_ = nuevo_libro(con, "Gomorra", casa["b1"])
    with pytest.raises(ubicaciones.ErrorUbicacion):
        ubicaciones.borrar(con, casa["est"])
    with pytest.raises(ubicaciones.ErrorUbicacion):
        ubicaciones.borrar(con, casa["est"], destino_id=casa["b2"])  # destino dentro de lo que se borra
    movidos = ubicaciones.borrar(con, casa["est"], destino_id=casa["caja"])
    assert movidos == 1
    assert elementos.obtener(con, id_).ubicacion_id == casa["caja"]
    assert ubicaciones.obtener(con, casa["b1"]) is None


def test_borrar_vacia_no_necesita_destino(con, casa):
    ubicaciones.borrar(con, casa["b2"])
    assert ubicaciones.obtener(con, casa["b2"]) is None


def test_contar_elementos_acumula_hacia_arriba(con, casa):
    nuevo_libro(con, "Uno", casa["b1"])
    nuevo_libro(con, "Dos", casa["b2"])
    cuentas = ubicaciones.contar_elementos(con)
    assert cuentas[casa["b1"]] == 1 and cuentas[casa["salon"]] == 2 and cuentas[planta(con, "CASA")] == 2


def test_tipo_ubicacion_en_uso_no_se_borra(con, casa):
    with pytest.raises(ubicaciones.ErrorUbicacion):
        ubicaciones.borrar_tipo(con, tipo_id(con, "Balda"))
    nuevo = ubicaciones.guardar_tipo(con, "Baúl")
    ubicaciones.borrar_tipo(con, nuevo)


# ---------------------------------------------------------------- tipos de elemento

def test_crear_tipo_con_campos_y_ocultar_campo(con):
    t = tipos.TipoElemento(id=None, nombre="Juego de mesa", roles=["Autor"], campos=[
        tipos.Campo(None, "", "Jugadores", "texto"),
        tipos.Campo(None, "", "Edad mínima", "numero"),
    ])
    tipos.guardar(con, t)
    guardado = tipos.obtener(con, t.id)
    assert [c.clave for c in guardado.campos] == ["jugadores", "edad_minima"]
    guardado.campos = guardado.campos[:1]
    tipos.guardar(con, guardado)
    visibles = tipos.campos(con, t.id)
    assert [c.etiqueta for c in visibles] == ["Jugadores"]
    assert len(tipos.campos(con, t.id, incluir_ocultos=True)) == 2


def test_lista_sin_opciones_se_rechaza(con):
    t = tipos.TipoElemento(id=None, nombre="X", campos=[tipos.Campo(None, "", "Color", "lista")])
    with pytest.raises(tipos.ErrorTipo):
        tipos.guardar(con, t)


def test_tipo_predefinido_no_se_borra(con):
    with pytest.raises(tipos.ErrorTipo):
        tipos.borrar(con, libro(con).id)


# ---------------------------------------------------------------- elementos

def test_guardar_y_leer_elemento_completo(con, casa):
    t = libro(con)
    editorial = next(c for c in t.campos if c.clave == "editorial")
    e = Elemento(tipo_id=t.id, titulo="  Gomorra ", anio=2008, identificador="978-84-8346-846-3",
                 ubicacion_id=casa["b1"], personas=[("Roberto Saviano", "Autor")],
                 etiquetas=["mafia", "Mafia", "ensayo"], valores={editorial.id: "Debolsillo"},
                 idioma="Español", estado="Bueno", valoracion=4, consumido=True)
    id_ = elementos.guardar(con, e)
    leido = elementos.obtener(con, id_)
    assert leido.titulo == "Gomorra"
    assert leido.identificador == "9788483468463"
    assert leido.personas == [("Roberto Saviano", "Autor")]
    assert leido.etiquetas == ["ensayo", "mafia"]  # sin duplicados
    assert leido.valores == {editorial.id: "Debolsillo"}
    assert leido.consumido is True


def test_titulo_obligatorio(con):
    with pytest.raises(elementos.ErrorElemento):
        nuevo_libro(con, "   ")


def test_personas_huerfanas_se_eliminan(con):
    id_ = nuevo_libro(con, "A", personas=[("Autor Único", "Autor")])
    elementos.borrar(con, [id_])
    assert elementos.nombres_personas(con) == []


def test_mover_varios(con, casa):
    ids = [nuevo_libro(con, "A", casa["b1"]), nuevo_libro(con, "B", casa["b1"])]
    elementos.mover(con, ids, casa["caja"])
    assert all(elementos.obtener(con, i).ubicacion_id == casa["caja"] for i in ids)


# ---------------------------------------------------------------- búsqueda

@pytest.mark.parametrize("entrada, esperado", [
    ("", None),
    ("garc", '"garc"*'),
    ("García Márquez", '"García"* AND "Márquez"*'),
    ('"cien años"', '"cien años"'),
    ("sol -luna", '"sol"* NOT "luna"*'),
    ("-solo", None),
    ('rara"comilla', '"rara"* AND "comilla"*'),
    ("AND OR NOT *", '"AND"* AND "OR"* AND "NOT"*'),
])
def test_construir_consulta(entrada, esperado):
    assert busqueda.construir_consulta(entrada) == esperado


def test_busqueda_sin_acentos_por_prefijo_y_campos(con, casa):
    t = libro(con)
    editorial = next(c for c in t.campos if c.clave == "editorial")
    elementos.guardar(con, Elemento(tipo_id=t.id, titulo="Cien años de soledad", ubicacion_id=casa["b1"],
                                    personas=[("Gabriel García Márquez", "Autor")],
                                    valores={editorial.id: "Sudamericana"}))
    nuevo_libro(con, "Gomorra", casa["b2"])
    titulos = lambda texto_: [r.titulo for r in busqueda.buscar(con, Filtros(texto=texto_))]  # noqa: E731
    assert titulos("garcia marq") == ["Cien años de soledad"]
    assert titulos("anos") == ["Cien años de soledad"]
    assert titulos("sudamer") == ["Cien años de soledad"]            # campo propio
    assert titulos("balda 2") == ["Gomorra"]                          # ruta de ubicación
    assert titulos("salon -gomorra") == ["Cien años de soledad"]


def test_filtro_por_ubicacion_incluye_sububicaciones(con, casa):
    nuevo_libro(con, "En balda", casa["b1"])
    nuevo_libro(con, "En caja", casa["caja"])
    nuevo_libro(con, "Sin sitio")
    assert [r.titulo for r in busqueda.buscar(con, Filtros(ubicacion_id=casa["salon"]))] == ["En balda"]
    assert [r.titulo for r in busqueda.buscar(con, Filtros(sin_ubicacion=True))] == ["Sin sitio"]
    assert len(busqueda.buscar(con, Filtros(ubicacion_id=planta(con, "CASA")))) == 2


def test_renombrar_ubicacion_actualiza_indice(con, casa):
    nuevo_libro(con, "Libro", casa["b1"])
    u = ubicaciones.obtener(con, casa["salon"])
    ubicaciones.actualizar(con, u.id, "Sala de estar", u.tipo_id, u.codigo)
    assert len(busqueda.buscar(con, Filtros(texto="sala estar"))) == 1
    assert busqueda.buscar(con, Filtros(texto="salon")) == []


def test_resultado_incluye_creadores_y_ruta(con, casa):
    nuevo_libro(con, "Obra", casa["b1"], personas=[("Ana", "Autor"), ("Luis", "Traductor")])
    r = busqueda.buscar(con, Filtros())[0]
    assert r.creadores == "Ana, Luis"
    assert r.ubicacion == "Planta baja › Salón › Estantería A › Balda 1"


def test_filtros_varios(con, casa):
    nuevo_libro(con, "Prestado", prestado_a="Pepe", consumido=True, etiquetas=["favorito"], estado="Bueno")
    nuevo_libro(con, "Normal", idioma="Inglés")
    assert [r.titulo for r in busqueda.buscar(con, Filtros(solo_prestados=True))] == ["Prestado"]
    assert [r.titulo for r in busqueda.buscar(con, Filtros(solo_no_consumidos=True))] == ["Normal"]
    assert [r.titulo for r in busqueda.buscar(con, Filtros(etiqueta="FAVORITO"))] == ["Prestado"]
    assert [r.titulo for r in busqueda.buscar(con, Filtros(estado="Bueno"))] == ["Prestado"]
    assert [r.titulo for r in busqueda.buscar(con, Filtros(idioma="Inglés"))] == ["Normal"]


def test_reindexar_todo(con, casa):
    nuevo_libro(con, "Uno")
    con.execute("DELETE FROM elemento_fts")
    assert busqueda.reindexar_todo(con) == 1
    assert len(busqueda.buscar(con, Filtros(texto="uno"))) == 1
