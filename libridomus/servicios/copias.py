"""Copias de seguridad.

- Automática (al cerrar): solo la base de datos, en datos/copias/auto_AAAAMMDD_HHMMSS.db.
  Se conservan las últimas N (Preferencias).
- Manual: un ZIP con la base de datos, las portadas y las preferencias, donde se elija
  (por ejemplo un USB).
- Restaurar: desde una copia .db o .zip. Antes se guarda el estado actual por si acaso.
"""

import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import rutas
from ..datos import conexion, esquema

PREFIJO_AUTO = "auto_"


class ErrorCopia(Exception):
    """Problema con una copia de seguridad (mensaje para el usuario)."""


@dataclass
class Copia:
    ruta: Path
    fecha: datetime
    tamano: int
    automatica: bool


def _marca() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def copia_automatica(con: sqlite3.Connection, conservar: int) -> Path:
    destino = rutas.carpeta_copias() / f"{PREFIJO_AUTO}{_marca()}.db"
    conexion.copiar_en_caliente(con, destino)
    rotar(conservar)
    return destino


def rotar(conservar: int) -> int:
    """Borra las copias automáticas más antiguas. Devuelve cuántas se han borrado."""
    automaticas = sorted(rutas.carpeta_copias().glob(f"{PREFIJO_AUTO}*.db"), reverse=True)
    sobrantes = automaticas[max(1, conservar):]
    for archivo in sobrantes:
        archivo.unlink(missing_ok=True)
    return len(sobrantes)


def listar() -> list[Copia]:
    copias = []
    for archivo in rutas.carpeta_copias().glob("*.db"):
        dato = archivo.stat()
        copias.append(Copia(archivo, datetime.fromtimestamp(dato.st_mtime), dato.st_size,
                            archivo.name.startswith(PREFIJO_AUTO)))
    return sorted(copias, key=lambda c: c.fecha, reverse=True)


def copia_manual(con: sqlite3.Connection, destino_zip: Path | str) -> Path:
    destino_zip = Path(destino_zip)
    with tempfile.TemporaryDirectory() as temporal:
        bd = conexion.copiar_en_caliente(con, Path(temporal) / "biblioteca.db")
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(bd, "biblioteca.db")
            for imagen in rutas.carpeta_portadas().glob("*.jpg"):
                z.write(imagen, f"portadas/{imagen.name}")
            if rutas.ruta_configuracion().exists():
                z.write(rutas.ruta_configuracion(), "config.json")
    return destino_zip


def validar_base_datos(ruta: Path) -> int:
    """Comprueba que el archivo es una base de datos de este programa. Devuelve su versión de esquema."""
    try:
        prueba = conexion.abrir_solo_lectura(ruta)
        try:
            version = prueba.execute("PRAGMA user_version").fetchone()[0]
            tablas = {f[0] for f in prueba.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            integridad = prueba.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            prueba.close()
    except sqlite3.DatabaseError as error:
        raise ErrorCopia("El archivo no es una base de datos válida.") from error
    if not {"elemento", "ubicacion", "tipo_elemento"} <= tablas or version < 1:
        raise ErrorCopia("El archivo no es una copia de LibriDomus.")
    if version > esquema.VERSION_ESQUEMA:
        raise ErrorCopia("La copia es de una versión más nueva del programa.")
    if integridad != "ok":
        raise ErrorCopia("La copia está dañada.")
    return version


def restaurar(con_actual: sqlite3.Connection | None, origen: Path | str) -> Path:
    """Sustituye la base de datos actual por la copia. Devuelve la copia de seguridad previa.

    Quien llama debe cerrar su conexión después (se cierra aquí si se pasa) y volver a abrir
    la base de datos, por ejemplo reiniciando el programa.
    """
    origen = Path(origen)
    with tempfile.TemporaryDirectory() as temporal:
        temporal = Path(temporal)
        if origen.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(origen) as z:
                    if "biblioteca.db" not in z.namelist():
                        raise ErrorCopia("El ZIP no contiene biblioteca.db.")
                    z.extractall(temporal)
            except zipfile.BadZipFile as error:
                raise ErrorCopia("El archivo ZIP está dañado.") from error
            bd_nueva = temporal / "biblioteca.db"
        else:
            bd_nueva = temporal / "biblioteca.db"
            shutil.copy2(origen, bd_nueva)
        validar_base_datos(bd_nueva)

        # Red de seguridad: copia del estado actual antes de sustituirlo.
        previa = rutas.carpeta_copias() / f"antes_de_restaurar_{_marca()}.db"
        if con_actual is not None:
            conexion.copiar_en_caliente(con_actual, previa)
        elif rutas.ruta_base_datos().exists():
            shutil.copy2(rutas.ruta_base_datos(), previa)

        # La copia se deja primero junto a la base de datos y luego se sustituye de golpe
        # (os.replace): si algo falla antes, biblioteca.db queda intacta, nunca a medias.
        provisional = rutas.ruta_base_datos().with_suffix(".db.restaurando")
        shutil.copy2(bd_nueva, provisional)
        if con_actual is not None:
            con_actual.close()  # en Windows no se puede sustituir un archivo abierto
        try:
            os.replace(provisional, rutas.ruta_base_datos())
        except OSError:
            provisional.unlink(missing_ok=True)
            raise
        portadas_zip = temporal / "portadas"
        if portadas_zip.is_dir():  # se añaden las portadas de la copia (no se borra ninguna)
            for imagen in portadas_zip.glob("*.jpg"):
                shutil.copy2(imagen, rutas.carpeta_portadas() / imagen.name)
    return previa
