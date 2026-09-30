"""Punto de entrada del programa."""

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--autoprueba" in argv:
        from . import autoprueba

        return autoprueba.ejecutar()

    from .interfaz.aplicacion import ejecutar

    return ejecutar(argv)


if __name__ == "__main__":
    sys.exit(main())
