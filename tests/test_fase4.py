"""Fase 4: etiquetas con QR, informes PDF y copias de seguridad."""

import sqlite3
import zipfile

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from libridomus import rutas
from libridomus.datos import conexion, elementos, tipos, ubicaciones
from libridomus.datos.elementos import Elemento
from libridomus.interfaz import comun, ventana_principal
from libridomus.interfaz.dialogo_etiquetas import DialogoEtiquetas
from libridomus.interfaz.ventana_principal import VentanaPrincipal
from libridomus.servicios import copias, etiquetas, informes, portadas


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


@pytest.fixture
def casa(con):
    tipo = lambda n: con.execute("SELECT id FROM tipo_ubicacion WHERE nombre = ?", (n,)).fetchone()[0]  # noqa: E731
    pb = ubicaciones.buscar_por_codigo(con, "PB").id
    salon = ubicaciones.crear(con, pb, tipo("Habitación"), "Salón")
    balda = ubicaciones.crear(con, salon, tipo("Balda"), "Balda 3")
    caja = ubicaciones.crear(con, ubicaciones.buscar_por_codigo(con, "SOT").id, tipo("Caja"), "Caja vacía")
    libro = tipos.por_nombre(con, "Libro").id
    for n in range(10):
        elementos.guardar(con, Elemento(tipo_id=libro, titulo=f"Libro {n:02d}", ubicacion_id=balda,
                                        personas=[("Autora", "Autor")]))
    elementos.guardar(con, Elemento(tipo_id=libro, titulo="Prestado", prestado_a="Lucía", ubicacion_id=salon))
    return {"salon": salon, "balda": balda, "caja": caja, "pb": pb}


def es_pdf(ruta) -> bool:
    with open(ruta, "rb") as f:
        return f.read(5) == b"%PDF-"


# ---------------------------------------------------------------- etiquetas

def test_datos_de_etiqueta_resumen_del_contenido(con, casa):
    d = etiquetas.datos_etiqueta(con, casa["salon"], max_titulos=3)
    assert d.codigo == "PB-SAL" and d.total == 11
    assert d.titulos == ["Libro 00", "Libro 01", "Libro 02"]
    assert d.ruta == "Planta baja › Salón"
    assert etiquetas.datos_etiqueta(con, casa["caja"], 6).total == 0


def test_pdf_de_etiquetas_paginas(app, con, casa, tmp_path):
    ids = [u.id for u in ubicaciones.todas(con)]  # 1 casa + 4 plantas + 3 = 8 -> 1 hoja
    assert etiquetas.generar_pdf(con, ids, tmp_path / "e.pdf") == 1
    assert etiquetas.generar_pdf(con, ids + ids[:1], tmp_path / "e2.pdf") == 2
    assert es_pdf(tmp_path / "e.pdf")
    with pytest.raises(ValueError):
        etiquetas.generar_pdf(con, [], tmp_path / "vacio.pdf")


def test_qr_de_cada_etiqueta_contiene_su_codigo(app, con, casa, tmp_path, monkeypatch):
    import segno
    codificados = []
    original = segno.make
    monkeypatch.setattr(etiquetas.segno, "make", lambda texto, **k: codificados.append(texto) or original(texto, **k))
    etiquetas.generar_pdf(con, [casa["salon"], casa["balda"]], tmp_path / "qr.pdf")
    assert codificados == ["PB-SAL", "PB-SAL-B3"]


def test_dialogo_etiquetas_marcar_rama_y_generar(app, con, casa, mensajes, tmp_path):
    d = DialogoEtiquetas(con, casa["salon"])
    assert d.marcados() == [casa["salon"]]
    d.marcar_rama()
    assert set(d.marcados()) == {casa["salon"], casa["balda"]}
    assert "2 etiqueta(s) · 1 hoja(s)" in d.resumen.text()
    assert d.generar(str(tmp_path / "etiquetas.pdf"), abrir=False)
    assert es_pdf(tmp_path / "etiquetas.pdf")


# ---------------------------------------------------------------- informes

def test_informes_pdf(app, con, casa, tmp_path):
    assert informes.inventario(con, casa["salon"], tmp_path / "inv.pdf") == 11
    assert informes.inventario(con, None, tmp_path / "casa.pdf") == 11
    assert informes.prestados(con, tmp_path / "prest.pdf") == 1
    for nombre in ("inv.pdf", "casa.pdf", "prest.pdf"):
        assert es_pdf(tmp_path / nombre)


def test_informes_desde_la_ventana(app, con, casa, mensajes, tmp_path):
    v = VentanaPrincipal(con)
    v.arbol.seleccionar(casa["balda"])
    v.informe_inventario(str(tmp_path / "a.pdf"), abrir=False)
    v.busqueda.setText("libro 0")
    v.refrescar_resultados()
    v.informe_busqueda(str(tmp_path / "b.pdf"), abrir=False)
    v.informe_prestados(str(tmp_path / "c.pdf"), abrir=False)
    assert all(es_pdf(tmp_path / n) for n in ("a.pdf", "b.pdf", "c.pdf"))


# ---------------------------------------------------------------- copias

def test_copia_automatica_y_rotacion(con, casa):
    import time
    for _ in range(4):
        copias.copia_automatica(con, conservar=2)
        time.sleep(1.05)  # el nombre lleva segundos
    automaticas = [c for c in copias.listar() if c.automatica]
    assert len(automaticas) == 2
    bd = sqlite3.connect(automaticas[0].ruta)
    assert bd.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 11
    bd.close()


def test_copia_manual_zip_con_portadas_y_restaurar(app, con, casa, tmp_path):
    imagen = QImage(10, 10, QImage.Format.Format_RGB32)
    imagen.fill(QColor("blue"))
    nombre = portadas.guardar_imagen(imagen)
    e = elementos.obtener(con, 1)
    e.portada = nombre
    elementos.guardar(con, e)
    destino = copias.copia_manual(con, tmp_path / "copia.zip")
    with zipfile.ZipFile(destino) as z:
        assert {"biblioteca.db", f"portadas/{nombre}"} <= set(z.namelist())

    # Se estropean los datos: se borra todo y la portada.
    elementos.borrar(con, [r[0] for r in con.execute("SELECT id FROM elemento").fetchall()])
    portadas.borrar(nombre)
    previa = copias.restaurar(con, destino)  # cierra la conexión
    assert previa.exists()
    nueva = conexion.abrir()
    assert nueva.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 11
    assert portadas.ruta(nombre)
    # La copia previa guarda el estado "estropeado" (0 elementos) por si hiciera falta volver.
    bd = sqlite3.connect(previa)
    assert bd.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 0
    bd.close()
    nueva.close()


def test_restaurar_desde_db_automatica(con, casa):
    copia = copias.copia_automatica(con, 5)
    con.execute("DELETE FROM elemento")
    copias.restaurar(con, copia)
    nueva = conexion.abrir()
    assert nueva.execute("SELECT COUNT(*) FROM elemento").fetchone()[0] == 11
    nueva.close()


def test_restaurar_rechaza_archivos_no_validos(con, tmp_path):
    basura = tmp_path / "basura.db"
    basura.write_bytes(b"no soy una base de datos" * 100)
    with pytest.raises(copias.ErrorCopia):
        copias.restaurar(con, basura)
    otra = tmp_path / "otra.db"
    ajena = sqlite3.connect(otra)
    ajena.execute("CREATE TABLE cosas (x)")
    ajena.close()
    with pytest.raises(copias.ErrorCopia):
        copias.restaurar(con, otra)
    zip_malo = tmp_path / "malo.zip"
    zip_malo.write_bytes(b"PK no es zip")
    with pytest.raises(copias.ErrorCopia):
        copias.restaurar(con, zip_malo)
    # La base de datos actual sigue intacta y abierta
    assert con.execute("SELECT COUNT(*) FROM tipo_elemento").fetchone()[0] == 10


def test_restaurar_desde_la_ventana_reinicia(app, con, casa, mensajes, monkeypatch):
    copia = copias.copia_automatica(con, 5)
    reinicios = []
    monkeypatch.setattr(ventana_principal, "reiniciar", lambda: reinicios.append(True))
    monkeypatch.setattr(ventana_principal.DialogoRestaurar, "exec", lambda self: setattr(self, "elegida", str(copia)) or 1)
    v = VentanaPrincipal(con)
    v.restaurar_copia()
    assert v.restaurado and reinicios == [True]


def test_copia_al_salir_respeta_preferencias(app, con, casa):
    from libridomus.interfaz.aplicacion import copia_al_salir
    from libridomus.servicios import configuracion
    configuracion.guardar({**configuracion.cargar(), "copia_al_cerrar": False})
    copia_al_salir(con)
    assert not list(rutas.carpeta_copias().glob("auto_*.db"))
    configuracion.guardar({**configuracion.cargar(), "copia_al_cerrar": True})
    copia_al_salir(con)
    assert len(list(rutas.carpeta_copias().glob("auto_*.db"))) == 1
