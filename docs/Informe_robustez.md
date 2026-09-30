# LibriDomus 1.1 — Cuaderno de pruebas de robustez

Fecha: 30/09/2026. Equipo de pruebas: el de desarrollo (Windows 10 Pro, Python 3.12, SQLite 3.49.1, Qt 6.11.2).
Los scripts de prueba están en `tests/robustez/` (no forman parte de la batería rápida).

Gravedad: **ALTA** (pérdida de datos, el programa no arranca o riesgo de seguridad real) ·
**MEDIA** (fallo visible o degradación importante) · **BAJA** (molestia o endurecimiento recomendable) ·
**OK** (comprobado y correcto).

## Anotaciones (en el orden en que se han ido encontrando)

### A1. Inyección SQL — **OK**
Revisadas todas las consultas construidas con f-strings (`elementos.py`, `ubicaciones.py`, `busqueda.py`, `etiquetas.py`, `conexion.py`). Solo se interpolan constantes internas: nombres de columnas, nombres de tabla fijos y marcadores `?`. Los datos del usuario siempre van como parámetros. No hay vía de inyección SQL.

### A2. Posible límite de parámetros de SQLite en listas `IN (…)` — *pendiente de verificar*
Borrar elementos o una ubicación arma `IN (?, ?, …)` con un parámetro por elemento. SQLite admite un máximo de 32 766 parámetros por consulta. Se comprueba en el bloque de estrés.

### A3. Antivirus del equipo: Avast, con inspección HTTPS — **información**
El certificado de pypi.org y el de openlibrary.org, vistos desde este equipo, los firma «Avast Web/Mail Shield Root». Avast intercepta el HTTPS con su propia autoridad instalada en Windows. Consecuencias:
- Explica por qué Windows Defender aparecía detenido en la Fase 0: el antivirus activo es Avast.
- **El `.exe` de LibriDomus se ha ejecutado decenas de veces con Avast activo sin ningún bloqueo ni aviso**: primera evidencia real contra el riesgo de falso positivo, al menos con Avast.
- La aplicación confía en las raíces de Windows (incluida la de Avast), así que su autocompletado por ISBN funciona en este equipo. Herramientas que usan su propio almacén (p. ej. `requests`/`certifi`) fallan aquí; no es un problema de LibriDomus.
- Las pruebas de certificados inválidos (B8) se interpretan con esto en mente: es Avast quien decide qué hacer con un certificado malo.

### A4. Vulnerabilidades conocidas en las librerías de PyPI — **OK**
`pip-audit` (base de datos de avisos de PyPI/OSV) sobre `requirements-dev.txt`: **«No known vulnerabilities found»** para PySide6 6.11.2, segno 1.6.6, PyInstaller 6.22.3 y pytest 9.1.1.

### A5. El Python que va dentro del ejecutable (3.12.10) no tiene los últimos parches de seguridad — **MEDIA**
El paquete lleva Python **3.12.10** (abril de 2025) y OpenSSL 3.0.16. Desde entonces la rama 3.12 ha publicado 3.12.11, .12, .13 y **3.12.14** (12/08/2026), que corrigen, entre otros, CVE-2026-2297, CVE-2026-4224, CVE-2026-3644, CVE-2025-4330 y CVE-2021-4189.
**Pero la rama 3.12 está en «solo seguridad» y ya no publica instaladores para Windows** («binary installers are no longer provided»). Sin compilar Python a mano, no se puede actualizar dentro de la 3.12.
- Exposición real de LibriDomus: baja. No usa `tarfile` ni `webbrowser` ni carga `.pyc` ajenos, y la única red es HTTPS de solo lectura a Open Library.
- **Recomendación:** pasar a **Python 3.13** (rama con correcciones e instaladores hasta 2029-10) o 3.14. PySide6 y PyInstaller ya lo admiten. Es un cambio de entorno de compilación, no de código, que se verifica con las 132 pruebas y la autoprueba.
- Fuentes: [Python 3.12.14](https://www.python.org/downloads/release/python-31214/), [Estado de las versiones de Python](https://devguide.python.org/versions/).

### A6. No hay gestor global de errores ni registro (log) — **MEDIA**
Revisión del código: no hay `sys.excepthook` ni archivo de registro, y la interfaz no captura los errores de SQLite (`OperationalError`: base de datos bloqueada, de solo lectura, disco lleno…). En el `.exe` (sin consola), un error inesperado dentro de una acción **no se ve**: el usuario pulsa un botón, «no pasa nada» y no queda rastro para diagnosticar.
**Recomendación:** un gestor global que muestre «Ha ocurrido un error inesperado; tus datos están a salvo» y lo escriba en `datos\registro.log`, con rotación.

### A7. Se pueden abrir dos LibriDomus a la vez sobre los mismos datos — *pendiente de medir*
No hay bloqueo de instancia única. Se mide su efecto en el bloque de concurrencia.

### A8. Cada alta es algo más lenta cuanto mayor es la colección — *pendiente de medir*
`elementos.guardar` borra las personas y etiquetas huérfanas recorriendo todas las relaciones en cada guardado, y `busqueda.reindexar` hace una consulta por nivel de la ruta de ubicación. Crear 20 000 elementos de golpe costó 42 s; 100 000 lleva más de 7 minutos (crecimiento cuadrático en altas masivas).

---
## Bloque B — Rendimiento con 100.000 elementos y 993 ubicaciones

Script: `tests/robustez/rendimiento_100k.py` y `memoria_y_alta_100k.py`. Base de datos resultante: 61,6 MB. Integridad SQLite al final: correcta.

| Operación | Tiempo | Valoración |
|---|---|---|
| Arrancar y abrir la base de datos | 0,00 s | OK |
| Abrir la ventana principal con toda la colección | 1,6–2,0 s | OK |
| Memoria con la ventana abierta | 129 MB | OK |
| Buscar texto («garc amor») | 0,26 s | OK |
| Buscar con una sola letra («a»: casi todo coincide) | 0,95 s | OK |
| Listar todo sin filtros | 1,66 s | Aceptable |
| Filtrar por una planta (250 ubicaciones) | 0,77 s | OK |
| Ordenar por una columna | 0,55 s | OK |
| Guardar **un** elemento | 21 ms (máx. 28) | OK |
| **Refrescar la ventana tras guardar** | **2,94 s** | **MEDIA** (B3) |
| **Seleccionar todo (Ctrl+A)** | **10,98 s** | **MEDIA** (B2) |
| Renombrar una habitación (≈4.000 reindexados) | 0,98 s | OK |
| **Mover una planta entera (≈25.000)** | **5,2 s** | **BAJA** (B4) |
| **Renombrar la casa** | **20,0 s** | **MEDIA** (B4) |
| Mover 10.000 elementos | 3,8 s | OK |
| Borrar 10.000 elementos | 0,95 s | OK |
| Copia automática al cerrar | 0,34 s | OK |
| Copia manual ZIP | 5,2 s | OK |
| Etiquetas de 993 ubicaciones (125 hojas) | 12,0 s | Aceptable |
| Inventario PDF de una habitación (≈3.600) | 5,2 s | Aceptable |
| **Inventario PDF de toda la casa (≈90.000)** | **109,5 s** | **BAJA** (B5) |
| Comprobación de integridad | 1,4 s | OK |
| **Alta de 100.000 seguidas (herramienta, no interfaz)** | **917 s** | **BAJA** (A8) |
| **`reindexar_todo`** | **994 s** | **BAJA** (B6) |

### B1. Conclusión de rendimiento — **OK para una colección doméstica**
Hasta unos 20.000 elementos todo es inmediato (medido en la Fase 5). Con 100.000 la aplicación sigue siendo usable: búsquedas por debajo de 1 s, memoria moderada y base de datos íntegra. Los puntos lentos son operaciones masivas poco frecuentes.

### B2. Seleccionar todo con 100.000 filas congela la ventana 11 s — **MEDIA**
Cada cambio de selección recalcula en Python la lista de elementos seleccionados recorriendo todas las filas (`ids_seleccionados`) y actualiza el panel de detalle.
**Recomendación:** calcular la lista con un pequeño retardo tras el último cambio y, en el panel, mostrar solo el número de elementos cuando hay muchos.

### B3. Tras cada guardado se recarga todo (2,9 s con 90.000 elementos) — **MEDIA con colecciones enormes**
`refrescar_todo` vuelve a construir el árbol y toda la lista después de cada alta o edición. Con 20.000 elementos son unos 0,5 s; con 90.000, casi 3 s por guardado.
**Recomendación:** actualizar solo la fila afectada y los contadores del árbol.

### B4. Renombrar la casa reindexa los 100.000 elementos sin necesidad — **MEDIA** (fácil de corregir)
La ruta que se indexa para buscar **no incluye** el nombre de la casa, pero `ubicaciones.actualizar` reindexa todo lo que cuelga de la ubicación renombrada: 20 s de ventana congelada para nada.
Mover una planta entera sí necesita reindexar (≈25.000 en 5 s), pero también congela la ventana sin avisar.
**Recomendación:** no reindexar cuando cambia solo la descripción o el código, ni cuando se renombra la raíz. Mostrar un indicador de progreso en las operaciones largas.

### B5. Inventario PDF de toda la casa: 110 s sin indicador de progreso — **BAJA**
Funciona (el PDF sale correcto), pero la ventana queda congelada casi 2 minutos. Con colecciones normales (≈3.600 por habitación) son 5 s.
**Recomendación:** hacerlo en segundo plano con barra de progreso.

### B6. `reindexar_todo` no usa una transacción — **BAJA**
Tarda 994 s frente a 20 s de la misma cantidad dentro de una transacción: cada una de las 200.000 escrituras se confirma en disco por separado. **No la usa la interfaz** (es una herramienta de mantenimiento), pero conviene envolverla en `transaccion()`.

### A8 (medido). Coste de las altas según el tamaño — **BAJA**
Un alta suelta con 100.000 elementos: 21 ms, imperceptible. Solo las cargas masivas por programa crecen de forma cuadrática (100.000 seguidas = 15 min), porque cada alta limpia las personas y etiquetas huérfanas recorriendo todas las relaciones.
**Recomendación:** limpiar solo las personas y etiquetas que el elemento acaba de dejar de usar. Importante si algún día se añade una importación desde Excel.

---
## Bloque C — Estrés, resistencia y entradas extremas

Scripts: `tests/robustez/estres_seguridad.py` y `concurrencia_cortes.py`.

### C1. Cortes bruscos (proceso matado a mitad de escritura, 15 veces) — **OK**
15 de 15 sin daños: `integrity_check` correcto, índice de búsqueda idéntico a los elementos (0 sin indexar) y comprobación interna de FTS5 correcta. Los totales tras cada corte son siempre múltiplos de 50: el lote a medio escribir se deshace entero. No quedan diarios huérfanos. **La base de datos resiste cortes de luz o cierres forzados.**

### C2. Dos o más instancias a la vez sobre los mismos datos — **MEDIA**
Seis procesos durante 25 s: 2 escribiendo, 1 moviendo, 2 buscando y 1 haciendo copias. Resultado:
- **Integridad perfecta** y 2.560 elementos, todos indexados.
- Pero hubo **5 errores «database is locked»** (2 al guardar y 3 al mover). Con dos LibriDomus abiertos (p. ej. doble clic dos veces), un guardado puede fallar de vez en cuando y, por A6, **sin avisar**.
- Con una sola instancia no ocurre.

**Recomendación:** impedir una segunda instancia sobre la misma carpeta de datos (archivo de bloqueo) y capturar «database is locked» con reintento y mensaje.

### C3. Fuzzing del buscador: 20.000 textos aleatorios — **OK**
Mezclas de unicode, comillas, `*`, `-`, `^`, `:`, paréntesis, `NOT/AND/OR/NEAR`, caracteres de ancho cero, nulos, emoji, chino y combinantes: **0 errores** en 14,4 s. Un texto pegado de 100.000 caracteres se busca en 0,17 s.

### C4. Textos extremos — **OK**
Emoji compuestos, árabe/hebreo con marcas de dirección, caracteres invisibles, acentos combinantes, carácter nulo, notas de 1 MB y títulos de 100.000 caracteres: se guardan y se leen intactos. «García» escrito con acento combinante se encuentra buscando «garcia». Un elemento con 500 personas y 500 etiquetas se guarda en 0,02 s y se encuentra por la última persona.

### C5. Cadenas con «sustitutos» UTF-16 sueltos — **BAJA**
`elementos.guardar` lanza `UnicodeEncodeError` sin controlar. Desde la interfaz no debería poder ocurrir (Qt no entrega ese tipo de texto), pero la capa de datos no se protege.

### C6. Árboles extremos — **OK con matices (BAJA)**
- 200 niveles de profundidad: todo funciona, pero **el código generado mide 892 caracteres** (`PB-C0-C1-C2-…`), inservible en una etiqueta. Convendría limitar su longitud.
- 5.000 cajas con el mismo nombre en la misma balda: códigos únicos correctos, árbol cargado en 0,25 s, pero crearlas costó 52 s: la búsqueda de un código libre crece con cada repetición. Caso poco realista.

### C7. Validación de fechas, año y valoración — **OK**
5.000 fechas aleatorias sin excepciones inesperadas; los valores fuera de rango se rechazan con un mensaje.

### C8. Límite de parámetros de SQLite (confirma A2) — **MEDIA**
**Seleccionar más de 32.766 elementos y pulsar Borrar falla** con «too many SQL variables». Por A6, sin mensaje: no se borra nada ni se pierde nada, pero el usuario no sabe por qué. Lo mismo al borrar una ubicación con más de 32.766 sububicaciones (irreal).
**Recomendación:** procesar las listas en tandas de 900.

### C9. Arranque con la base de datos dañada — **ALTA**
- Archivo con bytes aleatorios: `sqlite3.DatabaseError: file is not a database`.
- Archivo truncado a la mitad (p. ej. una copia a un USB interrumpida): `database disk image is malformed`.

En ambos casos `conexion.abrir` no convierte el error en `ErrorBaseDatos`, que es lo único que captura `aplicacion.py`. En el `.exe`, según la documentación de PyInstaller, aparece el cuadro técnico **«Unhandled exception in script»** con la traza en inglés **y el programa no abre**. Los datos se pueden recuperar (están las copias automáticas), pero el usuario no recibe ninguna pista de cómo hacerlo.
**Recomendación:** comprobar la integridad al arrancar y, si falla, ofrecer restaurar la última copia automática válida.
Fuente: [PyInstaller — excepciones en modo ventana](https://pyinstaller.org/en/stable/man/pyinstaller.html), [PR #5890](https://github.com/pyinstaller/pyinstaller/pull/5890).

### C10. Base de datos de solo lectura (USB protegido, permisos, copia desde un CD) — **MEDIA**
La aplicación abre sin avisar y, al guardar, falla con `attempt to write a readonly database`, que la ficha no captura: **se pulsa Guardar y no pasa nada**. La comprobación del arranque mira si se puede escribir en la *carpeta*, no en el *archivo*.

### C11. Preferencias (`config.json`) con valores inválidos — **MEDIA**
Un `config.json` con JSON roto ya se ignoraba bien. Pero con JSON válido y tipos o valores absurdos:
- `"escala": "grande"` → `ValueError`: **el programa no arranca**.
- `"escala": 50` → se acepta: **interfaz 50 veces más grande e inutilizable**, y desde ella no se puede ni llegar a Preferencias.
- `"columnas_ocultas": "x"` → `TypeError` al abrir la ventana.

Solo pasa si alguien edita el archivo a mano, pero bloquea el programa. **Recomendación:** validar tipos y rangos al cargar (escala entre 0,9 y 1,5, etc.).

---
## Bloque D — Seguridad

### D1. Inyección SQL — **OK** (ver A1)

### D2. Inyección en la búsqueda FTS5 — **OK**
Cada palabra se aísla entre comillas y solo pasan caracteres de palabra; ningún operador de FTS5 escrito por el usuario llega sin escapar (confirmado con el fuzzing de C3).

### D3. HTML en los datos del usuario — **BAJA**
En el panel de detalle, el **título, el subtítulo, las etiquetas y las notas se interpretan como HTML** (las personas sí se escapan bien). Un título `<h1>…</h1>` sale gigante y una nota `<img src='file:///…'>` muestra una imagen local.
- Sin riesgo de ejecución ni de fuga: el texto enriquecido de Qt no ejecuta scripts ni descarga de Internet.
- Sí puede desfigurar la ficha o esconder texto si un título contiene `<`.
- Los cuadros de confirmación (p. ej. «¿Borrar «…»?») probablemente se comportan igual, porque `QMessageBox` también interpreta HTML automáticamente.

**Recomendación:** `setTextFormat(Qt.PlainText)` en las etiquetas con datos del usuario, o escaparlos.

### D4. Certificados TLS — **OK**
`descargar()` rechaza certificados caducados, autofirmados y de otro dominio (badssl.com). En este equipo, además, Avast inspecciona el tráfico (A3).

### D5. Redirecciones de HTTPS a HTTP — **BAJA**
`urllib` sigue redirecciones a `http://` (código de CPython, `urllib/request.py` línea 703). Si Open Library o un intermediario redirigiera a HTTP, la consulta viajaría sin cifrar. Solo se envía un ISBN y se reciben datos públicos, así que el impacto es mínimo. **Recomendación:** rechazar redirecciones que no sean `https`.

### D6. Descargas sin límite de tamaño — **BAJA**
`descargar()` lee la respuesta entera en memoria. Un servidor comprometido o interceptado podría enviar gigas y agotar la memoria. **Recomendación:** leer como máximo unos pocos MB.

### D7. Respuestas malformadas de Open Library — **BAJA**
5 de 9 respuestas con tipos inesperados (autores que no son lista, título como objeto, `works` vacío, raíz que no es un objeto…) provocan `AttributeError`/`KeyError`. **No cierran el programa**: la interfaz muestra «Error inesperado al consultar el ISBN». Pero lo correcto sería tratarlas como «datos no válidos».

### D8. Imagen «bomba» de 30.000 × 30.000 píxeles — **OK**
Un PNG de 107 KB que ocuparía ~900 MB descomprimido se rechaza al instante gracias al límite de memoria de imágenes de Qt.

### D9. ZIP con rutas `../` al restaurar (zip slip) — **OK**
`zipfile` de Python neutraliza las rutas con `..` y las absolutas: ningún archivo sale de la carpeta temporal.

### D10. ZIP «bomba» (1 GB de ceros en 1 MB) — **BAJA**
Se rechaza porque no es una base de datos válida, pero **antes se descomprime entera** (1 GB en la carpeta temporal, 3,8 s). Con una bomba mayor podría llenar el disco. **Recomendación:** comprobar el tamaño declarado en el ZIP antes de extraer.

### D11. Restaurar una copia con esquema falso — **MEDIA**
Una base de datos con tablas `elemento`, `ubicacion` y `tipo_elemento` vacías de columnas pasa la validación, se restaura y **después el programa falla** (`no such table: tipo_ubicacion`). La copia previa (`antes_de_restaurar_…`) permite volver atrás, pero hay que saberlo. **Recomendación:** validar el esquema completo (tablas y columnas) y probar a abrirla antes de sustituir.

### D12. Copia ajena con un disparador (trigger) oculto — **MEDIA** (solo si se restaura una copia de otra persona)
Una copia manipulada puede llevar un `TRIGGER` que se ejecuta con las operaciones normales. En la prueba, **al añadir un elemento se borraron los otros 488**. El daño queda dentro de la base de datos (SQLite no puede tocar otros archivos ni ejecutar programas, y la carga de extensiones está desactivada), y la copia previa permite recuperarlo.
**Recomendación:** al restaurar, eliminar todo disparador y vista que no forme parte del esquema de LibriDomus, o rechazar la copia si los tiene.

### D13. Datos personales y secretos en claro — **BAJA / información**
- La base de datos no está cifrada: quién aparece en las fotos, a quién se ha prestado qué, notas… Es lo normal en una aplicación doméstica, pero conviene saberlo si se comparte el USB o una copia.
- La **clave de Google Books**, si se configura, se guarda en texto plano en `config.json` **y viaja dentro de la copia manual en ZIP**. **Recomendación:** excluirla de la copia o guardarla con la protección de datos de Windows (DPAPI).

### D14. Otros puntos revisados — **OK / información**
- La carga de extensiones de SQLite está desactivada por defecto en Python: una base de datos ajena no puede cargar código.
- El ejecutable no está firmado: SmartScreen puede avisar la primera vez (ya documentado en el manual).
- Los archivos de estilo temporales (`%TEMP%\libridomus_estilo`) son solo imágenes de flechas; manipularlos solo afectaría al aspecto.
- El `User-Agent` de las consultas no incluye datos personales.

---
## Resumen y prioridades

**Lo sólido:**
- Integridad ante cortes bruscos (15/15).
- Sin inyección SQL ni FTS; buscador inmune a 20.000 entradas aleatorias.
- Certificados, imágenes bomba y zip slip bien resueltos.
- Rendimiento holgado para una colección doméstica, y usable con 100.000 elementos.
- Ninguna vulnerabilidad conocida en las librerías de PyPI.

**Qué corregiría, por orden:**
1. **C9 (ALTA)** — Arranque con base de datos dañada: mensaje claro y ofrecer restaurar la última copia buena.
2. **A6 (MEDIA)** — Gestor global de errores y archivo de registro. Resuelve el «no pasa nada» de C2, C8 y C10.
3. **C11 (MEDIA)** — Validar `config.json` (tipos y rangos).
4. **C2 / A7 (MEDIA)** — Instancia única y reintento ante «database is locked».
5. **D11 + D12 (MEDIA)** — Validar el esquema completo al restaurar y eliminar disparadores y vistas ajenos.
6. **C8 (MEDIA)** — Operaciones en tandas para selecciones de más de 32.766 elementos.
7. **B2, B3, B4 (MEDIA)** — Rendimiento con colecciones muy grandes: selección, refresco tras guardar, renombrar la raíz.
8. **A5 (MEDIA)** — Compilar con Python 3.13 para llevar los parches de seguridad actuales.
9. **Resto (BAJA)** — D3, D5, D6, D7, D10, D13, C5, C6, B5, B6, A8.

**Sin probar** (fuera del alcance de este equipo): disco lleno, otro equipo físico sin Python, Windows Defender y otros antivirus distintos de Avast, pantallas de alta densidad (4K con escalado de Windows).

---
## Correcciones aplicadas en la versión 1.2.0

Cada corrección tiene su prueba de regresión en `tests/test_correcciones_robustez.py` (46 pruebas; 178 en total). Todos los scripts de `tests/robustez/` se han vuelto a ejecutar con el código corregido.

| Hallazgo | Estado | Cómo se ha resuelto | Resultado medido |
|---|---|---|---|
| **C9** Base de datos dañada al arrancar (ALTA) | ✅ | `conexion.abrir` traduce cualquier error de SQLite y comprueba la integridad (`quick_check`) al arrancar. Si está dañada, se ofrece restaurar la última copia automática **válida** o empezar de cero. El archivo dañado se aparta como `biblioteca_danada_…db`, nunca se borra | Archivo aleatorio y truncado: mensaje en castellano y recuperación guiada |
| **A6** Sin gestor de errores ni registro | ✅ | Gestor global (`sys.excepthook` y `threading.excepthook`) → `datos\registro.log` (rotativo, 512 KB × 4) y un mensaje comprensible. Mensajes específicos para «bloqueada», «solo lectura», «disco lleno» y «dañada» | Un error provocado dentro de una acción se explica y queda en el registro con su traza |
| **C2 / A7** Dos instancias a la vez | ✅ | Instancia única por carpeta de datos (`libridomus.lock`), espera de 15 s ante bloqueos y transacciones `BEGIN IMMEDIATE` | 6 procesos durante 25 s: de 5 errores a **0** |
| **C10** Base de datos de solo lectura | ✅ | Al arrancar se comprueba con una escritura real que se deshace y se avisa | Mensaje claro al abrir |
| **C8** Más de 32.766 elementos seleccionados | ✅ | Operaciones por tandas de 500 y subconsultas recursivas para los subárboles | Borrar 40.000 elementos y una ubicación con 40.000 cajas: correcto |
| **C11** `config.json` manipulado | ✅ | Validación de tipo y rango de cada ajuste; lo inválido vuelve al valor por defecto. Guardado atómico | «grande», 50, 7, null…: arranca con valores seguros |
| **D11** Copia con esquema falso | ✅ | Se exige el esquema exacto de su versión (construido desde las migraciones) y se prueba a abrirla sobre un duplicado antes de sustituir nada | Rechazada con explicación |
| **D12** Copia con disparador o vista oculta | ✅ | Se rechazan disparadores, vistas y tablas desconocidas | Rechazada antes de tocar los datos |
| **D10** ZIP «bomba» | ✅ | Solo se extraen `biblioteca.db`, `config.json` y `portadas/*.jpg`; se comprueban la relación de compresión, el tamaño total y el espacio libre **antes** de extraer | Rechazada en 0,0 s sin descomprimir |
| **D13** Clave de Google en la copia ZIP | ✅ | La copia manual ya no incluye la clave | — |
| **B2** Ctrl+A con 90.000 filas | ✅ (mejorado) | Lista de seleccionados leída por rangos; `flags()` precalculado; sin intermediario de ordenación | 11 s → **2,8 s** (el resto ocurre dentro de Qt) |
| **B3** Refresco tras guardar | ✅ | Solo se actualizan las filas afectadas y los contadores; recargar el árbol ya no recarga la lista entera | 2,94 s → **0,32 s** |
| **B4** Renombrar la casa / mover plantas | ✅ | Solo se reindexa si cambia la ruta: nada al reordenar, cambiar el código o la descripción, ni al renombrar la raíz. Cursor de espera en las operaciones largas | 20 s → **0,01 s** |
| **B5** Inventario PDF enorme | ✅ | Maquetado por partes de 2.000 filas; progreso página a página en la barra de estado; cursor de espera | Pico de memoria **1.031 MB → 144 MB**; 112 s → 94 s |
| **B6** `reindexar_todo` sin transacción | ✅ | Dentro de una transacción y con rutas precalculadas | 994 s → **16 s** |
| **A8** Altas cada vez más lentas | ✅ | Solo se limpian las personas y etiquetas que el elemento deja de usar | Un alta: 21 → **7 ms**; 100.000 seguidas: 917 → **22 s** |
| **A5** Python 3.12.10 sin parches | ✅ | Compilado con **Python 3.13.15** (instalador oficial, huella SHA-256 y firma de la PSF verificadas), que incluye **OpenSSL 3.0.21** y **SQLite 3.50.4** | Autoprueba del `.exe`: «Python incluido: 3.13.15» |
| **D3** HTML en los datos | ✅ | Texto plano en todas las etiquetas y cuadros con datos del usuario | El título `<h1>…` se ve literal |
| **D5** Redirección a HTTP | ✅ | Solo HTTPS, también en redirecciones | Rechazada con mensaje |
| **D6** Descargas sin límite | ✅ | Máximo 5 MB por respuesta | — |
| **D7** Respuestas malformadas | ✅ | Lectura defensiva de cada campo; solo se aceptan claves de autor y obra con el formato de Open Library | 11 respuestas malformadas: ninguna provoca un error del programa |
| **C5** Sustitutos UTF-16 sueltos | ✅ | Se sanean al guardar (se sustituyen por «?») | — |
| **C6** Códigos de ubicación enormes | ✅ | Máximo unos 20 caracteres (se conserva la planta y la abreviatura); búsqueda de código libre con una sola consulta | 200 niveles: 892 → **12 caracteres**; 5.000 duplicados: 52 → 17 s |

**Encontrado durante las correcciones:**
- «unable to open database file» (carpeta inexistente o sin permisos) se habría tratado como «base de datos dañada» y habría lanzado la recuperación sin motivo. Ahora tiene su propio mensaje.
- Recargar el árbol de ubicaciones emitía «ubicación cambiada» aunque la selección no cambiara, así que cada guardado recargaba la lista **dos veces**. Corregido.

**Sigue sin probarse** en este equipo: disco lleno real, otro PC sin Python, antivirus distintos de Avast y pantallas 4K con escalado.
