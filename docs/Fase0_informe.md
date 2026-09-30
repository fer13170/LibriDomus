# Fase 0 — Informe de validación técnica

**Fecha:** 30/09/2026

## Entorno

| Elemento | Versión |
|---|---|
| Python | 3.12 (entorno virtual `.venv`) |
| PySide6 / Qt | 6.11.2 |
| SQLite incluido en Python | 3.49.1 |
| PyInstaller | 6.22.3 |
| segno | 1.6.6 |
| pytest | 9.1.1 |

## Resultados

| Prueba | Resultado |
|---|---|
| FTS5 disponible en el `sqlite3` de Python | ✅ Sí |
| Búsqueda sin acentos y por prefijo (`garc*` y `marquez` encuentran "García Márquez") | ✅ Sí, con `unicode61 remove_diacritics 2` |
| Esquema v1 + datos iniciales (casa, 4 plantas, 10 tipos) | ✅ 8 pruebas automáticas correctas |
| Empaquetado `onedir` con PyInstaller | ✅ ZIP de ~46 MB |
| Autoprueba del `.exe` (`--autoprueba`): SQLite, FTS5, BD, Qt, QR | ✅ CORRECTO |
| `.exe` sin ninguna ruta de Python en el PATH | ✅ CORRECTO |
| Análisis con Windows Defender | ⚠️ **No verificado**: el servicio de Defender está detenido en el equipo de desarrollo y no hay otro antivirus registrado. Queda pendiente probarlo en el equipo de destino |
| Prueba en un Windows limpio (otro equipo) | ⚠️ Pendiente: requiere otra máquina |

## Cobertura de ISBN (10 ISBN reales)

**Hallazgo importante:** el endpoint antiguo de Open Library `api/books?bibkeys=...` devuelve **404**, así que ya no se puede usar. Funcionan:

- `https://openlibrary.org/isbn/{isbn}.json`: registro de **edición**, con el título en español, la editorial, la fecha, las páginas y la portada. Los autores vienen como claves, que hay que resolver con `/authors/{clave}.json`.
- `https://openlibrary.org/search.json?isbn=...`: da el nombre del autor directamente, pero el título es el de la **obra**, que puede estar en otro idioma. Por ejemplo, para *La virgen roja* devuelve "Red virgin and the vision of utopia".

Por eso el programa usa el registro de edición y resuelve los autores aparte.

| ISBN | Open Library | Título | Portada |
|---|---|---|---|
| 978-84-8346-846-3 | ✅ | Gomorra (Roberto Saviano) | ✅ |
| 84-406-2553-7 | ✅ | La conexión gallega (Perfecto Conde) | ❌ |
| 978-84-18909-65-8 | ✅ | María la jabalina (Cristina Durán) | ✅ |
| 978-84-233-6506-7 | ❌ | — | — |
| 978-84-17678-02-9 | ✅ | Esa maldita pared (Flako, Adrián Ramírez) | ✅ |
| 978-84-16400-44-7 | ✅ | La virgen roja (M. M. Talbot, B. Talbot) | ✅ |
| 978-84-1097-534-7 | ❌ | — | — |
| 978-84-19833-46-4 | ❌ | — | — |
| 978-84-617-6783-0 | ❌ | — | — |
| 978-84-127768-5-0 | ❌ | — | — |

**Cobertura de Open Library: 5 de 10** (4 con portada). Los libros más recientes o de editoriales pequeñas no aparecen.

**Google Books sin clave:** responde **429** ("Quota exceeded … Queries per day"). La cuota anónima es compartida y se agota, así que **solo es útil con una clave propia**. El programa permitirá configurarla. Sin clave no se ha podido medir su cobertura.

**Conclusión:** el autocompletado ayuda en aproximadamente la mitad de los casos. La entrada manual rápida (alta masiva) es imprescindible y así se ha diseñado.

## Decisiones derivadas

1. ISBN: `/isbn/{isbn}.json` + `/authors/{clave}.json`. Google Books como segunda fuente solo si hay una clave configurada.
2. La autoprueba (`--autoprueba`) queda integrada en `build.ps1`: si falla, no se genera el ZIP.
