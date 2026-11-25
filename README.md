# Claude Export Viewer

**English** | [Français](README.fr.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

CEV turns the export of your Claude.ai conversations into a **local library**: a site you read in your browser, offline, where you can search, annotate, reorganize and export your conversations. Each new export is added to the previous ones: nothing is lost, not even what has since been deleted on claude.ai.

> Independent project, not affiliated with Anthropic. Claude is a trademark of Anthropic. Designed and tested on Linux (Ubuntu 26.04, Python 3.14); Windows and macOS should work but have not been tried yet. 12 languages.

## Installation

1. Install Python 3 and four libraries:
   - Ubuntu / Debian: `sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments`
   - Windows (Python 3.11 or later): `py -m pip install jinja2 mistune pydantic pygments`
2. Unzip `claude-export-viewer.zip` and double-click **Installer CEV** (`.sh` on Linux, `.cmd` on Windows, `.command` on macOS).

The program goes into `~/claude-export-viewer` and creates the **Claude Library** icon. An update is done the same way, with the new ZIP: your conversations are never touched.

## First import

1. On claude.ai (website or desktop app; not from the mobile apps): **Settings > Privacy > Export data**. An e-mail arrives with a link, valid for 24 hours, that downloads a small "manifest" file.
2. Open the **Claude Library** with its icon. In the **Data management** tab, click the **Import an export** frame: CEV opens the links of the export one by one in your browser, imports everything and shows your conversations.

Do it again from time to time: new exports complete the archive.

## The Library: two parts

The Library has two parts: the **table of contents**, which lists all your conversations, and the **conversation** page of each one.

## The table of contents

![The top of the table of contents](docs/en/sommaire.png)

At the top, the language, then three tabs; only one is open at a time, and a click on the open tab closes it.

**Overview**: the number of conversations, messages and tokens, the size of the site, and the activity week by week. **A click on a bar filters the list on that week.** The size tile changes color when a backup is advised; a click then leads to the **Back up the Library** button.

![Overview](docs/en/vue-ensemble.png)

**Data management**: the import, then the tools of the Library. **Manage topics** (rename, merge, delete); **Back up the Library** into a dated ZIP; **Export all** as Markdown, readable without CEV; **Free up space** (files no longer needed); **Recover annotations** (CEV keeps the last 5 states of your annotations); **Check the archive** (and repair a damaged conversation from the kept exports); **Uninstall**, after offering copies of everything.

![Data management](docs/en/gestion.png)

**Filters**: search in the titles and in the content (text, formulas: `\alpha` or `α`), with a number of **typos allowed**; topic, period and sorting.

![Filters](docs/en/filtres.png)

**The list**: each conversation with its date, its size and its annotations (favorites, links, notes). The menu on the right gives it a **topic**. To **link** two conversations, drag one onto the other.

![The list of conversations](docs/en/liste.png)

## The conversation

![The top of a conversation](docs/en/discussion.png)

At the top: the title, with the **View** (Reading or Structure) on the right. Below, tabs that are closed at first; only one is open at a time, and a click on the open tab closes it.

- **Bubbles**: **Hide** lightens the screen (the AI's resources, notes, titles, numbers, other versions and deletions); **Display** cuts each bubble to 1, 3 or 5 lines; **Voices** chooses the voices for reading aloud. Your choices stay from one conversation to the next.
- **Export**: a .md, .odt, .docx, .txt or .pdf file, with or without your annotations and the other versions, as a ZIP if you wish.
- **Links**, **Favorites**, **Notes** and **Titles** of the page: a click takes you there.

**The bubbles** are shown as on claude.ai: Markdown, colored code with a Copy button, mathematical formulas, artifacts (Claude's programs run in the page, offline), complete attached documents.

![Bubbles](docs/en/bulles.png)

- After the date, the icons of the bubble: **favorite**, **note**, **title**, copy, export this message, the eye (on your messages: show or hide Claude's answer), **read it aloud**.
- Before the name, the place of the bubble in the conversation: `1 ← 2 → 2.1 3` = question 2 follows 1, has another answer (2.1) and is followed by 3. A click on a dot takes you there.
- **Other version**: when a message was edited or an answer retried, the other versions stay readable in these frames, in their place.
- **Highlighter** with 5 colors: select a passage, then the pen that appears next to it (or the button on the right).

A very long conversation is shown on several pages ("Part 2 of 5"), never separating a question from its answer; searching in the page, the Structure and the export then cover the part shown.

**The Structure** shows the diagram of the conversation: numbered questions, versions as branches. A click shows a question with all its answers. You can **reorganize the logical order** (drag a question after an answer, cut a branch, draw a green logical link) without touching the actual order; "Order: actual · logical", in the Structure bar, switches between the two.

![The structure](docs/en/structure.png)

**Series**: when a conversation continues in another one, open the **Links** tab and drag the linked conversations into the order you want. Each page of the series then shows "← previous · next →", at the top and at the bottom.

![A series](docs/en/suite.png)

<img src="docs/en/boutons.png" align="right" width="70" alt="The buttons on the right">

**The buttons on the right**, in two frames. At the top: highlighter (the mouse wheel chooses the color), back to the table of contents, search in the conversation, hide or show all of Claude's answers, background music, light or dark theme, previous or next page (‹ ›). At the bottom: your previous or next message, reading the whole conversation aloud, **slow scrolling** (speed with the mouse wheel), the top, middle and bottom of the page. The table of contents has the same buttons, except those specific to a conversation.

**Reading aloud** uses natural offline voices ([Piper](https://github.com/OHF-Voice/piper1-gpl)), installed on first use with your consent: one voice for you, one for Claude, and the voice of the language of each paragraph.

<br clear="right">

## Your data

Everything that matters is in **`~/claude_site/archive/`**: your conversations, the original exports, your annotations and your settings. A conversation deleted on claude.ai stays there, marked "Deleted on claude.ai". To back up, use **Back up the Library** or copy this folder; to restore everything, drop the backup onto an empty Library.

## Command line

Everything also exists in a terminal (`python3 claude-export-viewer.py`, `py` on Windows); `--help` gives the full list.

| Command | Effect |
| --- | --- |
| `~/Downloads -o ~/claude_site` | imports the latest export of the folder |
| `-o ~/claude_site --serve` | opens the Library |
| `--odt "title"`, `--docx "title"` | exports a conversation |
| `--export-all` | all conversations as Markdown |
| `--verify`, `--repair` | checks the archive, repairs what can be repaired |
| `--uninstall`, `--restore ZIP` | uninstalls, restores a backup |

## Extras and license

CEV grew out of Judson Neer's [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer), with our thanks; it has since been deeply transformed and expanded.

- **Pandoc** for .odt and .docx exports: `sudo apt install pandoc` (Windows: `winget install --exact --id JohnMacFarlane.Pandoc`; macOS: `brew install pandoc`).
- **Piper** for reading aloud: offered by CEV on first use (about 200 MB, plus 60 MB per voice).

Free software under the **MIT license** (file `LICENSE`), provided without warranty. Included: KaTeX (MIT). Installed separately at your request: Piper (GPL-3). Tests: `python3 -m pytest tests/`.
