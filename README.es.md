# Claude Export Viewer

[English](README.md) | [Français](README.fr.md) | **Español** | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

CEV convierte la exportación de sus conversaciones de Claude.ai en una **biblioteca local**: un sitio que se lee en el navegador, sin Internet, donde puede buscar, anotar, reorganizar y exportar sus conversaciones. Cada nueva exportación se suma a las anteriores: no se pierde nada, ni siquiera lo que se haya eliminado después en claude.ai.

> Proyecto independiente, no afiliado a Anthropic. Claude es una marca de Anthropic. Diseñado y probado en Linux (Ubuntu 26.04, Python 3.14); Windows y macOS deberían funcionar, pero aún no se han probado. 12 idiomas.

## Instalación

1. Instale Python 3 y cuatro bibliotecas:
   - Ubuntu / Debian: `sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments`
   - Windows (Python 3.11 o posterior): `py -m pip install jinja2 mistune pydantic pygments`
2. Descomprima `claude-export-viewer.zip` y haga doble clic en **Installer CEV** (`.sh` en Linux, `.cmd` en Windows, `.command` en macOS).

El programa se instala en `~/claude-export-viewer` y crea el icono **Biblioteca de Claude**. Una actualización se hace de la misma manera, con el nuevo ZIP: sus conversaciones nunca se tocan.

## Primera importación

1. En claude.ai (sitio web o aplicación de escritorio; no desde las aplicaciones móviles): **Configuración > Privacidad > Exportar datos**. Llega un correo con un enlace, válido 24 horas, que descarga un pequeño archivo «manifiesto».
2. Abra la **Biblioteca de Claude** con su icono. En la pestaña **Gestión de los datos**, haga clic en el marco **Importar una exportación**: CEV abre los enlaces de la exportación uno por uno en su navegador, lo importa todo y muestra sus conversaciones.

Repítalo de vez en cuando: las nuevas exportaciones completan el repositorio.

## La Biblioteca: dos partes

La Biblioteca tiene dos partes: el **índice**, que enumera todas sus conversaciones, y la página de cada **conversación**.

## El índice

![La parte superior del índice](docs/en/sommaire.png)

Arriba, el idioma y luego tres pestañas; solo una está abierta a la vez, y un clic en la pestaña abierta la cierra.

**Vista general**: el número de conversaciones, mensajes y tokens, el tamaño del sitio y la actividad semana a semana. **Un clic en una barra filtra la lista por esa semana.** La ficha del tamaño cambia de color cuando se aconseja una copia de seguridad; un clic lleva entonces al botón **Copia de seguridad de la Biblioteca**.

![Vista general](docs/en/vue-ensemble.png)

**Gestión de los datos**: la importación y luego las herramientas de la Biblioteca. **Gestionar categorías** (renombrar, fusionar, eliminar); **Copia de seguridad de la Biblioteca** en un ZIP con fecha; **Exportar todo** en Markdown, legible sin CEV; **Liberar espacio** (archivos que ya no sirven); **Recuperar anotaciones** (CEV guarda los 5 últimos estados de sus anotaciones); **Comprobar el repositorio** (y reparar una conversación dañada a partir de las exportaciones guardadas); **Desinstalar**, tras ofrecer copias de todo.

![Gestión de los datos](docs/en/gestion.png)

**Filtros**: búsqueda en los títulos y en el contenido (texto, fórmulas: `\alpha` o `α`), con un número de **errores tolerados**; categoría, período y orden.

![Filtros](docs/en/filtres.png)

**La lista**: cada conversación con su fecha, su tamaño y sus anotaciones (favoritos, enlaces, notas). El menú de la derecha le asigna una **categoría**. Para **enlazar** dos conversaciones, arrastre una sobre la otra.

![La lista de conversaciones](docs/en/liste.png)

## La conversación

![La parte superior de una conversación](docs/en/discussion.png)

Arriba: el título, con la **Vista** (Lectura o Estructura) a la derecha. Debajo, pestañas cerradas al principio; solo una está abierta a la vez, y un clic en la pestaña abierta la cierra.

- **Visualización**: **Ocultar** aligera la pantalla (recursos de la IA, notas, títulos, números, otras versiones y eliminaciones); **Altura** reduce cada mensaje a 1, 3 o 5 líneas; **Voces** elige las voces de la lectura en voz alta. Sus elecciones se mantienen de una conversación a otra.
- **Exportar**: un archivo .md, .odt, .docx, .txt o .pdf, con o sin sus anotaciones y las otras versiones, en ZIP si lo desea.
- **Enlaces**, **Favoritos**, **Notas** y **Títulos** de la página: un clic lleva a ellos.

**Los mensajes** se muestran como en claude.ai: Markdown, código coloreado con botón Copiar, fórmulas matemáticas, artefactos (los programas de Claude se ejecutan en la página, sin conexión), documentos adjuntos completos.

![Mensajes](docs/en/bulles.png)

- Después de la fecha, los iconos del mensaje: **favorito**, **nota**, **título**, copiar, exportar este mensaje, el ojo (en sus mensajes: mostrar u ocultar la respuesta de Claude), **leerlo en voz alta**.
- Antes del nombre, el lugar del mensaje en la conversación: `1 ← 2 → 2.1 3` = la pregunta 2 sigue a la 1, tiene otra respuesta (2.1) y le sigue la 3. Un clic en una marca lleva a ella.
- **Otra versión**: cuando un mensaje se ha modificado o una respuesta se ha regenerado, las otras versiones siguen legibles en estos marcos, en su lugar.
- **Resaltado** en 5 colores: seleccione un pasaje y luego el lápiz que aparece a su lado (o el botón de la derecha).

Una conversación muy larga se muestra en varias páginas («Parte 2 de 5»), sin separar nunca una pregunta de su respuesta; la búsqueda en la página, la Estructura y la exportación se refieren entonces a la parte mostrada.

**La Estructura** muestra el esquema de la conversación: preguntas numeradas, versiones en ramas. Un clic muestra una pregunta con todas sus respuestas. Puede **reorganizar el orden lógico** (arrastrar una pregunta tras una respuesta, cortar una rama, trazar un enlace lógico en verde) sin tocar el orden real; «Orden: real · lógico», en la barra de la Estructura, pasa de uno a otro.

![La estructura](docs/en/structure.png)

**Las series**: cuando una conversación continúa en otra, abra la pestaña **Enlaces** y arrastre las conversaciones enlazadas en el orden deseado. Cada página de la serie muestra entonces «← anterior · siguiente →», arriba y abajo.

![Una serie](docs/en/suite.png)

<img src="docs/en/boutons.png" align="right" width="70" alt="Los botones de la derecha">

**Los botones de la derecha**, en dos marcos. Arriba: resaltado (la rueda del ratón elige el color), volver al índice, buscar en la conversación, ocultar o mostrar todas las respuestas de Claude, música de fondo, tema claro u oscuro, página anterior o siguiente (‹ ›). Abajo: su mensaje anterior o siguiente, la lectura en voz alta de toda la conversación, el **desplazamiento lento** (velocidad con la rueda), el principio, el medio y el final de la página. El índice tiene los mismos botones, salvo los propios de una conversación.

La **lectura en voz alta** usa voces naturales sin conexión ([Piper](https://github.com/OHF-Voice/piper1-gpl)), instaladas en el primer uso con su consentimiento: una voz para usted, otra para Claude, y la voz del idioma de cada párrafo.

<br clear="right">

## Sus datos

Todo lo importante está en **`~/claude_site/archive/`**: sus conversaciones, las exportaciones originales, sus anotaciones y sus ajustes. Una conversación eliminada en claude.ai se queda ahí, marcada «Eliminada en claude.ai». Para hacer una copia de seguridad, use **Copia de seguridad de la Biblioteca** o copie esta carpeta; para restaurarlo todo, deposite la copia en una Biblioteca vacía.

## Línea de comandos

Todo existe también en un terminal (`python3 claude-export-viewer.py`, `py` en Windows); `--help` da la lista completa.

| Comando | Efecto |
| --- | --- |
| `~/Downloads -o ~/claude_site` | importa la última exportación de la carpeta |
| `-o ~/claude_site --serve` | abre la Biblioteca |
| `--odt "título"`, `--docx "título"` | exporta una conversación |
| `--export-all` | todas las conversaciones en Markdown |
| `--verify`, `--repair` | comprueba el repositorio, repara lo que se puede |
| `--uninstall`, `--restore ZIP` | desinstala, restaura una copia de seguridad |

## Complementos y licencia

CEV nació del [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) de Judson Neer, a quien damos las gracias; desde entonces se ha transformado y ampliado profundamente.

- **Pandoc** para las exportaciones .odt y .docx: `sudo apt install pandoc` (Windows: `winget install --exact --id JohnMacFarlane.Pandoc`; macOS: `brew install pandoc`).
- **Piper** para la lectura en voz alta: CEV lo ofrece en el primer uso (unos 200 MB, más 60 MB por voz).

Software libre bajo **licencia MIT** (archivo `LICENSE`), proporcionado sin garantía. Incluido: KaTeX (MIT). Instalado aparte a petición suya: Piper (GPL-3). Pruebas: `python3 -m pytest tests/`.
