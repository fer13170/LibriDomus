"""Fase 0: la base de datos se crea, se migra y trae los datos iniciales."""

import sqlite3

import pytest

from libridomus import autoprueba, rutas
from libridomus.datos import conexion, esquema


def test_base_datos_nueva_tiene_version_actual(con):
    assert conexion.version(con) == esquema.VERSION_ESQUEMA


def test_casa_con_cuatro_plantas_en_orden(con):
    filas = con.execute(
        "SELECT u.nombre FROM ubicacion u JOIN ubicacion casa ON casa.id = u.padre_id"
        " WHERE casa.codigo = 'CASA' ORDER BY u.orden"
    ).fetchall()
    assert [f["nombre"] for f in filas] == ["Sótano", "Planta baja", "Planta alta", "Buhardilla"]


def test_tipos_de_elemento_predefinidos(con):
    nombres = {f[0] for f in con.execute("SELECT nombre FROM tipo_elemento WHERE predefinido = 1")}
    assert {"Libro", "Disco", "Película", "Álbum de fotos", "Diapositivas", "Carpeta"} <= nombres
    assert len(nombres) == 10


def test_reabrir_no_duplica_semillas(carpeta_datos):
    conexion.abrir().close()
    con = conexion.abrir()
    assert con.execute("SELECT COUNT(*) FROM tipo_elemento").fetchone()[0] == 10
    con.close()


def test_base_datos_de_version_futura_se_rechaza(carpeta_datos):
    ruta = rutas.ruta_base_datos()
    bruta = sqlite3.connect(ruta)
    bruta.execute(f"PRAGMA user_version = {esquema.VERSION_ESQUEMA + 1}")
    bruta.close()
    with pytest.raises(conexion.ErrorBaseDatos):
        conexion.abrir()


def test_transaccion_deshace_si_hay_error(con):
    antes = con.execute("SELECT COUNT(*) FROM persona").fetchone()[0]
    with pytest.raises(RuntimeError):
        with conexion.transaccion(con):
            con.execute("INSERT INTO persona (nombre) VALUES ('Temporal')")
            raise RuntimeError("fallo simulado")
    assert con.execute("SELECT COUNT(*) FROM persona").fetchone()[0] == antes


def test_copia_en_caliente(con, tmp_path):
    destino = conexion.copiar_en_caliente(con, tmp_path / "copia.db")
    copia = sqlite3.connect(destino)
    assert copia.execute("SELECT COUNT(*) FROM tipo_elemento").fetchone()[0] == 10
    copia.close()


def test_autoprueba_correcta():
    assert autoprueba.ejecutar() == 0
