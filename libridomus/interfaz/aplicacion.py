"""Arranque de la interfaz gráfica: instancia única, gestor de errores, apertura segura de los
datos (con recuperación si están dañados) y tareas al cerrar."""

import os
import sqlite3
import sys
import threading
from datetime import datetime

from PySide6.QtCore import QByteArray, QLockFile, QThread
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import NOMBRE, VERSION, rutas
from ..datos import conexion
from ..servicios import registro
from . import comun


def ejecutar(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationVersion(VERSION)
    comun.preparar_aplicacion(app)

    carpeta = rutas.carpeta_datos()
    if not rutas.se_puede_escribir(carpeta):
        comun.error(None, f"No se puede escribir en la carpeta de datos:\n{carpeta}\n\n"
                          "Copia la carpeta del programa a Documentos, al Escritorio o a un USB.")
        return 1
    registro.configurar()
    instalar_gestor_errores()

    candado = bloquear_instancia()
    if candado is None:
        comun.aviso(None, f"{NOMBRE} ya está abierto con estos mismos datos.\n\n"
                          "Usa la ventana que ya está abierta (mira en la barra de tareas).")
        return 0
    try:
        con = abrir_datos()
        if con is None:
            return 1

        from ..servicios import portadas
        from .ventana_principal import VentanaPrincipal

        try:
            portadas.limpiar_huerfanas(con)  # imágenes que quedaron sin uso
        except (OSError, sqlite3.Error):
            registro.registro.exception("No se pudieron limpiar las portadas sin uso")

        ventana = VentanaPrincipal(con)
        restaurar_geometria(ventana)
        ventana.show()
        codigo = app.exec()
        guardar_geometria(ventana)
        if not ventana.restaurado:  # tras restaurar, la conexión ya está cerrada
            copia_al_salir(con)
            con.close()
        registro.registro.info("Cierre normal")
        return codigo
    finally:
        candado.unlock()


# ---------------------------------------------------------------- instancia única

def bloquear_instancia() -> QLockFile | None:
    """Impide abrir dos LibriDomus sobre la misma carpeta de datos (se pisarían al guardar).

    El bloqueo se libera solo si el programa se cierra de forma inesperada (Qt comprueba si el
    proceso que lo creó sigue vivo).
    """
    candado = QLockFile(str(rutas.carpeta_datos() / "libridomus.lock"))
    candado.setStaleLockTime(0)
    return candado if candado.tryLock(300) else None


# ---------------------------------------------------------------- errores

_mostrando_error = False


def instalar_gestor_errores() -> None:
    """Cualquier error no previsto se anota en registro.log y se explica al usuario, en lugar de
    perderse en silencio (el .exe no tiene consola) o cerrar el programa."""

    def gestor(tipo, valor, traza):
        if issubclass(tipo, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(tipo, valor, traza)
            return
        registro.registro.error("Error no controlado", exc_info=(tipo, valor, traza))
        mostrar_error(valor)

    sys.excepthook = gestor
    threading.excepthook = lambda args: gestor(args.exc_type, args.exc_value, args.exc_traceback)


def mostrar_error(error: BaseException) -> None:
    global _mostrando_error
    app = QApplication.instance()
    if app is None or _mostrando_error or QThread.currentThread() is not app.thread():
        return  # fuera del hilo de la interfaz solo se anota en el registro
    _mostrando_error = True
    try:
        comun.error(None, registro.mensaje_para_usuario(error)
                    + "\n\nEl detalle técnico se ha guardado en «registro.log», en la carpeta de datos.")
    finally:
        _mostrando_error = False


# ---------------------------------------------------------------- apertura de los datos

def abrir_datos() -> sqlite3.Connection | None:
    """Abre la base de datos comprobando su integridad; si está dañada, ofrece recuperarla."""
    for _intento in range(3):
        try:
            return conexion.abrir(comprobar_integridad=True, exigir_escritura=True)
        except conexion.BaseDatosDanada as error:
            registro.registro.error("Base de datos dañada al arrancar: %s", error)
            if not recuperar_base_danada(error):
                return None
        except conexion.ErrorBaseDatos as error:
            registro.registro.error("No se pudo abrir la base de datos: %s", error)
            comun.error(None, str(error))
            return None
    return None


def ultima_copia_valida():
    """La copia de seguridad más reciente que pasa todas las comprobaciones (o None)."""
    from ..servicios import copias

    for copia in copias.listar():
        try:
            copias.validar_base_datos(copia.ruta)
            return copia
        except copias.ErrorCopia:
            registro.registro.warning("Copia no válida descartada: %s", copia.ruta.name)
    return None


def recuperar_base_danada(error: Exception) -> bool:
    """Pregunta qué hacer. El archivo dañado nunca se borra: se aparta con otro nombre."""
    from ..servicios import copias

    danada = rutas.ruta_base_datos()
    apartada = danada.with_name(f"biblioteca_danada_{datetime.now():%Y%m%d_%H%M%S}.db")
    copia = ultima_copia_valida()
    texto = f"Los datos de {NOMBRE} están dañados y no se pueden abrir.\n\n({error})"
    if copia is not None:
        detalle = (f"Hay una copia de seguridad válida del {copia.fecha:%d/%m/%Y a las %H:%M}.\n\n"
                   f"Si la restauras, el archivo dañado se guardará aparte como «{apartada.name}» "
                   "por si hiciera falta.")
        opciones = ["Restaurar la copia", "Salir"]
    else:
        detalle = ("No se ha encontrado ninguna copia de seguridad válida en la carpeta de copias.\n\n"
                   "Puedes empezar con datos nuevos (el archivo dañado se guardará aparte como "
                   f"«{apartada.name}») o salir y restaurar después una copia manual desde "
                   "Archivo › Restaurar copia de seguridad.")
        opciones = ["Empezar con datos nuevos", "Salir"]
    if comun.preguntar(texto, detalle, opciones) != 0:
        return False
    try:
        os.replace(danada, apartada)
        diario = danada.with_name(danada.name + "-journal")
        if diario.exists():
            os.replace(diario, apartada.with_name(apartada.name + "-journal"))
        if copia is not None:
            copias.restaurar(None, copia.ruta)
            registro.registro.info("Restaurada la copia %s tras detectar datos dañados", copia.ruta.name)
    except (OSError, copias.ErrorCopia) as fallo:
        registro.registro.exception("Falló la recuperación")
        comun.error(None, f"No se ha podido recuperar: {fallo}")
        return False
    return True


# ---------------------------------------------------------------- ventana y cierre

def restaurar_geometria(ventana) -> None:
    from ..servicios import configuracion

    guardada = configuracion.obtener("ventana")
    if guardada:
        try:
            ventana.restoreGeometry(QByteArray.fromBase64(guardada.encode("ascii")))
        except (UnicodeEncodeError, ValueError):
            pass  # una preferencia dañada no impide arrancar


def guardar_geometria(ventana) -> None:
    from ..servicios import configuracion

    ajustes = configuracion.cargar()
    ajustes["ventana"] = bytes(ventana.saveGeometry().toBase64()).decode("ascii")
    try:
        configuracion.guardar(ajustes)
    except OSError:
        pass


def copia_al_salir(con) -> None:
    """Copia automática de la base de datos al cerrar (si está activada en Preferencias)."""
    from ..servicios import configuracion, copias

    ajustes = configuracion.cargar()
    if not ajustes["copia_al_cerrar"]:
        return
    try:
        copias.copia_automatica(con, int(ajustes["copias_a_conservar"]))
    except (OSError, sqlite3.Error) as error:
        registro.registro.exception("Falló la copia automática al cerrar")
        QMessageBox.warning(None, NOMBRE, f"No se ha podido hacer la copia automática:\n{error}")


if __name__ == "__main__":
    sys.exit(ejecutar(sys.argv))
