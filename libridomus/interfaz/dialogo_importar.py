"""Importar elementos desde Excel (.xlsx) o CSV.

El usuario elige el archivo, comprueba a qué dato va cada columna (se propone según el nombre
de la columna), elige el tipo y la ubicación por defecto e importa. Al terminar se muestra un
resumen con lo omitido y los avisos, y se puede deshacer la importación entera.
"""

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QPlainTextEdit, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..datos import elementos, tipos
from ..servicios import importar
from ..servicios.importar import ErrorImportar, Informe, Tabla
from . import comun, tema
from .selector_ubicacion import CampoUbicacion

FILAS_MUESTRA = 30


def filas_texto(n: int) -> str:
    """1 -> '1 fila', 1500 -> '1.500 filas'."""
    return f"{n:,} fila{'s' if n != 1 else ''}".replace(",", ".")


class DialogoImportar(QDialog):
    def __init__(self, con: sqlite3.Connection, ubicacion_id: int | None = None, parent=None):
        super().__init__(parent)
        self.con = con
        self.tabla: Tabla | None = None
        self.combos: list[QComboBox] = []
        self.creados: list[int] = []
        self.destinos = importar.destinos(con)
        self.setWindowTitle("Importar desde Excel o CSV")
        self.resize(tema.px(960), tema.px(720))

        explicacion = QLabel("Elige una hoja de Excel (.xlsx) o un archivo CSV. La primera fila debe tener los "
                             "nombres de las columnas (Título, Autor, Año, ISBN…). Solo el título es obligatorio.",
                             wordWrap=True)
        self.ruta = QLabel("Ningún archivo elegido", objectName="suave", textFormat=Qt.TextFormat.PlainText)
        b_elegir = comun.boton("Elegir archivo…", "folder-open", "primario")
        b_plantilla = comun.boton("Guardar una plantilla de Excel…", "download", "enlace")
        b_elegir.clicked.connect(lambda: self.elegir())
        b_plantilla.clicked.connect(lambda: self.guardar_plantilla())
        fila_archivo = QHBoxLayout()
        fila_archivo.addWidget(b_elegir)
        fila_archivo.addWidget(self.ruta, 1)
        fila_archivo.addWidget(b_plantilla)

        # Correspondencia columna -> dato
        self.form_columnas = QFormLayout()
        contenedor = QWidget()
        contenedor.setLayout(self.form_columnas)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setWidget(contenedor)
        desplazable.setMinimumWidth(tema.px(360))
        caja_columnas = QVBoxLayout()
        caja_columnas.addWidget(desplazable)
        self.grupo_columnas = QGroupBox("¿Qué contiene cada columna?")
        self.grupo_columnas.setLayout(caja_columnas)

        # Muestra de las primeras filas
        self.muestra = QTableWidget()
        self.muestra.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.muestra.setWordWrap(False)
        self.muestra.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        caja_muestra = QVBoxLayout()
        caja_muestra.addWidget(self.muestra)
        self.grupo_muestra = QGroupBox("Primeras filas del archivo")
        self.grupo_muestra.setLayout(caja_muestra)

        centro = QHBoxLayout()
        centro.addWidget(self.grupo_columnas, 2)
        centro.addWidget(self.grupo_muestra, 3)

        # Opciones
        self.tipo = QComboBox()
        for t in tipos.listar(con, con_campos=False):
            self.tipo.addItem(tema.icono(t.icono or "package", "primario"), t.nombre, t.id)
        self.ubicacion = CampoUbicacion(con)
        self.ubicacion.establecer(ubicacion_id)
        self.omitir_repetidos = QCheckBox("No importar las filas cuyo ISBN / identificador ya esté en la colección")
        self.omitir_repetidos.setChecked(True)
        opciones = QFormLayout()
        opciones.addRow("Tipo si la fila no lo indica:", self.tipo)
        opciones.addRow("Ubicación si la fila no la indica:", self.ubicacion)
        opciones.addRow("", self.omitir_repetidos)
        grupo_opciones = QGroupBox("Opciones")
        grupo_opciones.setLayout(opciones)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.b_importar = botones.addButton("Importar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_importar.setEnabled(False)
        botones.accepted.connect(lambda: self.importar())
        botones.rejected.connect(self.reject)

        capa = QVBoxLayout(self)
        capa.addWidget(explicacion)
        capa.addLayout(fila_archivo)
        capa.addLayout(centro, 1)
        capa.addWidget(grupo_opciones)
        capa.addWidget(botones)
        for grupo in (self.grupo_columnas, self.grupo_muestra):
            grupo.setEnabled(False)

    # ------------------------------------------------------------ archivo

    def elegir(self, ruta: str | None = None) -> bool:
        if ruta is None:
            ruta, _ = QFileDialog.getOpenFileName(self, "Elegir archivo", "",
                                                  "Excel o CSV (*.xlsx *.xlsm *.csv *.txt);;Todos los archivos (*)")
            if not ruta:
                return False
        try:
            with comun.ocupado(self, "Leyendo el archivo…"):
                tabla = importar.leer_tabla(ruta)
        except ErrorImportar as e:
            comun.error(self, str(e))
            return False
        self.tabla = tabla
        self.ruta.setText(f"{Path(ruta).name} · {filas_texto(len(tabla.filas))}")
        self._mostrar_columnas()
        self._mostrar_muestra()
        for grupo in (self.grupo_columnas, self.grupo_muestra):
            grupo.setEnabled(True)
        self._actualizar_boton()
        return True

    def _mostrar_columnas(self) -> None:
        while self.form_columnas.rowCount():
            self.form_columnas.removeRow(0)
        self.combos = []
        for cabecera in self.tabla.cabeceras:
            combo = QComboBox()
            combo.addItem("— No importar —", importar.IGNORAR)
            for clave, nombre in self.destinos:
                combo.addItem(nombre, clave)
            combo.setCurrentIndex(max(0, combo.findData(importar.sugerir_destino(cabecera, self.destinos))))
            combo.currentIndexChanged.connect(lambda _i: self._actualizar_boton())
            rotulo = QLabel(cabecera, textFormat=Qt.TextFormat.PlainText)
            rotulo.setToolTip(cabecera)
            self.form_columnas.addRow(rotulo, combo)
            self.combos.append(combo)

    def _mostrar_muestra(self) -> None:
        filas = self.tabla.filas[:FILAS_MUESTRA]
        self.muestra.clear()
        self.muestra.setColumnCount(len(self.tabla.cabeceras))
        self.muestra.setRowCount(len(filas))
        self.muestra.setHorizontalHeaderLabels(self.tabla.cabeceras)
        for f, fila in enumerate(filas):
            for c, valor in enumerate(fila):
                self.muestra.setItem(f, c, QTableWidgetItem(valor))
        self.muestra.resizeColumnsToContents()
        for c in range(self.muestra.columnCount()):
            self.muestra.setColumnWidth(c, min(self.muestra.columnWidth(c), tema.px(240)))

    def mapa(self) -> dict[int, str]:
        return {n: combo.currentData() for n, combo in enumerate(self.combos) if combo.currentData()}

    def _actualizar_boton(self) -> None:
        tiene_titulo = "titulo" in self.mapa().values()
        n = len(self.tabla.filas) if self.tabla else 0
        self.b_importar.setEnabled(bool(n) and tiene_titulo)
        self.b_importar.setText(f"Importar {filas_texto(n)}" if n else "Importar")
        self.b_importar.setToolTip("" if tiene_titulo else "Indica qué columna contiene el título")

    def guardar_plantilla(self, destino: str | None = None) -> bool:
        if destino is None:
            destino, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla", "plantilla_LibriDomus.xlsx",
                                                     "Excel (*.xlsx)")
            if not destino:
                return False
        try:
            importar.escribir_plantilla(destino)
        except OSError as e:
            comun.error(self, f"No se ha podido guardar la plantilla: {e}")
            return False
        comun.aviso(self, f"Plantilla guardada en:\n{destino}\n\nRellénala en Excel (una fila por objeto) y "
                          "vuelve aquí para importarla.")
        return True

    # ------------------------------------------------------------ importación

    def importar(self) -> Informe | None:
        if not self.tabla:
            return None
        try:
            with comun.ocupado(self, "Importando…"):
                informe = importar.importar(self.con, self.tabla, self.mapa(), self.tipo.currentData(),
                                            self.ubicacion.valor(), self.omitir_repetidos.isChecked(),
                                            self._progreso)
        except ErrorImportar as e:
            comun.error(self, str(e))
            return None
        self.creados = informe.creados
        resumen = ResumenImportacion(informe, self)
        resumen.exec()
        if resumen.deshacer:
            with comun.ocupado(self, "Deshaciendo la importación…"):
                elementos.borrar(self.con, self.creados)
            self.creados = []
            comun.aviso(self, "Importación deshecha: no se ha añadido nada.")
            return informe
        self.accept()
        return informe

    def _progreso(self, hechas: int, total: int) -> None:
        self.b_importar.setText(f"Importando… {hechas:,} de {total:,}".replace(",", "."))
        QApplication.processEvents()


class ResumenImportacion(QDialog):
    """Lo que ha pasado al importar, con la opción de deshacerlo todo."""

    def __init__(self, informe: Informe, parent=None):
        super().__init__(parent)
        self.deshacer = False
        self.setWindowTitle("Resultado de la importación")
        self.resize(tema.px(640), tema.px(460))
        n = len(informe.creados)
        titulo = QLabel(f"Se han añadido {n:,} elemento{'s' if n != 1 else ''}.".replace(",", "."),
                        objectName="titulo_seccion")
        lineas = []
        if informe.omitidos:
            lineas.append(f"NO IMPORTADAS ({len(informe.omitidos)}):")
            lineas += [f"  Fila {fila}: {motivo}" for fila, motivo in informe.omitidos]
            lineas.append("")
        if informe.avisos:
            lineas.append(f"IMPORTADAS CON AVISOS ({len(informe.avisos)}):")
            lineas += [f"  Fila {fila}: {texto_}" for fila, texto_ in informe.avisos]
            lineas.append("")
        if informe.categorias_nuevas:
            lineas.append(f"CATEGORÍAS NUEVAS AÑADIDAS AL CATÁLOGO ({len(informe.categorias_nuevas)}):")
            lineas.append("  " + ", ".join(informe.categorias_nuevas))
            lineas.append("")
        if not lineas:
            lineas.append("Todas las filas se han importado sin problemas.")
        else:
            lineas.append("Lo que no encajaba en ningún campo se ha guardado en las notas de cada elemento.")
        detalle = QPlainTextEdit("\n".join(lineas))
        detalle.setReadOnly(True)
        botones = QDialogButtonBox()
        b_bien = botones.addButton("Aceptar", QDialogButtonBox.ButtonRole.AcceptRole)
        b_deshacer = botones.addButton("Deshacer la importación", QDialogButtonBox.ButtonRole.DestructiveRole)
        b_deshacer.setEnabled(bool(n))
        b_bien.setDefault(True)
        botones.accepted.connect(self.accept)
        b_deshacer.clicked.connect(self._deshacer)
        capa = QVBoxLayout(self)
        capa.addWidget(titulo)
        capa.addWidget(detalle, 1)
        capa.addWidget(botones)

    def _deshacer(self) -> None:
        if comun.confirmar(self, "¿Borrar todos los elementos que se acaban de importar?"):
            self.deshacer = True
            self.accept()
