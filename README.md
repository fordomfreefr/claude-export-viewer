# Claude Export Viewer (version 2026.10.25.1)

**English** | [Français](README.fr.md)

Turn the chat history of Claude.ai into a local HTML site that any browser can open, with no internet connection, and keep a cumulative archive of your conversations, including the ones deleted from Claude.ai since.

This project is based on [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) by Judson Neer, heavily modified and extended (see "License and thanks").

> This project is independent and not affiliated with Anthropic. Claude is a trademark of Anthropic.

> It was designed and tested on Linux Ubuntu 26.04, in Python 3.14 and JavaScript. It should work on Windows. The code was written with Claude (Opus 5.5 model, high reasoning effort).

## Quick start on Linux Ubuntu / Debian

1. Get the chat history on claude.ai: **Settings > Privacy > Export data**. You will receive a first information e-mail, then a second one with a link to download a "manifest" file.

2. Install the 4 libraries and Pandoc from a terminal:  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Save the program `claude-export-viewer.zip` in `~/Downloads`.

4. Unzip it into your home folder, then run it: the files of the export are downloaded from the manifest and imported, then the index opens.  
`cd ~/Downloads && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Downloads -o ~/claude_site`  
(The `rm -rf` only removes the previous version of the program: your conversations are in `~/claude_site`.)

5. Once and for all, create the launcher icon on the desktop:  
`python3 claude-export-viewer.py -o ~/claude_site --install-icon`

## Features

- **General index** of all your chats, with:
  - search in the titles, with a result counter;
  - sorting of the conversations: by creation date, date of the last exchange, title, number of messages;
  - **topics** of your own, chosen in a small menu on the right of each conversation, for custom filtering.
- **In each conversation**:
  - local date and time, an **Open on claude.ai** link (if it still exists there);
  - formatted Markdown (bold, lists, tables) and highlighted code (Pygments);
  - code frames with the name of the language and a **Copy** button (copies the exact code to the clipboard);
  - **mathematical formulas rendered as in LaTeX** (KaTeX, bundled, offline): `$…$`, `$$…$$`, `\(…\)`, `\[…\]`; copying a passage copies the LaTeX source of its formulas; a formula that cannot be rendered stays as source, with the reason in a tooltip;
  - artifacts shown (code, documents, HTML/SVG shown as code, never run);
  - thinking, tool calls and tool results in collapsible blocks;
  - **multiple versions**: when a message was edited or an answer regenerated, the page follows the version that leads to the last exchange; the other versions are in collapsible "Other version" frames, where the conversation forked;
  - **export to Markdown, LibreOffice (.odt) and Word (.docx) on demand**: a ".md" button on each conversation; the file holds the main thread and, in frames (quotes) with labels in italics, every other version at its fork point (or, box unchecked, the main thread only); formulas as `$…$`, code, artifacts and names of attachments included (no thinking, no tool results); readable by Typora, Obsidian, Zettlr, convertible by Pandoc;
  - **PDF export** through the browser's print window, formulas included.
- **Cumulative archive**: successive exports are added without duplicates, and conversations deleted from claude.ai since are kept.
- **12 languages** (pages, console, exports), chosen on the index.
- **Desktop icon** (Linux, Windows) that opens the index and imports a new export with one click.
- Light or dark theme, following the system setting.

## Installation

Unzip this folder anywhere you like (disk, USB key…), then install the four libraries it needs.

**Ubuntu / Debian**: see "Quick start" above.

**Windows** (Python 3.11 or newer, from [python.org](https://www.python.org/downloads/) or the Microsoft Store), in a terminal (PowerShell or Command Prompt):

```
py -m pip install jinja2 mistune pydantic pygments
```

On Windows, replace `python3` with `py` in the commands of this document, and the `~/…` paths with Windows paths (`C:\Users\[User]\claude_site`, `E:\claude_site` for a USB key…). **Windows support was written from the documentation of Python and Windows, but has not been tried on a Windows machine yet**: feedback is welcome.

## The "Claude Archives" icon (the easiest way)

After the first import (see below), create the icon once:

```
python3 claude-export-viewer.py -o ~/claude_site --install-icon
```

It appears in the applications menu and on the desktop (Linux; KDE may ask once to trust the launcher), or in the Start menu and on the desktop (Windows: shortcuts created by PowerShell, which run `pythonw.exe`, so no console window opens; not tried). A click opens the index in the browser, served by a small local server (http://127.0.0.1:8000) that stops by itself 30 minutes after the last page was closed (`--idle` to change this delay). A second click reuses the server already running, unless it was started by an earlier version of the program: it is then stopped and replaced, so that the new version is really used. Put the program in a stable folder (for example `~/claude-export-viewer`) before creating the icon.

Opened by the icon, the index gathers its settings in a frame at the top: the **Import a new manifest** and **Manage topics** buttons, then the downloads folder and its **Change** button. Each button opens its panel; a second click (or the cross) closes it. The **Import a new manifest** button: after you have requested the export on claude.ai and clicked the link of the e-mail saying that your data is ready, it takes the most recent manifest of your Downloads, opens the links one by one (they are also shown, clickable, in the log of the page), imports the export and reloads the index. Closing the log during an import does not stop it: another click shows it again.

In the same frame, the **Downloads folder** line shows where the manifest is looked for. If your browser saves files elsewhere (its "Save files to" or "Location" setting), click **Change** and enter that folder: it is remembered in the archive and searched first, before the folder of the system. Leaving the field empty goes back to the folder of the system; if the chosen folder disappears (USB key removed), the folder of the system is used.

And on each conversation, the .md, .odt and .docx exports work with a click.

**Security**: the server only listens on your computer (127.0.0.1) and does not serve the raw archive. Importing requires a "secret token" that only the index pages can read, and requests coming from another site are refused: a web page open in the same browser cannot trigger them.

## Command line

1. On claude.ai: **Settings > Privacy > Export data**.
2. When the e-mail arrives, click its link: the browser downloads a small "manifest" file (the list of the files of the export and their links).
3. Run:

```
python3 claude-export-viewer.py ~/Downloads -o ~/claude_site
```

The program takes the most recent manifest of the folder, then:

- opens each link itself in your browser (where you are signed in to claude.ai), **one by one**, waiting for each download to finish (a link may stop working once used);
- finds the files already downloaded, even renamed by the browser (`conversations-000 (1).zip`), and ignores those of an earlier export;
- moves the files to `~/claude_site/archive/exports/<date>/`;
- imports the export into the archive and opens the index.

By default, only the useful files are fetched (conversations, projects, account). Options:

- `--all`: fetch the 7 files of the export (complete backup);
- `--browser brave-browser`: choose the browser that opens the links;
- `--manual`: open nothing; the links are shown one by one in the terminal (Ctrl + click to open them, or right click > copy the address to paste it into the browser of your choice) and the program moves on to the next one as soon as the file has arrived;
- `--timeout 600`: wait up to 600 s for each download (300 by default, 900 in manual mode);
- `--no-browser`: do not open the index at the end;
- `--downloads FOLDER`: remember the folder where your browser saves downloads (the same setting as "Change" on the index); `--downloads ""` goes back to the folder of the system. Alone, with no file to import, the option saves the setting and stops.

Every option also has a French name (`--tout`, `--navigateur`, `--manuel`, `--delai`, `--sans-navigateur`, `--telechargements`…), shown by `--help`.

**Requirement**: be signed in to claude.ai in the browser that opens the links (export links only work in a signed-in session). In automatic mode, each link is also shown in the terminal: if the wrong browser opened, open it in the right one, the program will still notice the file. Ctrl + C stops cleanly; running the same command again resumes where it stopped.

Browsers: all those that save to the usual download folder (downloads in progress `.crdownload` of Chrome, Brave, Edge, Opera, Vivaldi, `.part` of Firefox, `.download` of Safari), or to the folder given by `--downloads`. The folder of the system is found by `xdg-user-dir` on Linux and in the registry on Windows (even when moved, for example to OneDrive). Tested on Linux; macOS and Windows should work but have not been tried yet.

The links expire 24 hours after the export was created; after that, the program says so and reminds you how to request a new export. Only links to `https://claude.ai/` are ever opened, and no credentials are handled: the download happens in your own browser.

You can also give the ZIP files (or the extracted folder) directly:

```
python3 claude-export-viewer.py ~/Downloads/conversations-000.zip -o ~/claude_site
```

Conversations without any exchanged text are left out of the site: this is how conversations deleted before the export appear in it, sometimes with a leftover (image or attached file, empty answer) that does not count as text. Add `--keep-empty` to include them anyway.

## Topics

Each conversation can be given a topic of your choice ("math", "medicine", "science"…), one per conversation.

- **Choose**: when the index is opened by the icon, a small menu on the right of each conversation offers the existing topics, "No topic", and **New topic…** to create one (40 characters at most; "Math" and "math" are the same topic).
- **Filter**: as soon as a topic exists, an "All topics" menu appears next to the other filters, with "Without topic" and each topic. It combines with the search, the other filters and every sort order: on "All topics", every conversation stays visible.
- **Manage**: the **Manage topics** button, next to the import button, lists each topic with its number of conversations, to rename it (renaming into an existing topic merges both) or delete it (its conversations stay, without a topic).

Topics are saved in the archive (`archive/topics.json`): they follow the site (USB key, another browser) and survive later imports. Opened directly from `index.html`, without the program, the index shows the topics and can filter on them, but not change them.

## Where to put the program and the site

The program folder (`claude-export-viewer`) and the site folder (`claude_site`, chosen with `-o`) can be anywhere, a USB key included:

```
python3 /media/me/USBKEY/claude-export-viewer/claude-export-viewer.py ~/Downloads -o /media/me/USBKEY/claude_site
```

The site then opens from `index.html`, on any computer, even without the program (the import button and the .odt/.docx exports need the program; the .md and .pdf exports work everywhere). The icon and the commands shown in the pages keep full paths: if the key is mounted elsewhere (another computer, another drive letter on Windows), create the icon again from the new location; the pages are updated at the next import.

## Languages

The program speaks 12 languages: English, French, Spanish, German, Italian, Portuguese (Brazil), Dutch, Polish, Russian, Chinese (simplified), Japanese and Korean.

- **The pages** open in the browser's language, or in English when it is not available. The menu at the top right of the index changes the language of the whole site with one click: index, conversations, dates (in each country's format), exports and import log. The browser remembers the choice.
- **Console messages** follow the system language, or the `--lang` option (`--langue`): `--lang fr`, `--lang de`…
- **The name of the icon** follows the language of the session ("Claude Archives" in English, "Archives Claude" in French…).
- The conversations themselves are never translated. Code and formulas are marked so that a browser's automatic translation leaves them intact.

Translations other than French and English are machine translations: corrections are welcome. Each language is a plain text file, `src/claude_export_viewer/i18n/<code>.json`; a sentence missing from a language is shown in English.

## Exporting a conversation (.md, .odt, .docx, .pdf)

Each conversation page offers "Export: .md .odt .docx .pdf", followed by the **Include the other versions and the deleted parts** box:

- checked (default): everything is exported, the other versions and the deleted parts in indented frames, at their fork point;
- unchecked: only the **main thread** is exported (the one shown on the page), and the file name ends with "(main thread)".

The browser remembers the last choice. On the command line, the unchecked box is the `--main-thread` option.

- **.md** always works, directly in the browser.
- **.pdf** always works too: it opens the browser's print window, where you just choose "Save as PDF". Formulas look exactly as on screen, on a white background even in dark mode; the content is the same as for the other formats (no thinking, no tools) and the file name is suggested.
- **.odt** (LibreOffice) and **.docx** (Word) go through Pandoc, which turns LaTeX formulas into real, editable formulas. Install it once (see "Optional dependencies"). Two ways to use them:
  - **with a click**, browsing the site through the small built-in local server:  
    `python3 claude-export-viewer.py -o ~/claude_site --serve`  
    then http://127.0.0.1:8000 opens (Ctrl + C to stop). The server can only be reached from your computer;
  - **with a command**, if the page is opened without the server: the button shows the exact command to copy, for example  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pythagoras"`  
    (title, beginning of the title or identifier; `--export-dir` to choose where to write the file).

Formulas that Pandoc cannot convert stay as LaTeX in the document, and the program reports them.

## Cumulative archive: adding the next exports

Each claude.ai export is a snapshot of your account at a given moment. The site folder holds an **archive** (`archive/`) that accumulates every imported export. For a new export, simply run the same command with the same `-o` folder: only new or changed conversations are processed.

- **No duplicates**: each conversation is recognized by its identifier.
- **Nothing is lost**: a conversation deleted from claude.ai stays in the archive, with a "Deleted on claude.ai" badge in the index, a banner on its page and a filter to show or hide them.
- **Vanished messages**: the export holds every version of a conversation (edited messages, regenerated answers). Should messages still vanish from a later export, the archive keeps them and shows them in place, in a "Part deleted on claude.ai" frame.
- **Any order**: importing an older export after a newer one completes the archive without overwriting anything.
- **Date of each export**: the program looks for the manifest next to the zip (if there are several, it keeps the first one created after the most recent message of the export); otherwise it takes the date of that message. You can also give it with `--export-date YYYY-MM-DD`.

**Do not delete the site folder**: `archive/` holds the copy of your conversations, including those that no longer exist on claude.ai. To back up, copy this folder. To update the program, replace the program folder, then run the command without an export to regenerate the pages:

```
python3 claude-export-viewer.py -o ~/claude_site
```

Useful options: `--rebuild` (regenerate every page), `--structure EXPORT.zip` (only shows the names of the fields of the export, without any content: useful to report a problem).

Progress is shown every 50 conversations. Unreadable items are skipped and reported by a warning at the end, without stopping the processing.

## Changes from the original

- **Constant memory**: conversations are read and written one at a time (streaming), instead of loading the whole export. Measured on a fake 595 MB export: 57 MB of memory at most (the original needs about 4 times the size of the file).
- **New export format**: accepts the export split into several ZIPs, a folder, or `.json` / `.jsonl` files, whatever their exact name. The original only looked for `conversations.json` and reported "0 conversations" without an error otherwise.
- **Tolerance**: an unknown content type (image, web search…), an unexpected sender, an empty field or an unreadable date no longer crash the whole processing; they are shown generically or ignored.
- **Security**: `javascript:` links (and other dangerous protocols) are neutralized; images cited in a conversation are shown as links, without being loaded (the archive stays readable offline, without contacting third-party sites); the .odt / .docx export cannot embed a file of the computer.
- **Robustness**: a conversation that cannot be displayed is reported and skipped without stopping the generation of the site; a damaged archive gives a clear message; a project saved over several lines is recognized.
- **Code highlighting**.
- **LaTeX formulas**: protected from Markdown (the `_`, `*` and `\\` of formulas are no longer damaged), then rendered by KaTeX 0.16.47, bundled in the generated folder (no connection needed). Progressive rendering while scrolling: a page of 3,000 formulas opens in under a second; everything is rendered before printing or exporting to PDF.
- **"Copy" button** on each code frame (code blocks and artifacts), with the name of the language, as on claude.ai; fixes a double `<code>` for unknown languages along the way.
- **Cumulative archive** of successive exports: no duplicates, conversations deleted from claude.ai kept and flagged, deleted parts of a conversation kept in place, only the changed pages regenerated.
- **Guided download** from the manifest: links opened one by one in the browser, wait for each download to finish, files stored in the archive, import and opening of the index.
- **Markdown export** of each conversation, with a click, with no file created in advance (the content is embedded in the page and the file made by the browser).
- **.odt / .docx export** through Pandoc (`--odt` / `--docx` command, or with a click with the local server `--serve`); automatic fix of a LaTeX construct that Pandoc rejects (`\textbf` inside `\text{…}`).
- **Multilingual**: 12 languages for the pages, the console, the exports and the icon, with a language menu on the index.
- **Launcher icon** (`--install-icon`), local server that stops by itself (`--open`), "Import a new manifest" button protected by a token; "Include the other versions" box to export everything or the main thread only.
- **No more dependency on uv**: a `claude-export-viewer.py` launcher for the system's `python3`.
- **Topics** of your own, with a filter and management (rename, merge, delete), saved in the archive.
- **Downloads folder** setting (index or `--downloads`), for a browser that saves elsewhere or a USB key.
- **Windows** (not tested): Downloads folder read from the registry, text in UTF-8, `py` commands with Windows quoting, shortcuts in the Start menu and on the desktop.

## Optional dependencies

- **Pandoc** (.odt and .docx exports; tested with Pandoc 3.7):
  - on Linux Ubuntu: `sudo apt install pandoc`;
  - on Windows: `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (command given by [pandoc.org](https://pandoc.org/installing.html));
  - on macOS: `brew install pandoc`.

## License and thanks

Free software under the **MIT license** (`LICENSE` file): you may use, copy, modify, redistribute and exploit it freely, on the sole condition of keeping the copyright notice, which names its authors, and the text of the license. It is provided "as is", without any warranty: its authors are not liable for any damage arising from its use.

- **Author of the original project**: Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), project [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Many thanks to him for this clear and well-designed base, without which this version would not exist.
- **Changes and additions**: fordom.
- **KaTeX** (formula rendering, bundled): MIT license, Khan Academy and contributors, see `src/claude_export_viewer/static/katex/LICENSE`.

## Tests

```
sudo apt install python3-pytest      # Windows: py -m pip install pytest
python3 -m pytest tests/ -v          # Windows: py -m pytest tests/ -v
```

Windows specifics are checked on Linux by simulating Windows (`tests/test_windows.py`); the suite has not been run on Windows yet. The browser tests (`tests/test_topics_browser.py`) need Playwright and Chromium; they are skipped otherwise.
