# Bibliotecario Virtual — Documento de diseño

- **Versión:** 0.1 (borrador para revisión)
- **Fecha:** 30/09/2026
- **Estado:** pendiente de aprobación

---

## 1. Objetivo

Aplicación de escritorio para Windows, **100 % offline** (salvo la consulta opcional de ISBN), que permite registrar **dónde se guarda físicamente** cada elemento de una colección doméstica: libros, revistas, cómics, discos, películas, videojuegos, partituras, álbumes de fotos, diapositivas, carpetas y documentos. También permite **configurar la estructura de la casa** (habitaciones, muebles, estanterías, baldas, cajas…) y **buscar y editar** los elementos.

### 1.1 Qué aporta frente a lo existente

Ya hay gestores de colecciones libres y offline como Tellico, GCstar o Data Crow, pero se centran en la ficha del objeto. La ubicación física suele ser un simple campo de texto. Este programa pone en el centro la **ubicación jerárquica configurable**, que es precisamente lo que se necesita aquí.

---

## 2. Requisitos acordados

| # | Requisito | Decisión |
|---|---|---|
| R1 | Usuarios / volumen | 1 persona, 1 PC, **miles de elementos** (de 2.000 a más de 20.000) |
| R2 | Plataforma | Windows 10/11, sin conexión |
| R3 | Distribución | **Carpeta portable** (`.exe` + `_internal`), entregada en ZIP, sin instalación |
| R4 | Tecnología | **Python** (mantenimiento con nivel básico, así que se prioriza la simplicidad) |
| R5 | Ubicaciones | Árbol de profundidad libre con tipos configurables. **Una sola casa**, aunque el diseño admite añadir más inmuebles. La casa tiene **varias plantas** (inicialmente Sótano, Planta baja, Planta alta y Buhardilla), configurables como el resto del catálogo |
| R6 | Vista de ubicaciones | **Árbol + ruta clicable** (p. ej. `Salón › Estantería A › Balda 3`) |
| R7 | Posición | Solo se registra el **contenedor** (balda, caja…), sin orden interno |
| R8 | Registro | **Cada registro es un objeto físico** (no se distingue entre obra y ejemplar) |
| R9 | Tipos de elemento | **Predefinidos y ampliables** desde el programa (tipos nuevos y campos personalizados) |
| R10 | Captura | Manual, **autocompletado por ISBN** (opcional, con Internet) y **alta masiva por balda** |
| R11 | Campos comunes | Título, creadores, año, notas, etiquetas, ubicación, **estado de conservación**, **valoración + leído/visto/escuchado**, **idioma** |
| R12 | Elementos personales | **Periodo de fechas**, **personas**, **lugar/evento** |
| R13 | Préstamos | **Básicos**: "prestado a" (texto) y fecha, sin historial |
| R14 | Portadas | Imagen asociada a cada elemento |
| R15 | Etiquetas | Folio A4 normal. Cada etiqueta lleva **código + ruta + contenido resumido + QR** |
| R16 | Informes | Listados en PDF (por ubicación, prestados, etc.) |
| R17 | Copias de seguridad | **Automáticas al cerrar** (se conservan las últimas N) + manual + restaurar |
| R18 | Forma de trabajo | Este documento se aprueba primero y después se desarrolla **por fases**, cada una con un ejecutable probado |

**Fuera de alcance, por decisión expresa:** importar desde Excel/CSV, lector de código de barras, varios usuarios o PCs, historial de préstamos, plano de la casa.

---

## 3. Arquitectura y tecnología

| Componente | Elección | Motivo |
|---|---|---|
| Lenguaje | Python ≥ 3.10 (versión exacta a fijar en la Fase 0) | Requisito R4. PySide6 exige Python ≥ 3.10 |
| Interfaz | **PySide6** (Qt for Python, Qt Widgets) | Enlace oficial de Qt. Licencia **LGPL**, que no obliga a publicar el código propio, a diferencia de PyQt6 (GPL). Incluye árboles, tablas, arrastrar y soltar, impresión y PDF |
| Base de datos | **SQLite** (módulo `sqlite3` de la librería estándar) | Un único archivo, sin servidor, ideal para portable y para copias |
| Búsqueda | **SQLite FTS5** con `tokenize='unicode61 remove_diacritics 2'` | Búsqueda de texto completo con prefijos, frases y AND/OR/NOT, ordenada por relevancia (BM25) y sin distinguir acentos ("Garcia" encuentra "García") |
| QR | **segno** | Librería de Python pura, sin dependencias, conforme a ISO/IEC 18004 |
| PDF / impresión | Qt (`QPdfWriter` / `QPainter`) | Sin dependencias adicionales |
| ISBN | Open Library (principal, sin clave) y Google Books (opcional, requiere clave propia) | Consulta con `urllib` de la librería estándar |
| Empaquetado | **PyInstaller en modo `onedir`** | Arranque rápido y menos falsos positivos de antivirus que `onefile`, que se autoextrae en cada arranque |

**Dependencias externas en ejecución:** solo `PySide6` y `segno`. Todo lo demás es librería estándar. Esto reduce al mínimo el esfuerzo de mantenimiento.

### 3.1 Estructura de la carpeta portable

```
BibliotecarioVirtual\
├── BibliotecarioVirtual.exe
├── _internal\               ← generado por PyInstaller (no tocar)
└── datos\
    ├── biblioteca.db        ← toda la información
    ├── portadas\            ← imágenes (redimensionadas y en JPEG)
    ├── copias\              ← copias automáticas (rotación)
    └── config.json          ← preferencias
```

> La carpeta debe estar en un sitio con permiso de escritura (Documentos, Escritorio, USB), **no** en `C:\Archivos de programa`. El programa lo comprobará al arrancar y avisará si no puede escribir.

### 3.2 Capas del código

Tres capas sencillas, con nombres en español para facilitar el mantenimiento:

```
bibliotecario\
├── main.py                  ← punto de entrada
├── datos\                   ← acceso a SQLite
│   ├── esquema.sql
│   ├── conexion.py
│   ├── migraciones.py       ← evolución del esquema entre versiones
│   └── repositorios\        ← un archivo por entidad (ubicaciones, elementos…)
├── servicios\               ← lógica sin interfaz
│   ├── busqueda.py
│   ├── isbn.py
│   ├── copias.py
│   ├── etiquetas.py
│   └── informes.py
└── interfaz\                ← ventanas y diálogos Qt
    ├── ventana_principal.py
    ├── ficha_elemento.py
    ├── editor_ubicaciones.py
    ├── editor_tipos.py
    ├── alta_masiva.py
    └── ...
tests\                       ← pruebas automáticas (pytest)
build\build.ps1              ← genera el ZIP portable con un solo comando
docs\                        ← diseño, manual de usuario, manual de mantenimiento
```

---

## 4. Modelo de datos

### 4.1 Diagrama lógico

```
tipo_ubicacion 1───* ubicacion *───1 ubicacion (padre)
                         │1
                         │
                         *
tipo_elemento 1───* elemento *───* persona   (con rol)
      │1                 │  *───* etiqueta
      *                  │
    campo 1───* valor_campo *───1 elemento
```

### 4.2 Tablas

**Ubicaciones**

| Tabla | Campos principales |
|---|---|
| `tipo_ubicacion` | id, nombre (Casa, Planta, Habitación, Armario, Estantería, Balda, Caja, Cajón…), icono, orden |
| `ubicacion` | id, **padre_id** (nulo = raíz), tipo_id, nombre, **codigo** (único, p. ej. `PB-SAL-EA-B3`), descripcion, orden |

**Datos iniciales**: al crear la base de datos se generan la casa y sus cuatro plantas, en orden físico: Sótano, Planta baja, Planta alta y Buhardilla. Son ubicaciones normales, así que se pueden renombrar, añadir, reordenar o borrar desde el editor de ubicaciones. La jerarquía típica queda así: `Casa › Planta › Habitación › Mueble › Estantería/Balda › Caja…`, aunque no es obligatoria. Por ejemplo, una caja puede colgar directamente del sótano.

Para obtener una ubicación "con todo lo que cuelga de ella" se usa una consulta recursiva (`WITH RECURSIVE`). Así, filtrar por "Salón" encuentra también lo que hay en sus estanterías, baldas y cajas.

**Elementos**

| Tabla | Campos principales |
|---|---|
| `tipo_elemento` | id, nombre, icono, predefinido (sí/no), verbo de consumo ("leído", "visto", "escuchado") |
| `campo` | id, tipo_elemento_id, clave, etiqueta, tipo de dato (texto, texto largo, número, fecha, lista, sí/no), opciones de lista, orden |
| `elemento` | id, tipo_id, **titulo**, subtitulo, **anio**, **fecha_desde / fecha_hasta** (periodo), **idioma**, **estado_conservacion**, **valoracion** (0–5), **consumido** (sí/no), **identificador** (ISBN/EAN/ISSN), **lugar_evento**, **ubicacion_id**, **portada** (archivo), **prestado_a**, **fecha_prestamo**, notas, creado, modificado |
| `valor_campo` | elemento_id, campo_id, valor. Guarda los campos propios de cada tipo |
| `persona` | id, nombre. Se reutiliza para autores, intérpretes, personas que aparecen en fotos, etc. |
| `elemento_persona` | elemento_id, persona_id, **rol** (autor, traductor, ilustrador, intérprete, compositor, director, actor, aparece, propietario…) |
| `etiqueta` / `elemento_etiqueta` | Etiquetas libres (p. ej. "pendiente", "firmado", "herencia abuela") |
| `elemento_fts` | Índice FTS5: título, subtítulo, personas, etiquetas, notas, campos propios, lugar/evento y ruta de ubicación |

**Estado de conservación** (lista): Nuevo · Muy bueno · Bueno · Regular · Deteriorado.

### 4.3 Tipos predefinidos (propuesta para revisar)

| Tipo | Campos propios | Roles de persona |
|---|---|---|
| **Libro** | ISBN, editorial, edición, nº páginas, colección/serie, nº en serie, encuadernación | autor, traductor, ilustrador |
| **Revista / Cómic** | Cabecera/colección, número, editorial, ISSN | autor, guionista, dibujante |
| **Disco** | Soporte (CD, vinilo LP, vinilo single, casete, otro), sello, nº de discos, EAN, lista de pistas | intérprete, compositor |
| **Película** | Soporte (DVD, Blu-ray, VHS, otro), duración, nº de discos, EAN | director, actor |
| **Videojuego** | Plataforma, soporte, EAN | desarrollador |
| **Partitura** | Instrumentación, editorial | compositor, arreglista |
| **Álbum de fotos** | Formato | aparece, fotógrafo |
| **Diapositivas** | Formato (p. ej. 35 mm), contenedor (caja/carro) | aparece, fotógrafo |
| **Carpeta** | Temática (facturas, escrituras, estudios…) | propietario |
| **Mapa / Documento suelto** | Clase de documento, escala (mapas) | autor, propietario |

Los datos personales (periodo, personas, lugar/evento) están disponibles en todos los tipos, pero el formulario los destaca en Álbum, Diapositivas, Carpeta y Documento.

---

## 5. Interfaz

### 5.1 Ventana principal

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [🔍 Buscar…                         ] [Ir a código: ____ ] [+ Nuevo ▾]  │
├──────────────────┬──────────────────────────────────────────────────────┤
│ UBICACIONES      │ Filtros: Tipo ▾  Etiqueta ▾  Estado ▾  Idioma ▾      │
│ ▾ Casa           │          ☐ Solo prestados  ☐ Solo no leídos          │
│  ▸ Sótano        ├──────────────────────────────────────────────────────┤
│  ▾ Planta baja   │ Tipo  │ Título            │ Creador     │ Ubicación  │
│   ▾ Salón        │ 📖    │ Cien años de sol… │ G. Márquez  │ PB›Sal›A›B1│
│    ▾ Estant. A   │ 💿    │ Kind of Blue      │ Miles Davis │ PB›Sal›A›B2│
│      • Balda 1   │ 📷    │ Verano 1985       │ Ana, Luis   │ Sót›C4     │
│  ▸ Planta alta   │  …                                                   │
│  ▸ Buhardilla    │                                                      │
│ (n elementos)    │                          [Mostrando 3 de 4.210]      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

- Al seleccionar un nodo del árbol se filtra la lista, incluidas sus sububicaciones.
- La búsqueda se lanza mientras se escribe, sin distinguir acentos y aceptando prefijos ("garc" encuentra "García").
- **Ir a código**: se escribe el código de una etiqueta (o se pega el texto leído de su QR con el móvil) y el programa salta a esa ubicación.
- Doble clic en un elemento abre su ficha.
- Se pueden seleccionar varios elementos y **moverlos** a otra ubicación de una vez.

### 5.2 Ficha de elemento

- El formulario se construye según el tipo: primero los campos comunes y después los propios.
- **Ubicación**: selector con árbol y ruta visible (`Salón › Estantería A › Balda 3`).
- **Portada**: arrastrar una imagen o elegir un archivo (se redimensiona al guardar).
- **ISBN**: botón "Autocompletar" que rellena título, autores, editorial, año, páginas y portada. Si no hay Internet, avisa y se sigue a mano.
- **Préstamo**: "Prestado a" y fecha, con un botón "Devuelto" que vacía los dos campos.

### 5.3 Editor de ubicaciones (catálogo de la casa)

- Árbol con **arrastrar y soltar** para reorganizar.
- Crear, renombrar y borrar ubicaciones, y asignar tipo y código (el código se sugiere automáticamente).
- **Mover un contenedor completo**: los elementos que contiene viajan con él.
- Si se borra una ubicación con contenido, el programa **obliga a elegir un destino** para los elementos. Nunca se pierden en silencio.
- Gestión de los **tipos de ubicación**.

### 5.4 Editor de tipos de elemento

- Crear tipos nuevos y añadir, ordenar u ocultar campos (texto, número, fecha, lista, sí/no).
- Los tipos predefinidos se pueden ampliar pero no borrar, para no romper datos.

### 5.5 Alta masiva por balda

1. Se elige la ubicación destino, que queda fija.
2. Se elige el tipo, que se puede cambiar en cualquier momento.
3. El formulario es compacto: ISBN (con autocompletado), título, creador y los datos básicos.
4. **Intro = Guardar y siguiente.** Se muestra la lista de lo ya dado de alta en esta sesión.

### 5.6 Etiquetas e informes

- **Etiquetas**: se eligen una o varias ubicaciones y se genera un PDF A4 con una etiqueta por ubicación que incluye:
  - código en grande,
  - ruta completa,
  - contenido resumido (primeros N títulos + "y X más"),
  - QR con el código.
- **Informes PDF**: inventario por ubicación, elementos prestados, resultado de la búsqueda actual.

### 5.7 Copias de seguridad

- Al cerrar se hace una copia en `datos\copias\` con la API de copia en caliente de SQLite, que garantiza una copia coherente. Se conservan las **últimas 10** (configurable).
- **Copia manual**: ZIP con la base de datos y las portadas hacia la carpeta o USB que se elija.
- **Restaurar**: desde una copia, con confirmación previa y una copia del estado actual antes de sobrescribir.

---

## 6. Plan por fases

Cada fase termina con un **ZIP portable probado** en Windows.

| Fase | Contenido | Resultado verificable |
|---|---|---|
| **0. Validación técnica** | Entorno, esqueleto PySide6 + SQLite FTS5, empaquetado `onedir`, prueba en un Windows sin Python y con Windows Defender activo. Prueba de cobertura de ISBN con 10–20 ISBN reales tuyos | Un "hola mundo" empaquetado que arranca, crea la BD y busca con FTS5. Informe de cobertura de ISBN |
| **1. Núcleo** | Esquema y migraciones, editor de ubicaciones, tipos predefinidos, ficha de elemento, lista y búsqueda básica | Se puede configurar la casa, dar de alta, editar y buscar |
| **2. Productividad** | Filtros completos, alta masiva, mover en lote, editor de tipos y campos personalizados | Catalogar una balda entera de forma cómoda |
| **3. Enriquecimiento** | Portadas, autocompletado por ISBN, préstamos básicos | Fichas completas con imagen |
| **4. Salidas y seguridad** | Etiquetas QR, informes PDF, copias automáticas, manuales y restauración | Imprimir etiquetas; recuperar datos tras un error |
| **5. Cierre** | Manual de usuario, manual de mantenimiento, pruebas finales y ajustes | Versión 1.0 |

---

## 7. Riesgos y cómo se mitigan

| Riesgo | Mitigación |
|---|---|
| El antivirus marca el `.exe` como sospechoso (habitual en ejecutables generados con PyInstaller) | `onedir` en lugar de `onefile`. Prueba con Defender en la Fase 0. Si ocurre, se puede notificar el falso positivo a Microsoft o valorar la firma de código, que tiene coste |
| Poca cobertura de ISBN españoles en Open Library | Se mide en la Fase 0 con ISBN reales. Google Books como segunda fuente (requiere clave propia). Siempre queda la entrada manual |
| Carpeta portable sin permiso de escritura | Comprobación al arrancar y aviso claro |
| Pérdida de datos | Copias automáticas y API de copia de SQLite; confirmaciones al borrar; nunca se borran elementos al borrar una ubicación |
| Mantenimiento con conocimientos básicos | Pocas dependencias, código en español con comentarios, pruebas automáticas, `build.ps1` de un solo paso y manual de mantenimiento paso a paso |
| Cambios de esquema en versiones futuras | Tabla de versión y migraciones automáticas al abrir, con copia previa |

---

## 8. Puntos pendientes de confirmar

1. **Campos por tipo** (apartado 4.3): revisar, añadir o quitar.
2. **Tipos de ubicación iniciales**: se propone Casa, Planta, Habitación, Armario, Estantería, Balda, Caja, Cajón, Archivador y Otro. Plantas iniciales: Sótano, Planta baja, Planta alta y Buhardilla.
3. **Número de copias automáticas** a conservar: se propone 10.
4. **Idioma de la interfaz**: se asume solo español.
5. **Nombre del programa**: se asume "Bibliotecario Virtual".
6. **Formato de la etiqueta**: tamaño por defecto (se propone 8 por folio) y cuántos títulos mostrar.

---

## 9. Referencias

- Tellico: <https://sugggest.com/software/tellico>
- Data Crow (alternativas): <https://alternativeto.net/software/data-crow>
- Catálogo de software de catalogación para Windows: <https://sourceforge.net/directory/cataloguing/windows/>
- SQLite FTS5 (tokenizador `unicode61`, `remove_diacritics`, índices de prefijo): <https://sqlite.org/fts5.html>
- Dublin Core Metadata Element Set (inspiración de los campos comunes): <https://www.dublincore.org/specifications/dublin-core/dces/>
- PySide6 vs PyQt6, licencias: <https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/>
- Notas de versión de PySide6: <https://doc.qt.io/qtforpython-6/release_notes/pyside6_release_notes.html>
- PyInstaller, problemas comunes y modos de empaquetado: <https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html>
- PyInstaller, arranque con `onedir` y `onefile`: <https://github.com/pyinstaller/pyinstaller/issues/4563>
- Falsos positivos de antivirus con PyInstaller: <https://www.pythonguis.com/faq/problems-with-antivirus-software-and-pyinstaller/>
- Qt for Python y Nuitka (alternativa evaluada): <https://doc.qt.io/qtforpython-6/deployment/deployment-nuitka.html>
- Segno (QR): <https://segno.readthedocs.io/>
- Open Library Books API: <https://openlibrary.org/dev/docs/api/books>
- Open Library, límites de uso: <https://openlibrary.org/developers/api>
- Google Books API: <https://developers.google.com/books/docs/v1/using>
- FTS5 disponible en el `sqlite3` de Python (se verificará en la Fase 0): <https://tech-insider.org/sqlite-python-tutorial-fts5-wal-mode-2026/>
