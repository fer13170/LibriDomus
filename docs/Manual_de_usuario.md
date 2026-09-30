# LibriDomus — Manual de usuario

LibriDomus registra **dónde guardas** cada libro, revista, disco, película, videojuego, partitura, álbum de fotos, caja de diapositivas, carpeta o documento de tu casa, y te permite **encontrarlo** en segundos.

Funciona **sin Internet**. Solo usa la conexión, si la hay, para el botón *Autocompletar* por ISBN.

---

## 1. Instalación

1. Descomprime el archivo `LibriDomus-X.Y.Z.zip` en una carpeta **donde puedas escribir**: Documentos, el Escritorio o un USB. **No** lo pongas en `C:\Archivos de programa`.
2. Entra en la carpeta `LibriDomus` y abre **`LibriDomus.exe`**.
3. Si quieres, crea un acceso directo: clic derecho en el `.exe` › *Enviar a* › *Escritorio*.

**No hace falta instalar nada más**: ni Python ni otros programas. Todo lo necesario (incluidas las librerías de Microsoft Visual C++) va dentro de la carpeta.

Todos tus datos se guardan en la subcarpeta **`datos`**, junto al programa:

| Contenido | Qué es |
|---|---|
| `datos\biblioteca.db` | Toda la información |
| `datos\portadas\` | Las imágenes de portada |
| `datos\copias\` | Copias de seguridad automáticas |
| `datos\config.json` | Tus preferencias |

> Para llevarte el programa a otro ordenador, copia la carpeta `LibriDomus` completa.

La primera vez, Windows puede mostrar el aviso *«Windows protegió su PC»*, porque el programa no está firmado digitalmente. Pulsa *Más información* › *Ejecutar de todas formas*.

---

## 2. La ventana principal

La ventana tiene tres zonas:

- **Izquierda: ubicaciones.** La casa, sus plantas, las habitaciones, los muebles… A la derecha de cada nombre aparece cuántos elementos contiene, contando todo lo que hay dentro. Al pulsar una ubicación, la lista central muestra su contenido.
  - Arriba está *Toda la colección*; si hay elementos sin ubicar, al final aparece *Sin ubicación*.
  - Con **clic derecho** en una ubicación puedes añadir un elemento o una sububicación, editarla, **subirla o bajarla**, imprimir su etiqueta o sacar su inventario.
- **Centro: la lista.** Pulsa una cabecera para ordenar por esa columna. Con clic derecho en la cabecera eliges qué columnas ver (se recuerda). Doble clic en un elemento para abrir su ficha.
- **Derecha: el panel de detalle.** Muestra la ficha del elemento seleccionado: portada, personas, dónde está (pulsa la ruta para ir a esa ubicación), sus datos y botones para editar, mover, prestar o borrar. Se muestra u oculta con **F9**.

**Arriba**, la barra con el **buscador**, *Nuevo* (la flecha permite elegir el tipo), *Alta masiva*, *Casa* (editar ubicaciones), *Etiquetas*, *Informes*, *Ir a código*, el panel de detalle y las *Preferencias*.

Cuando la colección está vacía aparece una pantalla de bienvenida con botones para empezar.

### Atajos de teclado

| Tecla | Acción |
|---|---|
| Ctrl+N | Nuevo elemento |
| Ctrl+Mayús+N | Alta masiva |
| F2 | Editar el elemento seleccionado |
| Ctrl+M | Mover los elementos seleccionados |
| Supr | Borrar los elementos seleccionados |
| Ctrl+F | Ir al buscador |
| Ctrl+E | Imprimir etiquetas |
| Ctrl + / Ctrl − / Ctrl+0 | Aumentar, reducir o restablecer el tamaño de la interfaz |
| F9 | Mostrar u ocultar el panel de detalle |
| F1 | Este manual |

---

## 3. Apariencia: tema, tamaño y letra

En **Ver** o en **Preferencias › Apariencia** puedes elegir:

- **Tema**: *Claro*, *Oscuro* o *Según Windows* (sigue el modo claro u oscuro del sistema).
- **Tamaño de la interfaz**: *Pequeño*, *Normal*, *Grande*, *Muy grande* o *Enorme*. Cambia a la vez el tamaño de la letra, los iconos y las filas. También con **Ctrl +** y **Ctrl −**.
- **Tipo de letra** de toda la aplicación.

Los cambios se ven al momento y se recuerdan la próxima vez. También se recuerdan el tamaño y la posición de la ventana, las columnas visibles y si el panel de detalle está abierto.

---

## 4. Primer paso: describir tu casa

Botón **Casa** de la barra (o *Catálogo › Ubicaciones de la casa…*).

La casa ya viene con sus plantas: **Sótano, Planta baja, Planta alta y Buhardilla**. Puedes renombrarlas, borrarlas, añadir otras y **ordenarlas como quieras**.

- **Añadir dentro…**: crea una ubicación dentro de la seleccionada. Por ejemplo, selecciona *Planta baja*, pulsa *Añadir dentro* y escribe *Salón*. El programa propone el tipo más probable (tras una planta, una *Habitación*; tras una habitación, un *Armario*…) y un **código** corto (*PB-SAL*).
- **Añadir al mismo nivel…**: crea una hermana de la seleccionada.
- **Ordenar**: arrastra y suelta en el árbol, o usa *Subir* y *Bajar*. Funciona aquí y también directamente en el árbol de la ventana principal. **El orden se guarda** y se mantiene al volver a abrir el programa. Por ejemplo, puedes poner la Buhardilla arriba del todo.
- **Mover con contenido**: **todo lo que contiene una ubicación viaja con ella**. Si mueves una estantería, sus baldas y sus libros van detrás.
- **Mover a…**: lleva la ubicación dentro de otra sin arrastrar.
- **Borrar…**: si la ubicación contiene elementos, el programa te pide primero **a dónde moverlos**. Nunca se pierde nada sin preguntar.
- **Tipos de ubicación…**: añade tipos propios (Baúl, Vitrina, Maleta…) con su prefijo para los códigos y su icono.

No hay niveles obligatorios. Puedes tener `Planta baja › Salón › Estantería A › Balda 3` y también `Sótano › Caja 7` directamente.

---

## 5. Registrar elementos

### 5.1 Uno a uno: la ficha

Pulsa **Nuevo**, o la flecha junto a él para elegir el tipo. Si tenías una ubicación seleccionada en el árbol, la ficha ya viene con ella.

- **Tipo**: al cambiarlo, el formulario muestra sus campos propios. Por ejemplo, un *Libro* tiene editorial, páginas y encuadernación, y un *Disco* tiene soporte, sello y pistas.
- **Personas**: autores, intérpretes, directores, quién aparece en las fotos… Cada una con su **rol**. Pulsa *Añadir persona* para añadir más.
- **Identificador**: ISBN, EAN o ISSN. Con un ISBN, el botón **Autocompletar** busca en Internet el título, los autores, la editorial, el año, las páginas, el idioma y la portada. **Solo rellena lo que está vacío**: nunca borra lo que ya has escrito.
- **Conservación, valoración y leído/visto/escuchado**.
- **Etiquetas**: palabras libres separadas por comas (*pendiente*, *firmado*, *herencia*…).
- **Portada**: arrastra una imagen al recuadro, usa *Elegir…* o cópiala y pulsa *Pegar*.
- **Periodo, lugar y evento**: para álbumes, diapositivas, carpetas y documentos. Las fechas se escriben como `1985`, `1985-07` o `1985-07-14`.
- **Ubicación**: pulsa *Elegir…* para escogerla en el árbol.
- **Préstamo**: escribe a quién lo has prestado. Si no pones fecha, se usa la de hoy. El botón *Devuelto* lo borra.

*Guardar y nuevo* guarda el elemento y deja la ficha lista para el siguiente, con el mismo tipo y la misma ubicación.

Si el ISBN ya existe en tu colección, el programa te avisa antes de guardar. Puede que tengas dos ejemplares.

### 5.2 Muchos seguidos: el alta masiva

Pulsa **Alta masiva**. Es la forma más rápida de catalogar una balda o una caja entera.

1. Elige **dónde guardar** y el **tipo**. Se mantienen durante toda la sesión.
2. En los libros, discos y películas el cursor empieza en el **ISBN/EAN**. Escríbelo y pulsa **Intro**: si hay Internet, se rellenan título, autor y año, y el cursor pasa al título.
3. Completa lo que falte y pulsa **Intro**: se guarda y el formulario queda limpio para el siguiente.
4. Las **etiquetas** y el **estado de conservación** se mantienen de un alta a otra.
5. A la derecha ves lo registrado en la sesión. *Deshacer el último* lo borra si te has equivocado.

Si hay varias personas, sepáralas con punto y coma: `Cristina Durán; Miguel Á. Giner`.

> **Nota sobre el ISBN:** la fuente principal es Open Library, gratuita y sin registro. En las pruebas con libros españoles encontró aproximadamente **la mitad**; los más recientes o de editoriales pequeñas pueden no estar. Cuando no aparece, se rellena a mano. En *Archivo › Preferencias* puedes añadir una clave propia de Google Books como segunda fuente.

---

## 6. Buscar

Escribe en el buscador; los resultados aparecen mientras escribes.

- **No importan los acentos ni las mayúsculas**: `garcia marquez` encuentra *García Márquez*.
- **Basta con el principio de las palabras**: `sole` encuentra *Soledad*.
- **Deben aparecer todas las palabras**: `saviano gomorra`.
- **Frase exacta** entre comillas: `"cien años"`.
- **Excluir** con un guion delante: `novela -policiaca`.

Se busca en el título, el subtítulo, las personas, las etiquetas, las notas, los campos propios, el lugar o evento, a quién está prestado **y la ruta de la ubicación**. Por ejemplo, `buhardilla` encuentra todo lo que hay en la buhardilla.

La búsqueda se combina con la ubicación seleccionada en el árbol y con los **filtros** que hay sobre la lista: tipo, etiqueta, estado, idioma, *Prestados* y *Pendientes* (sin leer, ver o escuchar). *Quitar filtros* lo deja todo como al principio.

---

## 7. Mover, prestar y borrar

- **Mover**: selecciona uno o varios elementos (Ctrl o Mayús + clic) y **arrástralos a una ubicación del árbol**, o usa *Mover a…*.
- **Prestar**: con uno o varios elementos seleccionados, menú *Elemento › Prestar a…* o clic derecho. Para devolverlos: *Marcar como devuelto*.
- **Borrar**: el programa siempre pide confirmación.

---

## 8. Etiquetas para cajas y baldas

Pulsa **Etiquetas** (menú *Informes*).

1. Marca las ubicaciones que quieres etiquetar. *Marcar con todo lo que contiene* marca la seleccionada y todo lo que cuelga de ella.
2. Pulsa *Generar PDF…* y elige dónde guardarlo. El PDF se abre solo.
3. Imprime en **folio A4 normal** y recorta por la línea discontinua. Caben 8 etiquetas por hoja.

Cada etiqueta lleva:

- el **código** en grande,
- el nombre y la ruta,
- cuántos elementos contiene y los primeros títulos (el número se ajusta en *Preferencias*),
- un **código QR**.

El QR contiene el código de la ubicación (por ejemplo `PB-SAL-EA-B3`). Si lo escaneas con el móvil, verás ese texto. Escríbelo o pégalo en **Ir a código** (arriba a la derecha) y pulsa Intro: el programa salta a esa ubicación y muestra su contenido.

---

## 9. Informes

Menú **Informes**:

- **Inventario de la ubicación seleccionada**: todo lo que contiene, agrupado por mueble, balda o caja. Si no hay ninguna ubicación seleccionada, sale el inventario de toda la casa.
- **Elementos prestados**: a quién y qué.
- **Resultado de la búsqueda actual**: lo que ves en la lista, en el mismo orden.

---

## 10. Tipos de elemento propios

Menú **Catálogo › Tipos de elemento y campos…**

- Crea tipos nuevos (por ejemplo *Juego de mesa*) con sus campos: texto, texto largo, número, fecha, lista de opciones o sí/no.
- Amplía los tipos predefinidos con campos nuevos, cámbialos de orden u ocúltalos.
- **Ocultar o quitar un campo no borra los datos ya guardados**: si vuelves a mostrarlo, siguen ahí.
- Los tipos predefinidos no se pueden borrar. Los propios, solo si no hay elementos de ese tipo.

---

## 11. Copias de seguridad

- **Automáticas**: cada vez que cierras el programa se guarda una copia de la base de datos en `datos\copias`. Se conservan las últimas 10; puedes cambiar el número en *Preferencias*.
- **Manual**: *Archivo › Hacer copia de seguridad…* crea un **ZIP con todo** (datos, portadas y preferencias). **Guárdalo de vez en cuando fuera del ordenador**, por ejemplo en un USB o en la nube.
- **Restaurar**: *Archivo › Restaurar copia de seguridad…* Elige una copia automática o un ZIP. Antes de sustituir nada, el programa guarda una copia del estado actual (*«previa a un cambio»*). Después se reinicia solo.

> Las copias automáticas solo incluyen la base de datos. Las portadas están en `datos\portadas` y el programa **no borra ninguna portada que necesite alguna copia guardada**. Para una copia completa y portátil, usa la copia manual en ZIP.

---

## 12. Preferencias

*Archivo › Preferencias…*

- Activar o desactivar la consulta de ISBN por Internet.
- Clave de Google Books (opcional).
- Copia automática al cerrar y número de copias que se conservan.
- Número de títulos que se listan en cada etiqueta.
- Apariencia: tema, tamaño de la interfaz y tipo de letra (ver apartado 3).

---

## 13. Problemas frecuentes

| Problema | Solución |
|---|---|
| *«No se puede escribir en la carpeta de datos»* | Mueve la carpeta del programa a Documentos, al Escritorio o a un USB. |
| El antivirus bloquea el programa | Es un falso positivo habitual en programas hechos con Python y sin firma digital. Añade la carpeta a las exclusiones del antivirus. |
| El ISBN no se encuentra | Rellena los datos a mano. Open Library no tiene todos los libros. |
| *«Esta versión de SQLite no incluye la búsqueda FTS5»* | No debería ocurrir con el ejecutable oficial. Vuelve a descomprimir el ZIP. |
| He borrado algo por error | *Archivo › Restaurar copia de seguridad…* y elige la copia automática anterior. |
