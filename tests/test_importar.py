"""Importar elementos desde Excel o CSV."""

import pytest
from PySide6.QtWidgets import QApplication

from libridomus.datos import elementos, tipos, ubicaciones
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun
from libridomus.interfaz.dialogo_importar import DialogoImportar, ResumenImportacion
from libridomus.servicios import importar
from libridomus.servicios.importar import ErrorImportar


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


def id_tipo(con, nombre: str) -> int:
    return next(t.id for t in tipos.listar(con, con_campos=False) if t.nombre == nombre)


# ---------------------------------------------------------------- importar: lectura

def test_leer_csv_de_excel_en_espanol(tmp_path):
    ruta = tmp_path / "lista.csv"
    ruta.write_bytes("Título;Autor;Año\nEl árbol;Pío Baroja;1911\n;;\nOtro;;\n".encode("cp1252"))
    tabla = importar.leer_tabla(ruta)
    assert tabla.cabeceras == ["Título", "Autor", "Año"]
    assert tabla.filas == [["El árbol", "Pío Baroja", "1911"], ["Otro", "", ""]]


def test_leer_csv_utf8_con_comas_y_comillas(tmp_path):
    ruta = tmp_path / "lista.csv"
    ruta.write_text('titulo,autores\n"Uno, dos",Ana\n', encoding="utf-8-sig")
    assert importar.leer_tabla(ruta).filas == [["Uno, dos", "Ana"]]


def test_leer_xlsx_y_plantilla(tmp_path):
    ruta = tmp_path / "plantilla.xlsx"
    importar.escribir_plantilla(ruta)
    tabla = importar.leer_tabla(ruta)
    assert tabla.cabeceras == importar.COLUMNAS_PLANTILLA
    assert tabla.filas[0][1] == "Cien años de soledad" and tabla.filas[0][3] == "1967"


def test_leer_archivos_no_validos(tmp_path):
    for nombre, contenido, texto in (("a.xls", b"x", "xlsx"), ("a.xlsx", b"no es zip", "Excel"),
                                     ("a.pdf", b"x", "Elige"), ("a.csv", b"", "vac")):
        ruta = tmp_path / nombre
        ruta.write_bytes(contenido)
        with pytest.raises(ErrorImportar, match=texto):
            importar.leer_tabla(ruta)


def test_sugerir_destinos(con):
    disponibles = importar.destinos(con)
    esperado = {"Título": "titulo", "AUTOR": "personas", "Año de publicación": "anio", "ISBN": "identificador",
                "Editorial": "campo:editorial", "Ubicación": "ubicacion", "Nº de páginas": "campo:no de paginas",
                "Cosa rara": ""}
    for cabecera, destino in esperado.items():
        assert importar.sugerir_destino(cabecera, disponibles) == destino, cabecera


# ---------------------------------------------------------------- importar: datos

def test_importar_con_todo_tipo_de_datos(con):
    salon = ubicaciones.crear(con, ubicaciones.buscar_por_codigo(con, "PB").id,
                              ubicaciones.listar_tipos(con)[2]["id"], "Salón", "PB-SAL")
    tabla = importar.Tabla(
        cabeceras=["Tipo", "Título", "Autor", "Traductor", "Año", "ISBN", "Editorial", "Ubicación",
                   "Conservación", "Etiquetas", "Notas", "Escala"],
        filas=[
            ["Libro", "Uno", "Ana; Luis (Ilustrador)", "Eva", "c. 1999", "978-84-376-0494-7", "Cátedra",
             "pb-sal", "bueno", "novela, clásicos", "nota libre", "1:50000"],
            ["Disco", "Dos", "Grupo", "", "2001", "", "Sello", "Planta baja > Salón", "Rayado", "", "", ""],
            ["Cosa", "Tres", "", "", "", "", "", "Desván", "", "", "", ""],
            ["", "", "Sin título", "", "", "", "", "", "", "", "", ""],
            ["Libro", "Uno repetido", "", "", "", "9788437604947", "", "", "", "", "", ""],
        ])
    mapa = {n: importar.sugerir_destino(c, importar.destinos(con)) for n, c in enumerate(tabla.cabeceras)}
    mapa[3] = "personas"
    mapa[11] = "campo:escala"
    informe = importar.importar(con, tabla, mapa, id_tipo(con, "Libro"))
    assert len(informe.creados) == 3
    assert [f for f, _ in informe.omitidos] == [5, 6]  # sin título; ISBN repetido (en el mismo archivo)
    uno, dos, tres = (elementos.obtener(con, i) for i in informe.creados)
    assert uno.personas == [("Ana", "Autor"), ("Luis", "Ilustrador"), ("Eva", "Traductor")]
    assert (uno.anio, uno.identificador, uno.ubicacion_id, uno.estado) == (1999, "9788437604947", salon, "Bueno")
    assert uno.etiquetas == ["clásicos", "novela"]
    assert "Cátedra" in uno.valores.values()
    assert uno.notas == "nota libre\nEscala: 1:50000"  # los libros no tienen «Escala»
    assert dos.tipo_id == id_tipo(con, "Disco") and dos.ubicacion_id == salon
    assert dos.personas == [("Grupo", "Intérprete")]
    assert "Conservación: Rayado" in dos.notas and "Editorial: Sello" in dos.notas
    assert tres.tipo_id == id_tipo(con, "Libro") and tres.ubicacion_id is None
    assert "Ubicación indicada: Desván" in tres.notas
    assert [f for f, _ in informe.avisos] == [4]  # tipo «Cosa» y ubicación «Desván» desconocidos


def test_importar_omite_repetidos_de_la_coleccion_salvo_que_se_pida(con):
    libro = id_tipo(con, "Libro")
    elementos.guardar(con, Elemento(tipo_id=libro, titulo="Ya estaba", identificador="9788437604947"))
    tabla = importar.Tabla(["Título", "ISBN"], [["Nuevo", "978-84-376-0494-7"]])
    assert len(importar.importar(con, tabla, {0: "titulo", 1: "identificador"}, libro).creados) == 0
    assert len(importar.importar(con, tabla, {0: "titulo", 1: "identificador"}, libro,
                                 omitir_repetidos=False).creados) == 1


def test_importar_exige_columna_de_titulo(con):
    with pytest.raises(ErrorImportar, match="título"):
        importar.importar(con, importar.Tabla(["A"], [["x"]]), {0: "notas"}, id_tipo(con, "Libro"))


def test_importar_es_todo_o_nada_ante_un_fallo_inesperado(con, monkeypatch):
    original = elementos.guardar
    llamadas = []

    def guardar_que_falla(c, e):
        llamadas.append(e.titulo)
        if len(llamadas) == 3:
            raise RuntimeError("corte")
        return original(c, e)

    monkeypatch.setattr(elementos, "guardar", guardar_que_falla)
    tabla = importar.Tabla(["Título"], [["A"], ["B"], ["C"]])
    with pytest.raises(RuntimeError):
        importar.importar(con, tabla, {0: "titulo"}, id_tipo(con, "Libro"))
    assert con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 0


def test_importar_rendimiento_5000_filas(con):
    import time

    tabla = importar.Tabla(["Título", "Autor", "Año"], [[f"Libro {i}", f"Autor {i % 300}", "2000"]
                                                         for i in range(5000)])
    inicio = time.perf_counter()
    informe = importar.importar(con, tabla, {0: "titulo", 1: "personas", 2: "anio"}, id_tipo(con, "Libro"))
    assert len(informe.creados) == 5000
    assert time.perf_counter() - inicio < 30


# ---------------------------------------------------------------- importar: diálogo

def test_dialogo_importar_y_deshacer(app, con, mensajes, tmp_path, monkeypatch):
    ruta = tmp_path / "lista.csv"
    ruta.write_text("Título;Autor;Columna rara\nUno;Ana;x\nDos;Luis;y\n", encoding="utf-8")
    d = DialogoImportar(con)
    assert not d.b_importar.isEnabled()
    assert d.elegir(str(ruta))
    assert d.mapa() == {0: "titulo", 1: "personas"}
    assert d.b_importar.isEnabled() and d.b_importar.text() == "Importar 2 filas"
    d.combos[0].setCurrentIndex(0)  # sin columna de título no se puede importar
    assert not d.b_importar.isEnabled()
    d.combos[0].setCurrentIndex(d.combos[0].findData("titulo"))

    monkeypatch.setattr(ResumenImportacion, "exec", lambda self: self._deshacer())
    d.importar()
    assert con.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 0 and d.creados == []

    monkeypatch.setattr(ResumenImportacion, "exec", lambda self: self.accept())
    d.importar()
    assert len(d.creados) == 2
    assert con.execute("SELECT COUNT(*) FROM persona").fetchone()[0] == 2


def test_dialogo_guarda_plantilla(app, con, mensajes, tmp_path):
    d = DialogoImportar(con)
    destino = tmp_path / "p.xlsx"
    assert d.guardar_plantilla(str(destino)) and destino.exists()
    assert d.elegir(str(destino)) and d.mapa()[1] == "titulo"
