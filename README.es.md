# Claude Export Viewer (versión 2026.10.26.16)

[English](README.md) | [Français](README.fr.md) | **Español** | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Convierta el historial de conversaciones de Claude.ai en un sitio HTML local que cualquier navegador puede abrir, sin conexión a Internet, y conserve un archivo acumulativo de sus conversaciones, incluidas las que se hayan eliminado después en Claude.ai.

![Captura de pantalla](docs/apercu.png)

Este proyecto se basa en [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) de Judson Neer, ampliamente modificado y completado (véase «Licencia y agradecimientos»).

> Este proyecto es independiente y no está afiliado a Anthropic. Claude es una marca de Anthropic.

> Se diseñó y probó en Linux Ubuntu 26.04, en Python 3.14 y JavaScript. Debería funcionar en Windows. El código se escribió con Claude (modelo Opus 5.5, razonamiento alto). Este README es una traducción automática de la versión francesa.

## Inicio rápido en Linux Ubuntu / Debian

1. Obtenga el historial de conversaciones en claude.ai: **Configuración > Privacidad > Exportar datos**. Recibirá un primer correo informativo y luego un segundo con un enlace para descargar un archivo «manifiesto».

2. Instale las 4 bibliotecas y Pandoc desde un terminal:  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Guarde el programa `claude-export-viewer.zip` en `~/Descargas`.

4. Descomprímalo en su carpeta personal y ejecútelo: los archivos de la exportación se descargan a partir del manifiesto, se importan y luego se abre el índice.  
`cd ~/Descargas && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Descargas -o ~/claude_site`  
(El `rm -rf` solo elimina la versión anterior del programa: sus conversaciones están en `~/claude_site`.)

5. Una sola vez, cree el icono de inicio en el escritorio:  
`python3 claude-export-viewer.py -o ~/claude_site --install-icon`

## Funciones

- **Índice general** de todas sus conversaciones, con:
  - búsqueda en los títulos, con contador de resultados;
  - ordenación de las conversaciones: por fecha de creación, fecha del último intercambio, título, número de mensajes;
  - **categorías** propias, elegidas en un pequeño menú a la derecha de cada conversación, para filtrar a su gusto;
  - la **búsqueda en el contenido** (desde 3 letras): solo quedan las conversaciones que contienen todas las palabras, con el número de pasajes encontrados; una palabra se busca en el texto, un comando como `\alpha` en las fórmulas, un símbolo como `α` o `∞` en ambos; se ignoran mayúsculas y acentos.
- **En cada conversación**:
  - fecha y hora locales, enlace **Abrir en claude.ai** (si todavía existe allí);
  - Markdown con formato (negrita, listas, tablas) y código resaltado (Pygments);
  - marcos de código con el nombre del lenguaje y un botón **Copiar** (copia el código exacto al portapapeles);
  - **fórmulas matemáticas mostradas como en LaTeX** (KaTeX, incluido, sin conexión): `$…$`, `$$…$$`, `\(…\)`, `\[…\]`; al copiar un pasaje se copia la fuente LaTeX de sus fórmulas; una fórmula que no se puede mostrar queda como fuente, con el motivo en una información emergente;
  - artefactos mostrados (código, documentos, HTML/SVG mostrados como código, nunca ejecutados);
  - razonamientos, llamadas a herramientas y resultados en bloques plegables;
  - **varias versiones**: cuando se editó un mensaje o se regeneró una respuesta, la página sigue la versión que lleva al último intercambio; las demás versiones están en marcos plegables «Otra versión», en el punto donde la conversación se bifurcó;
  - **exportación a Markdown, LibreOffice (.odt) y Word (.docx) bajo demanda**: un botón «.md» en cada conversación; el archivo contiene el hilo principal y, en marcos (citas) con etiquetas en cursiva, todas las demás versiones en su punto de bifurcación (o, con la casilla desmarcada, solo el hilo principal); fórmulas como `$…$`, código, artefactos y nombres de los adjuntos incluidos (sin razonamientos ni resultados de herramientas); legible con Typora, Obsidian, Zettlr, convertible con Pandoc;
  - **exportación a PDF** mediante la ventana de impresión del navegador, fórmulas incluidas;
  - **palabras buscadas resaltadas** al abrir desde el índice, con una pequeña barra para ir de un pasaje a otro;
  - **ocultar las respuestas de Claude** para ver solo sus mensajes, uno debajo de otro (flechita tras la fecha de cada mensaje, botón arriba a la derecha para todas);
  - **copiar un mensaje** en Markdown, fórmulas en LaTeX, con el icono junto a la fecha;
  - **navegación con el teclado**: ← y → (4 y 6 del teclado numérico desactivado) para pasar de uno de sus mensajes a otro, 7, 5 y 1 del teclado numérico para el inicio, la mitad y el final de la página, M para ocultar las respuestas, ? para la lista; los mismos botones a la derecha, con un **desplazamiento lento y continuo** de velocidad ajustable (+ y −);
  - **documentos adjuntos**: texto completo (ya sin corte a 3000 caracteres), guardado como archivo y abierto con el programa del ordenador mediante un icono; las instrucciones añadidas automáticamente por claude.ai se muestran una sola vez.
- **Sus archivos recuperados**: las imágenes y archivos que envió, los originales de los documentos adjuntos y los archivos creados por Claude que guardó se buscan por su nombre exacto en las carpetas elegidas en el índice (subcarpetas incluidas), se copian en el sitio y se muestran en la conversación; botones Sí / No para confirmar que es el archivo correcto (y Modificar para cambiar la respuesta); los archivos que aún faltan se buscan en cada inicio.
- **Archivo acumulativo**: las exportaciones sucesivas se añaden sin duplicados, y se conservan las conversaciones eliminadas después en claude.ai.
- **12 idiomas** (páginas, consola, exportaciones), a elegir en el índice.
- **Icono de escritorio** (Linux, Windows) que abre el índice e importa una nueva exportación con un clic.
- Tema claro u oscuro según la configuración del sistema.

## Instalación

Descomprima esta carpeta donde quiera (disco, memoria USB…) e instale las cuatro bibliotecas que necesita.

**Ubuntu / Debian**: véase «Inicio rápido» más arriba.

**Windows** (Python 3.11 o posterior, desde [python.org](https://www.python.org/downloads/) o Microsoft Store), en un terminal (PowerShell o Símbolo del sistema):

```
py -m pip install jinja2 mistune pydantic pygments
```

En Windows, sustituya `python3` por `py` en los comandos de este documento, y las rutas `~/…` por rutas de Windows (`C:\Users\[Usuario]\claude_site`, `E:\claude_site` para una memoria USB…). **La compatibilidad con Windows se escribió a partir de la documentación de Python y de Windows, pero todavía no se ha probado en un equipo con Windows**: sus comentarios son bienvenidos.

## El icono «Archivos de Claude» (la forma más sencilla)

Después de la primera importación (véase más abajo), cree el icono una vez:

```
python3 claude-export-viewer.py -o ~/claude_site --install-icon
```

Aparece en el menú de aplicaciones y en el escritorio (Linux; KDE puede pedir una vez que confíe en el lanzador), o en el menú Inicio y en el escritorio (Windows: accesos directos creados por PowerShell, que ejecutan `pythonw.exe`, así que no se abre ninguna ventana de consola; no probado). Un clic abre el índice en el navegador, servido por un pequeño servidor local (http://127.0.0.1:8000) que se detiene solo 30 minutos después de cerrar la última página (`--idle` para cambiar este plazo). Un segundo clic reutiliza el servidor ya iniciado, salvo si lo inició una versión anterior del programa: entonces se detiene y se sustituye, para que se use realmente la nueva versión. Coloque el programa en una carpeta estable (por ejemplo `~/claude-export-viewer`) antes de crear el icono.

Abierto con el icono, el índice reúne sus ajustes en un marco en la parte superior: los botones **Importar un nuevo manifiesto** y **Gestionar categorías**, y debajo la carpeta de descargas con su botón **Cambiar**. Cada botón abre su panel; un segundo clic (o la cruz) lo cierra. El botón **Importar un nuevo manifiesto**: después de solicitar la exportación en claude.ai y hacer clic en el enlace del correo que indica que sus datos están listos, toma el manifiesto más reciente de su carpeta de descargas, abre los enlaces uno por uno (también se muestran, con enlace, en el registro de la página), importa la exportación y recarga el índice. Cerrar el registro durante una importación no la detiene: otro clic lo vuelve a mostrar.

En el mismo marco, la línea **Carpeta de descargas** indica dónde se busca el manifiesto. Si su navegador guarda los archivos en otro lugar (su ajuste «Guardar archivos en» o «Ubicación»), haga clic en **Cambiar** e indique esa carpeta: se guarda en el archivo y se busca primero, antes que la carpeta del sistema. Dejar el campo vacío vuelve a la carpeta del sistema; si la carpeta elegida desaparece (memoria USB retirada), se usa la carpeta del sistema.

Y en cada conversación, las exportaciones .md, .odt y .docx funcionan con un clic.

**Seguridad**: el servidor solo escucha en su ordenador (127.0.0.1) y no sirve el archivo en bruto. La importación exige un «token secreto» que solo pueden leer las páginas del índice, y se rechazan las peticiones que vienen de otro sitio: una página web abierta en el mismo navegador no puede desencadenarlas.

## Línea de comandos

1. En claude.ai: **Configuración > Privacidad > Exportar datos**.
2. Cuando llegue el correo, haga clic en su enlace: el navegador descarga un pequeño archivo «manifiesto» (la lista de los archivos de la exportación y sus enlaces).
3. Ejecute:

```
python3 claude-export-viewer.py ~/Descargas -o ~/claude_site
```

El programa toma el manifiesto más reciente de la carpeta y luego:

- abre él mismo cada enlace en su navegador (donde tiene la sesión iniciada en claude.ai), **uno por uno**, esperando a que termine cada descarga (un enlace puede dejar de funcionar una vez usado);
- detecta los archivos ya descargados, aunque el navegador los haya renombrado (`conversations-000 (1).zip`), e ignora los de una exportación anterior;
- mueve los archivos a `~/claude_site/archive/exports/<fecha>/`;
- importa la exportación en el archivo y abre el índice.

Por defecto, solo se obtienen los archivos útiles (conversaciones, proyectos, cuenta). Opciones:

- `--all`: obtener los 7 archivos de la exportación (copia de seguridad completa);
- `--browser brave-browser`: elegir el navegador que abre los enlaces;
- `--manual`: no abrir nada; los enlaces se muestran uno por uno en el terminal (Ctrl + clic para abrirlos, o clic derecho > copiar la dirección para pegarla en el navegador que prefiera) y el programa pasa al siguiente en cuanto llega el archivo;
- `--timeout 600`: esperar hasta 600 s cada descarga (300 por defecto, 900 en modo manual);
- `--no-browser`: no abrir el índice al final;
- `--downloads CARPETA`: recordar la carpeta donde su navegador guarda las descargas (el mismo ajuste que «Cambiar» en el índice); `--downloads ""` vuelve a la carpeta del sistema. Sola, sin archivo que importar, la opción guarda el ajuste y se detiene.

Cada opción tiene también un nombre francés (`--tout`, `--navigateur`, `--manuel`, `--delai`, `--sans-navigateur`, `--telechargements`…), que muestra `--help`.

**Requisito**: tener la sesión iniciada en claude.ai en el navegador que abre los enlaces (los enlaces de exportación solo funcionan en una sesión iniciada). En modo automático, cada enlace también se muestra en el terminal: si se abrió el navegador equivocado, ábralo en el correcto, el programa detectará el archivo igualmente. Ctrl + C detiene limpiamente; volver a ejecutar el mismo comando reanuda donde se quedó.

Navegadores: todos los que guardan en la carpeta de descargas habitual (descargas en curso `.crdownload` de Chrome, Brave, Edge, Opera, Vivaldi, `.part` de Firefox, `.download` de Safari), o en la carpeta indicada con `--downloads`. La carpeta del sistema se encuentra con `xdg-user-dir` en Linux y en el registro en Windows (aunque se haya movido, por ejemplo a OneDrive). Probado en Linux; macOS y Windows deberían funcionar pero aún no se han probado.

Los enlaces caducan 24 horas después de crear la exportación; pasado ese plazo, el programa lo indica y recuerda cómo solicitar una nueva exportación. Solo se abren enlaces a `https://claude.ai/`, y no se maneja ninguna credencial: la descarga se hace en su propio navegador.

También puede indicar directamente los archivos ZIP (o la carpeta extraída):

```
python3 claude-export-viewer.py ~/Descargas/conversations-000.zip -o ~/claude_site
```

Las conversaciones sin ningún texto intercambiado se excluyen del sitio: así aparecen en la exportación las conversaciones eliminadas, a veces con un resto (imagen o archivo adjunto, respuesta vacía) que no cuenta como texto. Añada `--keep-empty` para incluirlas de todos modos.

## Categorías

Cada conversación puede recibir una categoría de su elección («matemáticas», «medicina», «ciencias»…), una por conversación.

- **Elegir**: cuando el índice se abre con el icono, un pequeño menú a la derecha de cada conversación ofrece las categorías existentes, «Ninguna categoría» y **Nueva categoría…** para crear una (40 caracteres como máximo; «Mates» y «mates» son la misma categoría).
- **Filtrar**: en cuanto existe una categoría, aparece un menú «Todas las categorías» junto a los demás filtros, con «Sin categoría» y cada una de las categorías. Se combina con la búsqueda, los demás filtros y todos los órdenes: con «Todas las categorías», todas las conversaciones siguen visibles.
- **Gestionar**: el botón **Gestionar categorías**, junto al botón de importación, muestra cada categoría con su número de conversaciones, para renombrarla (renombrarla como una categoría existente fusiona ambas) o eliminarla (sus conversaciones se quedan, sin categoría).

Las categorías se guardan en el archivo (`archive/topics.json`): siguen al sitio (memoria USB, otro navegador) y sobreviven a las importaciones siguientes. Abierto directamente desde `index.html`, sin el programa, el índice muestra las categorías y permite filtrar, pero no modificarlas.

## Dónde colocar el programa y el sitio

La carpeta del programa (`claude-export-viewer`) y la del sitio (`claude_site`, elegida con `-o`) pueden estar en cualquier lugar, incluida una memoria USB:

```
python3 /media/yo/USB/claude-export-viewer/claude-export-viewer.py ~/Descargas -o /media/yo/USB/claude_site
```

El sitio se abre luego desde `index.html`, en cualquier ordenador, incluso sin el programa (el botón de importación y las exportaciones .odt/.docx necesitan el programa; las exportaciones .md y .pdf funcionan en todas partes). El icono y los comandos mostrados en las páginas guardan rutas completas: si la memoria se monta en otro lugar (otro ordenador, otra letra de unidad en Windows), vuelva a crear el icono desde la nueva ubicación; las páginas se actualizan en la siguiente importación.

## Idiomas

El programa habla 12 idiomas: inglés, francés, español, alemán, italiano, portugués, neerlandés, polaco, ruso, chino (simplificado), japonés y coreano.

- **Las páginas** se abren en el idioma del navegador, o en inglés si no está disponible. El menú de la parte superior derecha del índice cambia el idioma de todo el sitio con un clic: índice, conversaciones, fechas (en el formato de cada país), exportaciones y registro de importación. El navegador recuerda la elección.
- **Los mensajes de la consola** siguen el idioma del sistema, o la opción `--lang` (`--langue`): `--lang es`, `--lang de`…
- **El nombre del icono** sigue el idioma de la sesión («Archivos de Claude» en español, «Claude Archives» en inglés…).
- Las conversaciones en sí nunca se traducen. El código y las fórmulas están marcados para que la traducción automática de un navegador no los altere.

Las traducciones distintas del francés y el inglés son traducciones automáticas: las correcciones son bienvenidas. Cada idioma es un simple archivo de texto, `src/claude_export_viewer/i18n/<código>.json`; una frase que falta en un idioma se muestra en inglés.

## Exportar una conversación (.md, .odt, .docx, .pdf)

Cada página de conversación ofrece «Exportar: .md .odt .docx .pdf», seguido de la casilla **Incluir las otras versiones y las partes eliminadas**:

- marcada (por defecto): se exporta todo, con las otras versiones y las partes eliminadas en marcos con sangría, en su punto de bifurcación;
- desmarcada: solo se exporta el **hilo principal** (el que se muestra en la página), y el nombre del archivo termina en «(hilo principal)».

El navegador recuerda la última elección. En la línea de comandos, la casilla desmarcada es la opción `--main-thread`.

- **.md** funciona siempre, directamente en el navegador.
- **.pdf** también funciona siempre: abre la ventana de impresión del navegador, donde basta con elegir «Guardar como PDF». Las fórmulas se ven exactamente como en pantalla, sobre fondo blanco incluso en modo oscuro; el contenido es el mismo que en los demás formatos (sin razonamientos ni herramientas) y se propone el nombre del archivo.
- **.odt** (LibreOffice) y **.docx** (Word) pasan por Pandoc, que convierte las fórmulas LaTeX en fórmulas reales y editables. Instálelo una vez (véase «Dependencias opcionales»). Dos maneras de usarlas:
  - **con un clic**, consultando el sitio a través del pequeño servidor local integrado:  
    `python3 claude-export-viewer.py -o ~/claude_site --serve`  
    y se abre http://127.0.0.1:8000 (Ctrl + C para detenerlo). Solo se puede acceder al servidor desde su ordenador;
  - **con un comando**, si la página se abre sin el servidor: el botón muestra el comando exacto que hay que copiar, por ejemplo  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pitágoras"`  
    (título, comienzo del título o identificador; `--export-dir` para elegir dónde escribir el archivo).

Las fórmulas que Pandoc no sabe convertir quedan en LaTeX en el documento, y el programa las indica.

## Archivo acumulativo: añadir las siguientes exportaciones

Cada exportación de claude.ai es una instantánea de su cuenta en un momento dado. La carpeta del sitio contiene un **archivo** (`archive/`) que acumula todas las exportaciones importadas. Para una nueva exportación, basta con volver a ejecutar el mismo comando con la misma carpeta `-o`: solo se procesan las conversaciones nuevas o modificadas.

- **Sin duplicados**: cada conversación se reconoce por su identificador.
- **No se pierde nada**: una conversación eliminada en claude.ai permanece en el archivo, con una etiqueta «Eliminada en claude.ai» en el índice, un aviso en su página y un filtro para mostrarlas u ocultarlas.
- **Mensajes desaparecidos**: la exportación contiene todas las versiones de una conversación (mensajes editados, respuestas regeneradas). Si aun así desaparecieran mensajes de una exportación posterior, el archivo los conserva y los muestra en su lugar, en un marco «Parte eliminada en claude.ai».
- **Cualquier orden**: importar una exportación más antigua después de una más reciente completa el archivo sin sobrescribir nada.
- **Fecha de cada exportación**: el programa busca el manifiesto junto al zip (si hay varios, conserva el primero creado después del mensaje más reciente de la exportación); si no, toma la fecha de ese mensaje. También puede indicarla con `--export-date AAAA-MM-DD`.

**No elimine la carpeta del sitio**: `archive/` contiene la copia de sus conversaciones, incluidas las que ya no existen en claude.ai. Para hacer una copia de seguridad, copie esta carpeta. Para actualizar el programa, sustituya la carpeta del programa y ejecute el comando sin exportación para regenerar las páginas:

```
python3 claude-export-viewer.py -o ~/claude_site
```

Opciones útiles: `--rebuild` (regenerar todas las páginas), `--structure EXPORTACION.zip` (muestra solo los nombres de los campos de la exportación, sin ningún contenido: útil para informar de un problema).

El progreso se muestra cada 50 conversaciones. Los elementos ilegibles se omiten y se indican con un aviso al final, sin detener el proceso.

## Cambios respecto al original

- **Memoria constante**: las conversaciones se leen y escriben de una en una (en flujo), en lugar de cargar toda la exportación. Medido con una exportación ficticia de 595 MB: 57 MB de memoria como máximo (el original necesita unas 4 veces el tamaño del archivo).
- **Nuevo formato de exportación**: acepta la exportación dividida en varios ZIP, una carpeta o archivos `.json` / `.jsonl`, sea cual sea su nombre exacto. El original solo buscaba `conversations.json` y, si no, indicaba «0 conversaciones» sin error.
- **Tolerancia**: un tipo de contenido desconocido (imagen, búsqueda web…), un remitente inesperado, un campo vacío o una fecha ilegible ya no bloquean todo el proceso; se muestran de forma genérica o se ignoran.
- **Seguridad**: los enlaces `javascript:` (y otros protocolos peligrosos) se neutralizan; las imágenes citadas en una conversación se muestran como enlaces, sin cargarlas (el archivo sigue siendo legible sin conexión, sin contactar con sitios de terceros); la exportación .odt / .docx no puede incrustar un archivo del ordenador.
- **Robustez**: una conversación que no se puede mostrar se indica y se omite sin detener la generación del sitio; un archivo dañado da un mensaje claro; un proyecto guardado en varias líneas se reconoce correctamente.
- **Resaltado del código**.
- **Fórmulas LaTeX**: protegidas del Markdown (los `_`, `*` y `\\` de las fórmulas ya no se estropean) y mostradas con KaTeX 0.16.47, incluido en la carpeta generada (sin necesidad de conexión). Renderizado progresivo al desplazarse: una página de 3000 fórmulas se abre en menos de un segundo; todo se renderiza antes de imprimir o exportar a PDF.
- **Botón «Copiar»** en cada marco de código (bloques de código y artefactos), con el nombre del lenguaje, como en claude.ai; corrige de paso un `<code>` doble para los lenguajes desconocidos.
- **Archivo acumulativo** de las exportaciones sucesivas: sin duplicados, conversaciones eliminadas en claude.ai conservadas y señaladas, partes eliminadas de una conversación conservadas en su lugar, solo se regeneran las páginas modificadas.
- **Descarga guiada** a partir del manifiesto: enlaces abiertos uno por uno en el navegador, espera a que termine cada descarga, archivos guardados en el archivo, importación y apertura del índice.
- **Exportación a Markdown** de cada conversación, con un clic, sin archivo creado de antemano (el contenido está incrustado en la página y el navegador fabrica el archivo).
- **Exportación .odt / .docx** mediante Pandoc (comando `--odt` / `--docx`, o con un clic con el servidor local `--serve`); corrección automática de una construcción LaTeX que Pandoc rechaza (`\textbf` dentro de `\text{…}`).
- **Multilingüe**: 12 idiomas para las páginas, la consola, las exportaciones y el icono, con un menú de idioma en el índice.
- **Icono de inicio** (`--install-icon`), servidor local que se detiene solo (`--open`), botón «Importar un nuevo manifiesto» protegido por un token; casilla «Incluir las otras versiones» para exportarlo todo o solo el hilo principal.
- **Sin dependencia de uv**: un lanzador `claude-export-viewer.py` para el `python3` del sistema.
- **Categorías** propias, con filtro y gestión (renombrar, fusionar, eliminar), guardadas en el archivo.
- **Carpeta de descargas** configurable (índice o `--downloads`), para un navegador que guarda en otro lugar o una memoria USB.
- **Windows** (no probado): carpeta de descargas leída del registro, textos en UTF-8, comandos `py` con las comillas de Windows, accesos directos en el menú Inicio y en el escritorio.
- **Búsqueda en el contenido** de las conversaciones, con palabras resaltadas y paso de un resultado a otro; palabras, comandos LaTeX y símbolos.
- **Documentos adjuntos completos** (sin el límite de 3000 caracteres), abiertos con el programa del ordenador; **sus archivos recuperados** del ordenador y mostrados en las conversaciones.
- **Lectura**: respuestas de Claude plegables, copia de un mensaje, navegación con el teclado y el teclado numérico, desplazamiento lento y continuo.

## Dependencias opcionales

- **Pandoc** (exportaciones .odt y .docx; probado con Pandoc 3.7):
  - en Linux Ubuntu: `sudo apt install pandoc`;
  - en Windows: `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (comando indicado por [pandoc.org](https://pandoc.org/installing.html));
  - en macOS: `brew install pandoc`.

## Licencia y agradecimientos

Software libre con **licencia MIT** (archivo `LICENSE`): puede usarlo, copiarlo, modificarlo, redistribuirlo y explotarlo libremente, con la única condición de conservar el aviso de copyright, que cita a sus autores, y el texto de la licencia. Se proporciona «tal cual», sin ninguna garantía: sus autores no se hacen responsables de ningún daño derivado de su uso.

- **Autor del proyecto original**: Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), proyecto [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Muchas gracias a él por esta base clara y bien diseñada, sin la cual esta versión no existiría.
- **Modificaciones y añadidos**: fordom.
- **KaTeX** (renderizado de fórmulas, incluido): licencia MIT, Khan Academy y colaboradores, véase `src/claude_export_viewer/static/katex/LICENSE`.

## Pruebas

```
sudo apt install python3-pytest      # Windows: py -m pip install pytest
python3 -m pytest tests/ -v          # Windows: py -m pytest tests/ -v
```

Las particularidades de Windows se comprueban en Linux simulando Windows (`tests/test_windows.py`); el conjunto de pruebas aún no se ha ejecutado en Windows. Las pruebas en el navegador (`tests/test_topics_browser.py`) necesitan Playwright y Chromium; sin ellos, se omiten.
