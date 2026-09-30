"""Copias de seguridad.

- Automática (al cerrar): solo la base de datos, en datos/copias/auto_AAAAMMDD_HHMMSS.db.
  Se conservan las últimas N (Preferencias).
- Manual: un ZIP con la base de datos, las portadas y las preferencias, donde se elija
  (por ejemplo un USB).
- Restaurar: desde una copia .db o .zip. Antes se guarda el estado actual por si acaso.
"""

import json
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
    """ZIP con la base de datos, las portadas y las preferencias.

    La clave de Google Books NO se incluye: la copia puede acabar en otras manos.
    """
    destino_zip = Path(destino_zip)
    with tempfile.TemporaryDirectory() as temporal:
        bd = conexion.copiar_en_caliente(con, Path(temporal) / "biblioteca.db")
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(bd, "biblioteca.db")
            for imagen in rutas.carpeta_portadas().glob("*.jpg"):
                z.write(imagen, f"portadas/{imagen.name}")
            if rutas.ruta_configuracion().exists():
                try:
                    ajustes = json.loads(rutas.ruta_configuracion().read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    ajustes = {}
                if isinstance(ajustes, dict):
                    ajustes.pop("clave_google_books", None)
                    z.writestr("config.json", json.dumps(ajustes, ensure_ascii=False, indent=2))
    return destino_zip


# ---------------------------------------------------------------- validación de copias

def _esquema(con: sqlite3.Connection) -> tuple[dict[str, set[str]], set[str]]:
    """(tablas con sus columnas, otros objetos del esquema como disparadores o vistas)."""
    tablas: dict[str, set[str]] = {}
    otros: set[str] = set()
    for tipo, nombre in con.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"):
        if tipo == "table":
            tablas[nombre] = {f[1] for f in con.execute(f'PRAGMA table_info("{nombre}")')}
        elif tipo in ("trigger", "view"):
            otros.add(f"{tipo} {nombre}")
    return tablas, otros


def esquema_de_referencia(version: int) -> dict[str, set[str]]:
    """Tablas y columnas que tiene una base de datos de LibriDomus en esa versión del esquema."""
    ref = sqlite3.connect(":memory:")
    try:
        for sql in esquema.MIGRACIONES[:version]:
            ref.executescript(sql)
        return _esquema(ref)[0]
    finally:
        ref.close()


def validar_base_datos(ruta: Path) -> int:
    """Comprueba que el archivo es una base de datos de LibriDomus sin manipular. Devuelve su versión.

    Exige exactamente las tablas y columnas de su versión del esquema y rechaza disparadores y
    vistas: una copia ajena podría esconder un disparador que borrase datos al usarla.
    """
    try:
        prueba = conexion.abrir_solo_lectura(ruta)
        try:
            version = prueba.execute("PRAGMA user_version").fetchone()[0]
            tablas, otros = _esquema(prueba)
            integridad = prueba.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            prueba.close()
    except sqlite3.DatabaseError as error:
        raise ErrorCopia("El archivo no es una base de datos válida.") from error
    if version < 1 or not {"elemento", "ubicacion", "tipo_elemento"} <= set(tablas):
        raise ErrorCopia("El archivo no es una copia de LibriDomus.")
    if version > esquema.VERSION_ESQUEMA:
        raise ErrorCopia("La copia es de una versión más nueva del programa.")
    if integridad != "ok":
        raise ErrorCopia("La copia está dañada.")
    referencia = esquema_de_referencia(version)
    faltan = [f"{t}.{c}" for t, cols in referencia.items() for c in sorted(cols - tablas.get(t, set()))]
    sobran = sorted(set(tablas) - set(referencia))
    if faltan or sobran or otros:
        detalle = "; ".join(filter(None, [
            f"faltan {', '.join(faltan[:5])}" if faltan else "",
            f"tablas desconocidas: {', '.join(sobran[:5])}" if sobran else "",
            f"contiene {', '.join(sorted(otros)[:5])}" if otros else ""]))
        raise ErrorCopia(f"La copia no tiene la estructura de LibriDomus o ha sido modificada ({detalle}).")
    return version


def probar_apertura(ruta: Path) -> None:
    """Abre una copia (sobre un duplicado temporal) como lo haría el programa, migración incluida."""
    from .busqueda import Filtros, buscar

    with tempfile.TemporaryDirectory() as temporal:
        duplicado = Path(temporal) / "prueba.db"
        shutil.copy2(ruta, duplicado)
        try:
            con = conexion.abrir(duplicado, comprobar_integridad=True, copia_antes_de_migrar=False)
        except conexion.ErrorBaseDatos as error:
            raise ErrorCopia(f"La copia no se puede abrir: {error}") from error
        try:
            buscar(con, Filtros())
            con.execute("SELECT COUNT(*) FROM elemento_fts").fetchone()
        except sqlite3.Error as error:
            raise ErrorCopia(f"La copia no funciona con esta versión del programa ({error}).") from error
        finally:
            con.close()


# ---------------------------------------------------------------- extracción segura de ZIP

LIMITE_ZIP = 8 * 2**30         # 8 GB descomprimidos como máximo
RATIO_SOSPECHOSO = 200         # un archivo que se comprime más de 200:1 y ocupa > 50 MB es una «bomba»


def _miembro_valido(nombre: str) -> bool:
    if nombre in ("biblioteca.db", "config.json"):
        return True
    if nombre.startswith("portadas/"):
        archivo = nombre[len("portadas/"):]
        return bool(archivo) and "/" not in archivo and "\\" not in archivo and archivo.lower().endswith(".jpg") \
            and archivo not in (".", "..")
    return False


def _extraer_zip(origen: Path, destino: Path) -> None:
    """Extrae solo lo que es de LibriDomus, comprobando tamaños y espacio libre antes de escribir."""
    try:
        with zipfile.ZipFile(origen) as z:
            miembros = [i for i in z.infolist() if not i.is_dir() and _miembro_valido(i.filename)]
            if "biblioteca.db" not in {i.filename for i in miembros}:
                raise ErrorCopia("El ZIP no contiene biblioteca.db.")
            total = sum(i.file_size for i in miembros)
            for i in miembros:
                if i.file_size > 50 * 2**20 and i.file_size / max(1, i.compress_size) > RATIO_SOSPECHOSO:
                    raise ErrorCopia(f"El ZIP tiene un archivo sospechoso ({i.filename}): no es una copia normal.")
            if total > LIMITE_ZIP:
                raise ErrorCopia("La copia es demasiado grande para ser de LibriDomus.")
            if total > shutil.disk_usage(destino).free * 0.9:
                raise ErrorCopia("No hay espacio libre suficiente en el disco para restaurar la copia.")
            for i in miembros:
                ruta = destino / Path(*i.filename.split("/"))
                ruta.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as entrada, open(ruta, "wb") as salida:
                    escrito = 0
                    while bloque := entrada.read(1 << 20):
                        escrito += len(bloque)
                        if escrito > i.file_size:  # el ZIP miente sobre el tamaño
                            raise ErrorCopia("El ZIP está dañado o manipulado.")
                        salida.write(bloque)
    except zipfile.BadZipFile as error:
        raise ErrorCopia("El archivo ZIP está dañado.") from error


def restaurar(con_actual: sqlite3.Connection | None, origen: Path | str) -> Path:
    """Sustituye la base de datos actual por la copia. Devuelve la copia de seguridad previa.

    Quien llama debe cerrar su conexión después (se cierra aquí si se pasa) y volver a abrir
    la base de datos, por ejemplo reiniciando el programa.
    """
    origen = Path(origen)
    with tempfile.TemporaryDirectory() as temporal:
        temporal = Path(temporal)
        bd_nueva = temporal / "biblioteca.db"
        if origen.suffix.lower() == ".zip":
            _extraer_zip(origen, temporal)
        else:
            shutil.copy2(origen, bd_nueva)
        validar_base_datos(bd_nueva)
        probar_apertura(bd_nueva)

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
