# Bibliotecario Virtual

Aplicación de escritorio para Windows, **sin conexión**, que registra dónde se guarda cada libro, revista, disco, película, videojuego, partitura, álbum de fotos, caja de diapositivas, carpeta o documento de una casa. Organiza la casa en **plantas › habitaciones › muebles › baldas › cajas**, con tantos niveles como hagan falta.

- Catálogo de ubicaciones configurable, que se reorganiza arrastrando nodos.
- Diez tipos de elemento predefinidos, ampliables con tipos y campos propios.
- Búsqueda instantánea sin acentos (SQLite FTS5) y filtros.
- Alta masiva por balda y autocompletado por ISBN (Open Library) cuando hay Internet.
- Portadas, préstamos, etiquetas con QR para imprimir en A4 e informes en PDF.
- Copias de seguridad automáticas y manuales, y restauración.
- Carpeta portable: `BibliotecarioVirtual.exe` + `_internal` + `datos`.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/Manual_de_usuario.md](docs/Manual_de_usuario.md) | Uso del programa (también se genera en PDF junto al `.exe`) |
| [docs/Manual_de_mantenimiento.md](docs/Manual_de_mantenimiento.md) | Preparar el entorno, pruebas, empaquetado y recetas de cambios |
| [docs/Documento_de_diseño.md](docs/Documento_de_diseño.md) | Requisitos, arquitectura, modelo de datos y plan por fases |
| [docs/Fase0_informe.md](docs/Fase0_informe.md) | Validación técnica y cobertura de ISBN |

## Inicio rápido (desarrollo)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q          # pruebas
.venv\Scripts\python BibliotecarioVirtual.py   # abrir el programa
.\build\build.ps1                           # generar el ZIP portable
```
