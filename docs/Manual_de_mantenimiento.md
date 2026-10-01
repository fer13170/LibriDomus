# LibriDomus — Manual de mantenimiento

Guía paso a paso para quien tenga que modificar el programa, pensada para un nivel **básico** de Python. Si solo quieres usarlo, lee el *Manual de usuario*.

---

## 1. Preparar el ordenador (una sola vez)

1. Instala **Python 3.13** (la última 3.13.x) desde <https://www.python.org/downloads/windows/>. No hace falta añadirlo al PATH: se usa con `py -3.13`.
   *Por qué 3.13 y no 3.12:* la rama 3.12 ya solo recibe parches de seguridad en código fuente, sin instaladores para Windows, así que el Python que va dentro del ejecutable se quedaría sin actualizar.
2. Instala **Git** desde <https://git-scm.com/download/win> (opcional, pero muy recomendable para no perder cambios).
3. Instala **Inno Setup 6** (para crear el instalador; si no lo instalas, `build.ps1` solo genera el ZIP). Desde PowerShell, sin permisos de administrador:

```powershell
winget install --id JRSoftware.InnoSetup --exact --source winget --scope user
```

   Queda en `%LOCALAPPDATA%\Programs\Inno Setup 6`. Web oficial: <https://jrsoftware.org/isinfo.php>.
4. Abre **PowerShell** en la carpeta del proyecto (en el Explorador: *Archivo › Abrir Windows PowerShell*) y ejecuta:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Esto crea un entorno aislado (`.venv`) con las versiones exactas de las librerías:

| Librería | Versión | Para qué |
|---|---|---|
| PySide6 | 6.11.2 | Interfaz gráfica (Qt), PDF e imágenes |
| segno | 1.6.6 | Códigos QR |
| openpyxl | 3.1.5 | Leer hojas de Excel (.xlsx) al importar y crear la plantilla |
| PyInstaller | 6.22.3 | Crear el ejecutable (solo para empaquetar) |
| pytest | 9.1.1 | Pruebas automáticas (solo para desarrollar) |

Todo lo demás (SQLite, acceso a Internet, ZIP) forma parte de Python.

---

## 2. Tareas habituales

| Quiero… | Comando (en PowerShell, desde la carpeta del proyecto) |
|---|---|
| Abrir el programa sin empaquetar | `.venv\Scripts\python LibriDomus.py` |
| Ejecutar las pruebas automáticas | `.venv\Scripts\python -m pytest -q` |
| Generar el ejecutable, el ZIP y el instalador | `.\build\build.ps1` |
| Comprobar un ejecutable ya generado | `build\salida\LibriDomus\LibriDomus.exe --autoprueba` (el resultado queda en `datos\autoprueba.txt`) |
| Regenerar los iconos de la aplicación desde `res\LibriDomus-icono.svg` | `.venv\Scripts\python build\generar_icono.py` |
| Comprobar que el paquete no depende de nada del equipo | `.venv\Scripts\python build\verificar_dependencias.py build\salida\LibriDomus` |

Sin empaquetar, el programa guarda sus datos en la carpeta `datos` del proyecto; Git la ignora. Para probar con otra carpeta:

```powershell
$env:LIBRIDOMUS_DATOS = "C:\ruta\a\otra\carpeta"
```

### Qué hace `build.ps1`

1. Ejecuta **todas las pruebas**. Si alguna falla, se detiene.
2. Crea el ejecutable con PyInstaller en modo **carpeta** (`onedir`). PyInstaller copia dentro Python, Qt, las librerías de Visual C++ (`vcruntime140*.dll`, `msvcp140*.dll`), OpenSSL y SQLite: **el equipo de destino no necesita tener Python ni nada instalado**.
3. **Verifica las dependencias** (`build\verificar_dependencias.py`). Lee qué DLL importa cada binario del paquete y exige que esté dentro o que sea propia de Windows. El runtime de Visual C++ y el de Python **tienen** que ir dentro aunque este equipo los tenga. También comprueba los complementos de Qt imprescindibles (ventanas, JPEG y traducción al español). Si falta algo, se detiene.
4. Ejecuta la **autoprueba** del `.exe` con un PATH mínimo de Windows, sin ninguna ruta de Python. Comprueba SQLite con FTS5, la base de datos, Qt, el tema y los iconos SVG, las ventanas, JPEG, SSL, QR y PDF. Si falla, se detiene.
5. Genera **«Manual de usuario.pdf»** a partir de `docs\Manual_de_usuario.md`.
6. Comprime todo en `build\salida\LibriDomus-X.Y.Z.zip`.
7. Si Inno Setup 6 está instalado, crea **`build\salida\LibriDomus-X.Y.Z-instalador.exe`** con `build\instalador.iss`. El instalador:
   - instala **solo para el usuario** en `%LOCALAPPDATA%\Programs\LibriDomus`, **sin pedir administrador**. Por eso la carpeta `datos` junto al programa se puede escribir y el código no necesita saber si está instalado o es portable;
   - crea accesos en el menú Inicio (programa y manual) y, si se marca, en el escritorio;
   - al **actualizar**, borra la carpeta `_internal` antigua y copia la nueva; **no toca `datos`**;
   - al **desinstalar**, deja `datos` y avisa de dónde queda;
   - si el programa está abierto, pide cerrarlo.

   **No cambies nunca el `AppId`** de `instalador.iss`: Windows lo usa para reconocer que una versión nueva actualiza a la anterior. El `.iss` debe guardarse en UTF-8 **con BOM** (si no, los acentos salen mal).

La versión se cambia en `libridomus\__init__.py` (`VERSION = "..."`).

### Dónde guarda los datos el programa

Siempre en la subcarpeta **`datos`** junto a `LibriDomus.exe`. Con el instalador, está en `%LOCALAPPDATA%\Programs\LibriDomus\datos`. Desde el programa se abre con *Ayuda › Abrir la carpeta de datos*.

| Contenido | Qué es |
|---|---|
| `datos\biblioteca.db` | La colección (SQLite) |
| `datos\portadas\` | Las imágenes de portada |
| `datos\copias\` | Copias automáticas (solo la base de datos; las portadas que use alguna copia no se borran) |
| `datos\config.json` | Preferencias |
| `datos\registro.log` | Registro de errores: es lo primero que hay que pedir si el usuario ve *«Ha ocurrido un error inesperado»* |
| `datos\biblioteca_danada_….db` | Base de datos dañada apartada al recuperar una copia (nunca se borra sola) |

La copia manual (ZIP) incluye base de datos, portadas y preferencias, pero **no** la clave de Google Books.

### Versión portable (ZIP)

Además del instalador se genera `LibriDomus-X.Y.Z.zip`. Se descomprime en una carpeta con permiso de escritura (Documentos, Escritorio o un USB; **no** en `C:\Archivos de programa`) y se abre `LibriDomus.exe`. Para llevarlo a otro equipo se copia la carpeta completa, con `datos`. Para actualizarla, se sustituyen el `.exe` y `_internal` conservando `datos`.

### Opciones que no aparecen en el manual de usuario

- **Clave de Google Books** (*Preferencias › ISBN*): fuente adicional, que se consulta justo después de Open Library. Sin clave propia, Google rechaza las consultas (responde 429). Se consigue gratis en la consola de Google Cloud (API «Books») y es la mejor opción para encontrar **portadas** de libros españoles recientes y libros en inglés que no estén en Open Library.
- **Cobertura medida el 01/10/2026** con 13 ISBN reales (9 españoles): solo Open Library encontraba 4; con los catálogos nacionales se encuentran 9. Los españoles que faltan son muy recientes o estuches (varios libros en una caja).

---

## 3. Cómo está organizado el código

```
LibriDomus.py        ← lanzador (lo usa PyInstaller)
libridomus\
  __init__.py                  ← nombre y VERSION
  main.py                      ← punto de entrada (--autoprueba o interfaz)
  rutas.py                     ← carpeta 'datos' junto al .exe
  texto.py                     ← quitar acentos, abreviar, ordenar
  recursos\                    ← icono.png, logo.png e iconos\ (Lucide, licencia ISC)
  autoprueba.py                ← comprobaciones del ejecutable
  datos\                       ← TODO el acceso a la base de datos
    esquema.py                 ← tablas y MIGRACIONES
    conexion.py                ← abrir, migrar, transacciones, copia en caliente
    semillas.py                ← datos iniciales (plantas, tipos y campos)
    ubicaciones.py             ← árbol de la casa
    tipos.py                   ← tipos de elemento y campos
    elementos.py               ← libros, discos… (alta, cambios, préstamos)
  servicios\                   ← lógica sin ventanas
    busqueda.py                ← índice FTS5 y filtros
    isbn.py                    ← validar ISBN, orden de las fuentes y combinación de datos; Open Library y Google Books
    catalogos.py               ← Agencia Española del ISBN, Biblioteca Nacional de España y BnF
    portadas.py                ← guardar y limpiar imágenes
    etiquetas.py               ← PDF de etiquetas con QR
    informes.py                ← PDF de inventario, prestados, búsquedas y manual
    copias.py                  ← copias de seguridad y restauración
    importar.py                ← leer Excel/CSV, proponer columnas e importar (con informe)
    configuracion.py           ← datos\config.json (incluido el modo sencillo/avanzado)
  interfaz\                    ← ventanas (PySide6)
    aplicacion.py              ← arranque, copia al salir, tamaño de la ventana
    tema.py                    ← PALETAS clara/oscura, escala, fuente, hoja de estilos e iconos
    ventana_principal.py       ← barra, lateral de ubicaciones, lista, panel de detalle, menú Ver
    panel_detalle.py, capa_fluida.py
    ficha_elemento.py, panel_portada.py, autocompletar.py
    alta_masiva.py, editor_ubicaciones.py, editor_tipos.py
    arbol_ubicaciones.py, selector_ubicacion.py, modelo_resultados.py
    dialogo_etiquetas.py, dialogo_copias.py, dialogo_importar.py, preferencias.py, comun.py
tests\                         ← pruebas automáticas (una carpeta de datos temporal por prueba)
build\                         ← build.ps1, instalador.iss, generar_icono.py, generar_manual.py, verificar_dependencias.py
res\                           ← logotipo: LibriDomus-icono.svg (fuente del icono), versión simplificada
                                 para 16-32 px, PNG de 1024 px y el dibujo original en PNG
docs\                          ← diseño, informe de la fase 0, manuales
```

**Regla de oro:** las ventanas (`interfaz`) no escriben SQL. Llaman a funciones de `datos` o `servicios`. Así la lógica se puede probar sin ventanas.

---

## 4. Recetas

### 4.1 Añadir un tipo de elemento o un campo predefinido

Casi nunca hace falta tocar código: se hace desde el programa, en *Catálogo › Tipos de elemento y campos*.

Si quieres que venga de serie en **bases de datos nuevas**, añádelo a `TIPOS_ELEMENTO` en `libridomus\datos\semillas.py`.

> Las semillas solo se aplican al crear una base de datos. Para añadir algo a bases de datos que **ya existen**, hay que hacer una migración (ver 4.2).

### 4.2 Cambiar la estructura de la base de datos (migración)

1. Abre `libridomus\datos\esquema.py`.
2. **No modifiques** `MIGRACION_1` ni ninguna migración que ya exista: esas ya se han aplicado en bases de datos reales.
3. Añade al final una nueva migración y regístrala en la lista:

```python
MIGRACION_2 = """
ALTER TABLE elemento ADD COLUMN precio TEXT NOT NULL DEFAULT '';
"""

MIGRACIONES: list[str] = [MIGRACION_1, MIGRACION_2]
```

4. Al abrir una base de datos antigua, el programa guarda antes una copia (`datos\copias\antes_de_migrar_...db`) y aplica la migración.
5. Añade una prueba en `tests\` que compruebe el cambio y ejecuta `pytest`.

### 4.3 Añadir un campo común nuevo a la ficha

Como ejemplo, un campo «precio», tras la migración anterior:

1. `datos\elementos.py`: añade `precio: str = ""` a la clase `Elemento` y `"precio"` a la lista `_COLUMNAS`.
2. `interfaz\ficha_elemento.py`: crea el control (`self.precio = QLineEdit()`), añádelo al formulario con `general.addRow(...)`, cárgalo en `_cargar` y léelo en `leer`.
3. Si debe poder buscarse, añádelo al texto que indexa `servicios\busqueda.py → reindexar`.
4. Prueba y empaqueta.

### 4.4 Fuentes de datos por ISBN (versión 1.3.1)

`isbn.consultar` pregunta a varias fuentes gratuitas, en un orden que depende del país del ISBN (`orden_fuentes`):

| ISBN | Orden |
|---|---|
| 978-84 y 979-13 (España) | Agencia del ISBN › BNE › Open Library › (Google Books) › BnF |
| 978-2 y 979-10 (países francófonos) | BnF › Open Library › (Google Books) › Agencia › BNE |
| El resto | Open Library › (Google Books) › Agencia › BNE › BnF |

Google Books solo entra si hay clave. Se para en cuanto el libro tiene **título, autor, editorial y año**; si a la primera fuente le falta algo, lo completan las siguientes (`fusionar`, que nunca pisa un dato ya encontrado). Si al final no hay portada, se pide a Open Library por ISBN. Una fuente caída no impide consultar las demás; solo si fallan todas se muestra «no hay conexión». Límite total: 30 s.

| Fuente | Dónde | Formato | Notas |
|---|---|---|---|
| Agencia Española del ISBN | `catalogos.consultar_agencia` | Web con formulario (HTML) | Todos los libros con ISBN español, incluso los recién salidos. Necesita sesión (cookie) y POST. **La página mezcla UTF-8 y Latin-1**: se lee con `_decodificar`. Da autores y traductores (`; tr.`). |
| BNE | `catalogos.consultar_bne` | SRU, MARC21 | `https://catalogo.bne.es/view/sru/34BNE_INST`, índice `alma.isbn`. Los 700 sin función no se toman como autores (suelen ser ilustradores). |
| BnF | `catalogos.consultar_bnf` | SRU, UNIMARC | `https://catalogue.bnf.fr/api/SRU`, índice `bib.isbn`. Función 070 = autor, 730 = traductor. |
| Open Library | `isbn.consultar_open_library` | JSON | La edita cualquiera: un título de menos de 4 letras se contrasta con el de la obra (el ISBN 9781593276034 tenía por título «lol»). |
| Google Books | `isbn.consultar_google_books` | JSON | Solo con clave. |

Si una fuente cambia de formato:

1. Prueba a mano la consulta en el navegador (las direcciones están en `catalogos.py` e `isbn.py`).
2. Ajusta la función de lectura correspondiente (`leer_ficha_agencia`, `leer_marc21`, `leer_unimarc`…).
3. Actualiza las respuestas de ejemplo de `tests\test_fuentes_isbn.py` (y `tests\test_fase3.py` para Open Library).

La Agencia no tiene API: si cambia su web habrá que retocar `leer_ficha_agencia`. Mientras tanto, el resto de fuentes sigue funcionando.


### 4.5 Cambiar colores, tamaños o iconos

- **Colores:** todos están en `PALETAS` de `libridomus\interfaz\tema.py`, uno para el tema claro y otro para el oscuro, con los mismos nombres (`primario`, `acento`, `fondo`…). Cambia el valor y se aplica a toda la aplicación.
- **Tamaños:** en la hoja de estilos (`hoja_de_estilos`) todas las medidas pasan por `px()`, que las multiplica por la escala elegida. Usa también `tema.px()` en código nuevo.
- **Iconos:** son SVG de **Lucide** (<https://lucide.dev>, licencia ISC, incluida en `recursos\iconos\LICENSE-lucide.txt`). Para añadir uno, descárgalo con la versión fijada y guárdalo en `libridomus\recursos\iconos\`:

```powershell
curl.exe -o libridomus\recursos\iconos\NOMBRE.svg https://unpkg.com/lucide-static@1.49.0/icons/NOMBRE.svg
```

  Después úsalo con `tema.icono("NOMBRE")` o `comun.boton("Texto", "NOMBRE")`. La prueba `test_todos_los_iconos_citados_existen` falla si el código cita un icono que no está en la carpeta.
- **Logotipo:** sustituye `res\LibriDomus---Icono.png` (mejor cuadrado y de 512 px o más) y ejecuta `build\generar_icono.py`.


### 4.6 Modo sencillo y modo avanzado (versión 1.3)

El ajuste `modo` de `config.json` vale `"sencillo"` (por defecto) o `"avanzado"`. Se consulta con `configuracion.modo_avanzado()`.

- **Ficha** (`ficha_elemento.py → _aplicar_modo`): la lista `partes` dice qué se oculta en el modo sencillo y cuándo tiene datos. Una parte se ve si el modo es avanzado, si se ha pulsado *Más campos* o **si ya tiene datos**. Al añadir un campo común nuevo a la ficha, decide si es básico (no se toca nada) o avanzado (añádelo a `partes` con su condición de «tiene datos»).
- **Ocultar nunca borra**: los controles ocultos siguen existiendo y `leer()` los guarda igual. No sustituyas `setVisible`/`setRowVisible` por quitar los controles.
- **Ventana principal** (`ventana_principal.py → aplicar_modo`): oculta los filtros avanzados (y **los reinicia** si estaban activos, para que un filtro invisible no esconda resultados), el botón *Informes* de la barra y *Catálogo › Tipos de elemento*. Los menús conservan el resto de funciones.
- **Alta masiva**: en el modo sencillo oculta las filas de etiquetas y conservación.

### 4.7 Importar desde Excel o CSV (versión 1.3)

Todo está en `servicios/importar.py`; la ventana es `interfaz/dialogo_importar.py`.

- **Sinónimos de columnas:** el diccionario `SINONIMOS` relaciona nombres de columna habituales (sin acentos y en minúsculas) con un dato. Para que se reconozca un nombre nuevo, añádelo ahí. Los campos propios de los tipos se reconocen solos por su etiqueta.
- **Nada se pierde:** lo que no encaja (conservación desconocida, campo que el tipo no tiene, ubicación inexistente, fecha mal escrita) va a las **notas** del elemento. Mantén esa regla si añades destinos.
- **Todo o nada:** la importación entera va en una transacción. Las filas con problemas leves se importan y se anotan como avisos; si ocurre un error inesperado no queda nada a medias. El usuario puede **deshacer** la importación desde el resumen (borra los ids creados).
- **Límites:** 50 MB por archivo, 200.000 filas y 10.000 caracteres por celda. Los `.xls` antiguos no se leen (se pide guardarlos como `.xlsx`). Los CSV se leen en UTF-8 o, si falla, en ANSI (cp1252, el de Excel en español); el separador se detecta solo.
- **Rendimiento:** unas 5.000 filas en pocos segundos (prueba `test_importar_rendimiento_5000_filas`).

### 4.8 Reglas de robustez (versión 1.2)

Surgen de las pruebas de `docs/Informe_robustez.md`. Respétalas al tocar el código:

- **Listas de ids en SQL:** SQLite admite como máximo 32.766 parámetros por consulta. Nunca construyas `IN (?, ?, …)` con una lista que pueda crecer: usa `elementos.tandas(lista)` (lotes de 500) o una subconsulta recursiva, como `_SUBARBOL` en `servicios/busqueda.py`.
- **Errores de SQLite:** `conexion.abrir()` convierte cualquier error en `ErrorBaseDatos` (`BaseDatosDanada`, `BaseDatosSoloLectura`) con un mensaje en castellano. Lo que falle después, dentro de una acción, lo recoge el **gestor global** (`interfaz/aplicacion.py → instalar_gestor_errores`): lo anota en `datos\registro.log` y muestra un mensaje comprensible (`servicios/registro.py → mensaje_para_usuario`). Para diagnosticar un problema, pide al usuario ese archivo.
- **Texto del usuario en la interfaz:** siempre como **texto plano** (`setTextFormat(Qt.PlainText)`; los cuadros de `comun.error/aviso/confirmar` ya lo hacen). Solo se usa HTML en textos que construye el programa, escapando los datos con `html.escape`.
- **Preferencias:** cada ajuste nuevo de `config.json` necesita su entrada en `POR_DEFECTO` **y** en `VALIDADORES` (`servicios/configuracion.py`). Un valor inválido nunca debe impedir arrancar.
- **Copias:** al restaurar se exige exactamente el esquema de la versión de la copia. Ese esquema de referencia se construye ejecutando `esquema.MIGRACIONES`, así que una migración nueva queda cubierta sin tocar `copias.py`. Se rechazan disparadores, vistas y tablas desconocidas. Del ZIP solo se extraen `biblioteca.db`, `config.json` y `portadas/*.jpg`, con límites de tamaño y de espacio libre.
- **Red:** `isbn.descargar()` solo admite HTTPS (también en las redirecciones) y como máximo 5 MB por respuesta. Todas las fuentes (también `catalogos.py`) descargan con esa función. Lee las respuestas con `_texto()`, `_lista()` y `_dic()`: nunca des por hecho el tipo de un dato recibido.
- **Instancia única:** `datos\libridomus.lock` (QLockFile). Si el programa se cierra de golpe, el bloqueo se libera solo, porque Qt comprueba si el proceso que lo creó sigue vivo.
- **Arranque:** se ejecuta `PRAGMA quick_check` (≈0,5 s con 100.000 elementos). Si falla, se ofrece restaurar la última copia automática válida. El archivo dañado se aparta como `biblioteca_danada_AAAAMMDD_HHMMSS.db`, nunca se borra.
- **Pruebas de robustez:** `tests\robustez\` contiene scripts largos que no forman parte de `pytest`. Ejecútalos tras cambios importantes:
  - `estres_seguridad.py` (≈3 min),
  - `concurrencia_cortes.py` (≈2 min),
  - `rendimiento_100k.py` y después `memoria_y_alta_100k.py` (varios minutos).

---

## 5. Antes de entregar una versión nueva

1. Sube la `VERSION` en `libridomus\__init__.py`.
2. Ejecuta `.\build\build.ps1`. Debe terminar en *«Listo.»*, con el ZIP y el instalador creados.
3. Abre el `.exe` de `build\salida\LibriDomus\` y comprueba a mano:
   - crear una ubicación,
   - dar de alta un elemento,
   - buscarlo,
   - generar una etiqueta,
   - cambiar entre modo sencillo y avanzado (Alt+1 / Alt+2),
   - importar la plantilla de Excel (*Archivo › Importar desde Excel o CSV…*),
   - instalar con el instalador, abrir el programa y desinstalarlo (los datos deben quedarse).
4. Para actualizar un equipo que ya usa el programa: si se instaló con el instalador, basta con abrir el instalador nuevo. Si usa la versión portable, sustituye el `.exe` y la carpeta `_internal` **conservando la carpeta `datos`**. Al arrancar, la base de datos se migra sola si hace falta.
5. Si usas Git: `git add -A` y `git commit -m "Versión X.Y.Z: …"`.

---

## 6. Problemas conocidos y decisiones

- **Antivirus:** los ejecutables de PyInstaller sin firma digital a veces dan falsos positivos, y los antivirus (Avast, por ejemplo) **analizan en la nube** cualquier programa que ven por primera vez. Como cada versión nueva es un archivo distinto, ese análisis puede repetirse con cada versión. Lo que ya se hace para reducirlo:
  - modo carpeta en lugar de un único `.exe`;
  - sin compresión UPX (`--noupx`);
  - datos de versión en el `.exe` (`build\version_info.py`) y en el instalador (`VersionInfo…` de `instalador.iss`).

  Lo que queda fuera del código: **enviar el archivo como falso positivo** al fabricante del antivirus (Avast y Microsoft tienen formularios web para ello) y, como solución definitiva, **firmar** el `.exe` y el instalador con un certificado de firma de código, que tiene coste anual.
- **Portadas:** borrar un elemento o cambiar su portada no borra la imagen en el momento. La limpieza del arranque (`portadas.limpiar_huerfanas`) la borra solo si no la usa **ni** la base de datos **ni** ninguna copia guardada en `datos\copias`. Si alguna copia no se puede leer, no borra nada.
- **Ordenar sin acentos:** los listados grandes se ordenan en Python con `texto.clave_orden`, no con `COLLATE ES` en SQL, porque la comparación desde SQLite es muy lenta con miles de filas (se midió: 2,4 s frente a 0,3 s con 20 000 elementos).
- **Migración 2 (LibriDomus):** los tipos de ubicación tienen icono y los emojis de los tipos de elemento se cambiaron por nombres de iconos Lucide. Un tipo propio antiguo con emoji se sigue viendo, dibujado como texto.
- **Restaurar:** la copia se escribe primero junto a la base de datos y luego se sustituye de golpe (`os.replace`), para que nunca quede una base de datos a medias.
