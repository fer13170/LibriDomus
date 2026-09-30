"""Convierte docs/Manual_de_usuario.md en «Manual de usuario.pdf».

Uso:  .venv\\Scripts\\python build\\generar_manual.py <carpeta_destino>
(build.ps1 lo llama para dejar el PDF junto al .exe).
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from bibliotecario.servicios import informes  # noqa: E402

NOMBRE_PDF = "Manual de usuario.pdf"


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "build" / "salida"
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - necesario para las fuentes
    texto = (RAIZ / "docs" / "Manual_de_usuario.md").read_text(encoding="utf-8")
    paginas = informes.markdown_a_pdf(texto, destino / NOMBRE_PDF, "Bibliotecario Virtual — Manual de usuario")
    print(f"Manual generado: {destino / NOMBRE_PDF} ({paginas} páginas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
