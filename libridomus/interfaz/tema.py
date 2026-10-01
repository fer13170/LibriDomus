"""Aspecto de LibriDomus: paletas (clara y oscura), escala de la interfaz, fuente,
hoja de estilos e iconos Lucide coloreados según el tema.

Los colores salen del logotipo: ocre, madera, terracota y verde azulado.
Todo se recalcula en ``aplicar`` y se puede cambiar en caliente (Preferencias o menú Ver).
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"
ICONOS = RECURSOS / "iconos"

ESCALAS = [("Pequeño", 0.9), ("Normal", 1.0), ("Grande", 1.15), ("Muy grande", 1.3), ("Enorme", 1.5)]
TEMAS = [("claro", "Claro"), ("oscuro", "Oscuro"), ("sistema", "Según Windows")]
FUENTE_POR_DEFECTO = "Segoe UI"
PUNTOS_BASE = 10.0  # tamaño de letra con la escala «Normal»

PALETAS = {
    "claro": {
        "fondo": "#F7F3EC", "superficie": "#FFFFFF", "lateral": "#EFE8DC", "borde": "#E2D8C8",
        "borde_fuerte": "#CBBEAA", "texto": "#2B2520", "texto_suave": "#7A6E62",
        "primario": "#246C6C", "primario_hover": "#1B5656", "primario_texto": "#FFFFFF",
        "seleccion": "#D3E6E3", "seleccion_texto": "#16302F", "acento": "#C4552E", "ocre": "#D9A556",
        "peligro": "#B3261E", "fila_alterna": "#FBF8F3", "hover": "#F1EBE1", "sombra": "#00000014",
    },
    "oscuro": {
        "fondo": "#1C1A17", "superficie": "#25221E", "lateral": "#211F1B", "borde": "#3A342D",
        "borde_fuerte": "#4F473E", "texto": "#EDE6DB", "texto_suave": "#A99D8D",
        "primario": "#4FA3A0", "primario_hover": "#63B6B2", "primario_texto": "#0F1716",
        "seleccion": "#2B4C4A", "seleccion_texto": "#F2FBFA", "acento": "#E07A52", "ocre": "#E0B266",
        "peligro": "#E5766E", "fila_alterna": "#29261F", "hover": "#302C26", "sombra": "#00000040",
    },
}


class _Avisador(QObject):
    """Emite ``cambiado`` cuando cambia el tema o la escala (las ventanas recargan iconos)."""

    cambiado = Signal()


avisador = _Avisador()


@dataclass
class Estado:
    nombre: str = "claro"      # paleta efectiva ('claro' u 'oscuro')
    escala: float = 1.0
    fuente: str = FUENTE_POR_DEFECTO


estado = Estado()
_cache_iconos: dict[tuple, QIcon] = {}


# ---------------------------------------------------------------- utilidades

def color(clave: str) -> str:
    return PALETAS[estado.nombre][clave]


def px(valor: float) -> int:
    """Medida en píxeles escalada según el tamaño de interfaz elegido."""
    return max(1, round(valor * estado.escala))


def paleta_efectiva(tema: str, app: QApplication | None = None) -> str:
    if tema in PALETAS:
        return tema
    app = app or QApplication.instance()
    try:
        oscuro = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt anterior a 6.5
        oscuro = False
    return "oscuro" if oscuro else "claro"


# ---------------------------------------------------------------- iconos

def existe_icono(nombre: str) -> bool:
    return bool(nombre) and (ICONOS / f"{nombre}.svg").exists()


def _pixmap_svg(nombre: str, tono: str, lado: int, dpr: float) -> QPixmap:
    svg = (ICONOS / f"{nombre}.svg").read_text(encoding="utf-8").replace("currentColor", tono)
    renderizador = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    real = max(1, round(lado * dpr))
    imagen = QImage(real, real, QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderizador.render(pintor, QRectF(0, 0, real, real))
    pintor.end()
    mapa = QPixmap.fromImage(imagen)
    mapa.setDevicePixelRatio(dpr)
    return mapa


def _pixmap_texto(texto: str, lado: int, dpr: float) -> QPixmap:
    """Para tipos antiguos con un emoji como icono."""
    real = max(1, round(lado * dpr))
    mapa = QPixmap(real, real)
    mapa.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(mapa)
    fuente = QFont("Segoe UI Emoji")
    fuente.setPixelSize(int(real * 0.8))
    pintor.setFont(fuente)
    pintor.drawText(QRectF(0, 0, real, real), Qt.AlignmentFlag.AlignCenter, texto)
    pintor.end()
    mapa.setDevicePixelRatio(dpr)
    return mapa


def icono(nombre: str, tono: str = "texto", lado: int | None = None) -> QIcon:
    """Icono Lucide coloreado con un color del tema ('texto', 'primario'...) o un color '#rrggbb'.

    Si ``nombre`` no es un icono conocido (p. ej. un emoji de una versión anterior), se dibuja el texto.
    """
    lado = lado or px(18)
    color_real = tono if tono.startswith("#") else color(tono)
    clave = (nombre, color_real, lado)
    if clave in _cache_iconos:
        return _cache_iconos[clave]
    app = QApplication.instance()
    dpr = max(2.0, app.devicePixelRatio()) if app else 2.0
    resultado = QIcon()
    if existe_icono(nombre):
        resultado.addPixmap(_pixmap_svg(nombre, color_real, lado, dpr), QIcon.Mode.Normal)
        resultado.addPixmap(_pixmap_svg(nombre, color("borde_fuerte"), lado, dpr), QIcon.Mode.Disabled)
        if tono == "texto":  # en la fila seleccionada el icono toma el color del texto seleccionado
            resultado.addPixmap(_pixmap_svg(nombre, color("seleccion_texto"), lado, dpr), QIcon.Mode.Selected)
    elif nombre:
        resultado.addPixmap(_pixmap_texto(nombre, lado, dpr))
    _cache_iconos[clave] = resultado
    return resultado


def _imagen_para_qss(nombre: str, tono: str, lado: int) -> str:
    """Las hojas de estilo necesitan un archivo: se genera en la carpeta temporal."""
    carpeta = Path(tempfile.gettempdir()) / "libridomus_estilo"
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f"{nombre}_{tono.strip('#')}_{lado}.png"
    if not ruta.exists():
        _pixmap_svg(nombre, tono, lado, 2.0).save(str(ruta))
    return ruta.as_posix()


# ---------------------------------------------------------------- aplicar

def aplicar(app: QApplication, tema: str = "claro", escala: float = 1.0, fuente: str = "") -> None:
    estado.nombre = paleta_efectiva(tema, app)
    try:  # nunca fuera de los tamaños ofrecidos, venga de donde venga el valor
        estado.escala = min(max(float(escala), ESCALAS[0][1]), ESCALAS[-1][1])
    except (TypeError, ValueError):
        estado.escala = 1.0
    estado.fuente = fuente or FUENTE_POR_DEFECTO
    _cache_iconos.clear()
    app.setStyle("Fusion")
    letra = QFont(estado.fuente)
    letra.setPointSizeF(PUNTOS_BASE * estado.escala)
    app.setFont(letra)
    app.setPalette(_paleta_qt())
    app.setStyleSheet(hoja_de_estilos())
    avisador.cambiado.emit()


def _paleta_qt() -> QPalette:
    c = PALETAS[estado.nombre]
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: c["fondo"], QPalette.ColorRole.WindowText: c["texto"],
        QPalette.ColorRole.Base: c["superficie"], QPalette.ColorRole.AlternateBase: c["fila_alterna"],
        QPalette.ColorRole.Text: c["texto"], QPalette.ColorRole.Button: c["superficie"],
        QPalette.ColorRole.ButtonText: c["texto"], QPalette.ColorRole.Highlight: c["seleccion"],
        QPalette.ColorRole.HighlightedText: c["seleccion_texto"], QPalette.ColorRole.ToolTipBase: c["superficie"],
        QPalette.ColorRole.ToolTipText: c["texto"], QPalette.ColorRole.PlaceholderText: c["texto_suave"],
        QPalette.ColorRole.Link: c["primario"], QPalette.ColorRole.Mid: c["borde_fuerte"],
        QPalette.ColorRole.Light: c["superficie"], QPalette.ColorRole.Dark: c["borde_fuerte"],
    }
    for rol, valor in roles.items():
        p.setColor(rol, QColor(valor))
    for rol in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, rol, QColor(c["borde_fuerte"]))
    return p


def hoja_de_estilos() -> str:
    c = PALETAS[estado.nombre]
    r = px(6)          # radio de las esquinas
    pad = px(6)        # relleno de los campos
    alto = px(30)      # alto de campos y botones
    flecha_abajo = _imagen_para_qss("chevron-down", c["texto_suave"], 16)
    flecha_arriba = _imagen_para_qss("chevron-up", c["texto_suave"], 16)
    marca = _imagen_para_qss("check", c["primario_texto"], 16)
    return f"""
    QWidget {{ color: {c['texto']}; }}
    QMainWindow, QDialog {{ background: {c['fondo']}; }}
    QToolTip {{ background: {c['superficie']}; color: {c['texto']}; border: 1px solid {c['borde']};
               padding: {px(4)}px {px(6)}px; }}

    /* --- barra superior y menús --- */
    QMenuBar {{ background: {c['fondo']}; border: none; padding: {px(2)}px {px(4)}px; }}
    QMenuBar::item {{ padding: {px(4)}px {px(10)}px; border-radius: {r}px; background: transparent; }}
    QMenuBar::item:selected {{ background: {c['hover']}; }}
    QMenu {{ background: {c['superficie']}; border: 1px solid {c['borde']}; padding: {px(4)}px; }}
    QMenu::item {{ padding: {px(6)}px {px(24)}px {px(6)}px {px(10)}px; border-radius: {px(4)}px; }}
    QMenu::item:selected {{ background: {c['seleccion']}; color: {c['seleccion_texto']}; }}
    QMenu::item:disabled {{ color: {c['borde_fuerte']}; }}
    QMenu::separator {{ height: 1px; background: {c['borde']}; margin: {px(4)}px {px(6)}px; }}
    QMenu::icon {{ padding-left: {px(6)}px; }}
    QToolBar {{ background: {c['superficie']}; border: none; border-bottom: 1px solid {c['borde']};
               padding: {px(6)}px {px(10)}px; spacing: {px(6)}px; }}
    QToolBar::separator {{ width: 1px; background: {c['borde']}; margin: {px(4)}px {px(6)}px; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r}px;
                  padding: {px(5)}px {px(8)}px; }}
    QToolButton:hover {{ background: {c['hover']}; border-color: {c['borde']}; }}
    QToolButton:pressed, QToolButton:checked {{ background: {c['seleccion']}; }}
    QToolButton#primario {{ background: {c['primario']}; color: {c['primario_texto']}; font-weight: 600; }}
    QToolButton#primario:hover {{ background: {c['primario_hover']}; }}
    QToolButton::menu-button {{ border: none; width: {px(16)}px; }}
    QToolButton[popupMode="1"] {{ padding-right: {px(22)}px; }}
    QStatusBar {{ background: {c['fondo']}; color: {c['texto_suave']}; border-top: 1px solid {c['borde']}; }}
    QStatusBar::item {{ border: none; }}

    /* --- botones --- */
    QPushButton {{ background: {c['superficie']}; border: 1px solid {c['borde_fuerte']}; border-radius: {r}px;
                  padding: {px(4)}px {px(14)}px; min-height: {alto - px(10)}px; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:pressed {{ background: {c['seleccion']}; }}
    QPushButton:disabled {{ color: {c['borde_fuerte']}; border-color: {c['borde']}; }}
    QPushButton#primario, QPushButton:default {{ background: {c['primario']}; color: {c['primario_texto']};
                  border-color: {c['primario']}; font-weight: 600; }}
    QPushButton#primario:hover, QPushButton:default:hover {{ background: {c['primario_hover']}; }}
    QPushButton#primario:disabled {{ background: {c['borde']}; border-color: {c['borde']}; color: {c['texto_suave']}; }}
    QPushButton#peligro {{ color: {c['peligro']}; border-color: {c['peligro']}; }}
    QPushButton#enlace {{ border: none; background: transparent; color: {c['primario']}; padding: 0 {px(4)}px;
                  text-align: left; min-height: 0; }}
    QPushButton#enlace:hover {{ text-decoration: underline; }}
    QPushButton#plano {{ border: none; background: transparent; padding: {px(4)}px; min-height: 0; }}
    QPushButton#plano:hover {{ background: {c['hover']}; }}

    /* --- campos --- */
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QFontComboBox {{
        background: {c['superficie']}; border: 1px solid {c['borde_fuerte']}; border-radius: {r}px;
        padding: {px(3)}px {pad}px; min-height: {alto - px(10)}px;
        selection-background-color: {c['seleccion']}; selection-color: {c['seleccion_texto']}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 1px solid {c['primario']}; }}
    QLineEdit:disabled, QComboBox:disabled {{ background: {c['fondo']}; color: {c['texto_suave']}; }}
    QLineEdit#busqueda {{ border-radius: {px(18)}px; padding: {px(5)}px {px(14)}px; background: {c['fondo']};
                         min-width: {px(270)}px; }}
    QLineEdit#busqueda:focus {{ background: {c['superficie']}; }}
    QComboBox::drop-down, QFontComboBox::drop-down {{ border: none; width: {px(24)}px; }}
    QComboBox::down-arrow, QFontComboBox::down-arrow {{ image: url("{flecha_abajo}"); width: {px(14)}px; height: {px(14)}px; }}
    QComboBox QAbstractItemView {{ background: {c['superficie']}; border: 1px solid {c['borde']};
        selection-background-color: {c['seleccion']}; selection-color: {c['seleccion_texto']}; outline: 0; }}
    QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: {px(18)}px; }}
    QSpinBox::up-arrow {{ image: url("{flecha_arriba}"); width: {px(12)}px; height: {px(12)}px; }}
    QSpinBox::down-arrow {{ image: url("{flecha_abajo}"); width: {px(12)}px; height: {px(12)}px; }}

    /* --- casillas (visibles también en el tema oscuro) --- */
    QCheckBox {{ spacing: {px(6)}px; }}
    QCheckBox::indicator, QTreeView::indicator, QListView::indicator, QTableView::indicator {{
        width: {px(15)}px; height: {px(15)}px; border: 1px solid {c['borde_fuerte']}; border-radius: {px(4)}px;
        background: {c['superficie']}; }}
    QCheckBox::indicator:hover, QTreeView::indicator:hover {{ border-color: {c['primario']}; }}
    QCheckBox::indicator:checked, QTreeView::indicator:checked, QListView::indicator:checked,
    QTableView::indicator:checked {{ background: {c['primario']}; border-color: {c['primario']};
        image: url("{marca}"); }}
    QCheckBox::indicator:disabled {{ background: {c['fondo']}; border-color: {c['borde']}; }}
    QToolButton[popupMode="2"] {{ padding-right: {px(20)}px; }}
    QToolButton::menu-indicator {{ image: url("{flecha_abajo}"); subcontrol-origin: padding;
        subcontrol-position: center right; width: {px(12)}px; height: {px(12)}px; right: {px(4)}px; }}

    /* --- listas, árboles y tablas --- */
    QTreeView, QTableView, QListView, QListWidget, QTreeWidget, QTableWidget {{
        background: {c['superficie']}; border: 1px solid {c['borde']}; border-radius: {r}px;
        alternate-background-color: {c['fila_alterna']}; outline: 0;
        selection-background-color: {c['seleccion']}; selection-color: {c['seleccion_texto']}; }}
    QTreeView::item, QListView::item {{ padding: {px(4)}px {px(2)}px; border-radius: {px(4)}px; }}
    QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background: {c['hover']}; }}
    QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
        background: {c['seleccion']}; color: {c['seleccion_texto']}; }}
    QTableView {{ gridline-color: transparent; }}
    QTableView::item {{ padding: 0 {px(6)}px; border-bottom: 1px solid {c['fila_alterna']}; }}
    QTreeView#lateral {{ background: {c['lateral']}; border: none; }}
    QHeaderView::section {{ background: {c['superficie']}; color: {c['texto_suave']}; font-weight: 600;
        border: none; border-bottom: 1px solid {c['borde']}; padding: {px(6)}px {px(8)}px; }}
    QHeaderView::section:hover {{ color: {c['texto']}; }}
    QHeaderView::up-arrow {{ image: url("{flecha_arriba}"); width: {px(12)}px; }}
    QHeaderView::down-arrow {{ image: url("{flecha_abajo}"); width: {px(12)}px; }}
    QTableCornerButton::section {{ background: {c['superficie']}; border: none; }}

    /* --- agrupaciones --- */
    QGroupBox {{ background: {c['superficie']}; border: 1px solid {c['borde']}; border-radius: {px(8)}px;
                margin-top: {px(22)}px; padding: {px(12)}px {px(10)}px {px(8)}px {px(10)}px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: {px(10)}px; top: {px(2)}px; padding: 0 {px(2)}px;
                       color: {c['primario']}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QSplitter::handle {{ background: {c['borde']}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QTabWidget::pane {{ border: 1px solid {c['borde']}; border-radius: {r}px; background: {c['superficie']}; top: -1px; }}
    QTabBar::tab {{ padding: {px(6)}px {px(14)}px; border: none; color: {c['texto_suave']}; }}
    QTabBar::tab:selected {{ color: {c['primario']}; border-bottom: 2px solid {c['primario']}; }}

    /* --- barras de desplazamiento finas --- */
    QScrollBar:vertical {{ background: transparent; width: {px(10)}px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: {px(10)}px; margin: 2px; }}
    QScrollBar::handle {{ background: {c['borde_fuerte']}; border-radius: {px(4)}px; min-height: {px(30)}px;
                         min-width: {px(30)}px; }}
    QScrollBar::handle:hover {{ background: {c['texto_suave']}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; border: none; width: 0; height: 0; }}

    /* --- textos con nombre --- */
    QLabel#titulo_app {{ font-size: {px(15)}pt; font-weight: 700; color: {c['texto']}; }}
    QLabel#titulo_seccion {{ font-size: {PUNTOS_BASE * estado.escala * 1.35:.1f}pt; font-weight: 700; }}
    QLabel#titulo_panel {{ font-size: {PUNTOS_BASE * estado.escala * 1.25:.1f}pt; font-weight: 700; }}
    QLabel#encabezado {{ color: {c['texto_suave']}; font-weight: 700; letter-spacing: 1px;
                         font-size: {PUNTOS_BASE * estado.escala * 0.85:.1f}pt; }}
    QLabel#suave, QLabel#contador {{ color: {c['texto_suave']}; }}
    QLabel#ruta {{ color: {c['primario']}; }}
    QLabel#chip {{ background: {c['seleccion']}; color: {c['seleccion_texto']}; border-radius: {px(9)}px;
                  padding: {px(1)}px {px(8)}px; }}
    QLabel#aviso {{ background: {c['hover']}; border: 1px solid {c['borde']}; border-radius: {r}px;
                   padding: {px(8)}px; }}
    QWidget#lateral, QWidget#panel_detalle {{ background: {c['lateral']}; }}
    QFrame#tarjeta {{ background: {c['superficie']}; border: 1px solid {c['borde']}; border-radius: {px(10)}px; }}
    QFrame#portada {{ background: {c['fondo']}; border: 1px dashed {c['borde_fuerte']}; border-radius: {px(6)}px; }}
    """
