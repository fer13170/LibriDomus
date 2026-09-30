# LibriDomus — Manual de mantenimiento

Guía paso a paso para quien tenga que modificar el programa, pensada para un nivel **básico** de Python. Si solo quieres usarlo, lee el *Manual de usuario*.

---

## 1. Preparar el ordenador (una sola vez)

1. Instala **Python 3.12** desde <https://www.python.org/downloads/windows/>. Marca la casilla *«Add python.exe to PATH»*.
2. Instala **Git** desde <https://git-scm.com/download/win> (opcional, pero muy recomendable para no perder cambios).
3. Abre **PowerShell** en la carpeta del proyecto (en el Explorador: *Archivo › Abrir Windows PowerShell*) y ejecuta:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Esto crea un entorno aislado (`.venv`) con las versiones exactas de las librerías:

| Librería | Versión | Para qué |
|---|---|---|
| PySide6 | 6.11.2 | Interfaz gráfica (Qt), PDF e imágenes |
| segno | 1.6.6 | Códigos QR |
| PyInstaller | 6.22.3 | Crear el ejecutable (solo para empaquetar) |
| pytest | 9.1.1 | Pruebas automáticas (solo para desarrollar) |

Todo lo demás (SQLite, acceso a Internet, ZIP) forma parte de Python.

---

## 2. Tareas habituales

| Quiero… | Comando (en PowerShell, desde la carpeta del proyecto) |
|---|---|
| Abrir el programa sin empaquetar | `.venv\Scripts\python LibriDomus.py` |
| Ejecutar las pruebas automáticas | `.venv\Scripts\python -m pytest -q` |
| Generar el ejecutable y el ZIP | `.\build\build.ps1` |
| Comprobar un ejecutable ya generado | `build\salida\LibriDomus\LibriDomus.exe --autoprueba` (el resultado queda en `datos\autoprueba.txt`) |
| Regenerar los iconos de la aplicación desde `res\LibriDomus---Icono.png` | `.venv\Scripts\python build\generar_icono.py` |
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

La versión se cambia en `libridomus\__init__.py` (`VERSION = "..."`).

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
    isbn.py                    ← validar ISBN y consultar Open Library / Google Books
    portadas.py                ← guardar y limpiar imágenes
    etiquetas.py               ← PDF de etiquetas con QR
    informes.py                ← PDF de inventario, prestados, búsquedas y manual
    copias.py                  ← copias de seguridad y restauración
    configuracion.py           ← datos\config.json
  interfaz\                    ← ventanas (PySide6)
    aplicacion.py              ← arranque, copia al salir, tamaño de la ventana
    tema.py                    ← PALETAS clara/oscura, escala, fuente, hoja de estilos e iconos
    ventana_principal.py       ← barra, lateral de ubicaciones, lista, panel de detalle, menú Ver
    panel_detalle.py, capa_fluida.py
    ficha_elemento.py, panel_portada.py, autocompletar.py
    alta_masiva.py, editor_ubicaciones.py, editor_tipos.py
    arbol_ubicaciones.py, selector_ubicacion.py, modelo_resultados.py
    dialogo_etiquetas.py, dialogo_copias.py, preferencias.py, comun.py
tests\                         ← pruebas automáticas (una carpeta de datos temporal por prueba)
build\                         ← build.ps1, generar_icono.py, generar_manual.py, verificar_dependencias.py
res\                           ← logotipo original de LibriDomus
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

### 4.4 Si cambia la API de Open Library

Toda la consulta está en `servicios\isbn.py`. En la Fase 0 se comprobó que el endpoint antiguo `api/books` ya devolvía 404 (ver `docs\Fase0_informe.md`). Si deja de funcionar:

1. Prueba a mano en el navegador: `https://openlibrary.org/isbn/9788483468463.json`.
2. Ajusta `consultar_open_library`.
3. Las pruebas de `tests\test_fase3.py` simulan las respuestas: actualízalas al nuevo formato.


### 4.5 Cambiar colores, tamaños o iconos

- **Colores:** todos están en `PALETAS` de `libridomus\interfaz\tema.py`, uno para el tema claro y otro para el oscuro, con los mismos nombres (`primario`, `acento`, `fondo`…). Cambia el valor y se aplica a toda la aplicación.
- **Tamaños:** en la hoja de estilos (`hoja_de_estilos`) todas las medidas pasan por `px()`, que las multiplica por la escala elegida. Usa también `tema.px()` en código nuevo.
- **Iconos:** son SVG de **Lucide** (<https://lucide.dev>, licencia ISC, incluida en `recursos\iconos\LICENSE-lucide.txt`). Para añadir uno, descárgalo con la versión fijada y guárdalo en `libridomus\recursos\iconos\`:

```powershell
curl.exe -o libridomus\recursos\iconos\NOMBRE.svg https://unpkg.com/lucide-static@1.49.0/icons/NOMBRE.svg
```

  Después úsalo con `tema.icono("NOMBRE")` o `comun.boton("Texto", "NOMBRE")`. La prueba `test_todos_los_iconos_citados_existen` falla si el código cita un icono que no está en la carpeta.
- **Logotipo:** sustituye `res\LibriDomus---Icono.png` (mejor cuadrado y de 512 px o más) y ejecuta `build\generar_icono.py`.

---

## 5. Antes de entregar una versión nueva

1. Sube la `VERSION` en `libridomus\__init__.py`.
2. Ejecuta `.\build\build.ps1`. Debe terminar en *«Listo: …zip»*.
3. Abre el `.exe` de `build\salida\LibriDomus\` y comprueba a mano:
   - crear una ubicación,
   - dar de alta un elemento,
   - buscarlo,
   - generar una etiqueta.
4. Para actualizar un equipo que ya usa el programa: sustituye el `.exe` y la carpeta `_internal` **conservando la carpeta `datos`**. Al arrancar, la base de datos se migra sola si hace falta.
5. Si usas Git: `git add -A` y `git commit -m "Versión X.Y.Z: …"`.

---

## 6. Problemas conocidos y decisiones

- **Antivirus:** los ejecutables de PyInstaller sin firma digital a veces dan falsos positivos. El modo carpeta reduce el riesgo. La solución definitiva es firmar el ejecutable con un certificado de firma de código, que tiene coste.
- **Portadas:** borrar un elemento o cambiar su portada no borra la imagen en el momento. La limpieza del arranque (`portadas.limpiar_huerfanas`) la borra solo si no la usa **ni** la base de datos **ni** ninguna copia guardada en `datos\copias`. Si alguna copia no se puede leer, no borra nada.
- **Ordenar sin acentos:** los listados grandes se ordenan en Python con `texto.clave_orden`, no con `COLLATE ES` en SQL, porque la comparación desde SQLite es muy lenta con miles de filas (se midió: 2,4 s frente a 0,3 s con 20 000 elementos).
- **Migración 2 (LibriDomus):** los tipos de ubicación tienen icono y los emojis de los tipos de elemento se cambiaron por nombres de iconos Lucide. Un tipo propio antiguo con emoji se sigue viendo, dibujado como texto.
- **Restaurar:** la copia se escribe primero junto a la base de datos y luego se sustituye de golpe (`os.replace`), para que nunca quede una base de datos a medias.
