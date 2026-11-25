# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working on this repository.

## What this is

A Python program that keeps a local, cumulative archive of Claude.ai data
exports and turns it into a static HTML site (one page per conversation, an
index), readable offline. User-facing texts are in French.

Run it straight from the folder with the system Python (no install, no uv):

```bash
python3 claude-export-viewer.py ~/Téléchargements -o ~/claude_site   # folder holding the manifest
python3 claude-export-viewer.py conversations-000.zip -o ~/claude_site
python3 claude-export-viewer.py -o ~/claude_site                     # regenerate from the archive
python3 claude-export-viewer.py -o ~/claude_site --ouvrir            # what the desktop icon runs
python3 -m pytest tests/
```

Dependencies (Ubuntu packages): python3-jinja2, python3-mistune (3.1.4 on
Ubuntu 26.04, the code must work with every mistune 3.x), python3-pydantic,
python3-pygments. Pandoc is optional (.odt/.docx).

## Data flow

export ZIPs → `loader` (streaming, tolerant) → `archive` (merge into
`archive/etat.json` + one gzipped raw conversation per file) →
`html_builder.build_site_from_archive` (incremental) → pages + index.

There is a single rendering path: every page is rendered from the archived raw
conversation, so what tests check is what the program produces
(`tests/helpers.py` builds sites through the archive).

## Modules

- **`cli.py`** — argparse, the whole workflow (manifest download, import,
  rendering, server). Every message comes from `i18n.t()` (plural forms
  included); the language is pre-read from `--langue` before the parser is
  built, so that `--help` is translated too.
- **`loader.py`** — finds JSON/JSONL files in any mix of ZIPs (old single ZIP,
  newer split `conversations-000.zip`…), folders and files, classifies them by
  name/folder, and yields `(raw dict, Conversation)` one at a time
  (`iter_conversation_records`) so memory stays small. Also the export date
  (manifest given > manifest found next to the data > ZIP date if plausible >
  latest date in the data > today).
  What an import leaves out (AE-f2, 08/11): `found.others` (JSON files of no known kind: memories…),
  `pop_left_out()` (duplicate conversations, block types the pages show only raw — not in `_SHOWN_BLOCKS` —,
  blocks that are not objects with a type); `cli._print_left_out` prints one line "Laissé de côté : …" (or
  "… : rien.") after the import stats, with the manifest categories not used (all but `fetch.USED_CATEGORIES`, said kept in the archive);
  the import log of the index shows it too (output of the job). Tests: tests/test_cli.py.
- **`models.py`** — tolerant Pydantic v2 models: unknown keys and `null`s are
  ignored, unparseable dates become `None`, unknown or broken content blocks
  become `UnknownContent`, broken items are dropped. `parse_message`,
  `is_empty_conversation`.
- **`archive.py`** — cumulative archive. Conversations are merged by uuid and
  never deleted; one missing from the latest export (or emptied) is marked
  "supprimée sur claude.ai" (recomputed at every run). Messages that vanished
  from a conversation are kept under `tree.EXTRA_KEY` with the date of the last
  export holding them. An older export never overwrites a newer version. An import cut short (Ctrl+C,
  power cut) leaves raw files ahead of `etat.json`: the archive still loads and builds, and importing
  the same export again gives exactly the archive of an import never cut (tests/test_interrupted_import.py);
  `archive/import-en-cours.json` ({date, label}) is written when an import starts and removed when the
  state of that same export is saved (another export leaves it): meanwhile the console and the index
  (`.import-cut`, red) ask to run it again.
  Two programs never write it at once: `archive.ArchiveLock` (`archive/verrou`, flock / msvcrt, released
  by the system even when the program is killed, not re-entrant) is taken by the CLI around import +
  build and around a backup (the second one waits: "attente de la fin…"), by the server around a link
  change, the cleaning (409 when busy) and the backup job (waits); never by `build_site_from_archive`.
  The backup leaves the lock file out (tests/test_concurrent.py; msvcrt not run on Windows).
- **`tree.py`** — conversation trees from `parent_message_uuid`: the main
  branch is the path to the most recent message (preferring messages still on
  claude.ai); every other branch is a frame at its fork point ("Autre version",
  or "Partie supprimée sur claude.ai" when all its messages are gone).
  `Item` uses identity equality; `_link` resets children so items can be
  rendered several times.
- **`html_builder.py`** — Jinja2 templates; a page is regenerated only when its
  conversation, its deleted status, the program (`generator_signature()`), the
  launcher path or the site path changed. A conversation that fails to render
  is reported and skipped, never stopping the site.
- **Your bubbles** (style.css): fill `--human-bg` and frame `--human-border` of two distinct blues; in another
  version or a part deleted on claude.ai (`.removed-part`), the frame without the fill (as the empty circles of
  the structure view).
- **Printing** (style.css, 11/11): bubbles without fill (ink), your frame blue, Claude's thin black, the notes in black
  (also from the dark theme). Tests: tests/test_fold_browser.py `test_print_ink`.
- **`renderer.py`** — one `ChatMessage` → HTML. mistune 3 with
  `_HighlightRenderer` (Pygments; code without a language stays plain text),
  safe links, "Copier" button on code blocks. Each run of blocks added by claude.ai
  (injected instructions, tool uses and results, other unknown blocks except the user's
  document / image) goes into one closed `<details class="cev-resources">` "Ressources de
  claude.ai (n)"; thinking between two of them stays inside, at the ends outside
  (`_group_resources`). The magnifier of the right column opens / closes the search bar.
- **`created.py`** — files created by Claude, rebuilt from the export: along the branch of each
  message, replays `create_file` / `Write`, `str_replace` / `Edit` (one occurrence, or `replace_all`),
  and in shell commands `cat > f << 'EOF'` (`>>` too; an unquoted tag with `$`, backquotes or `\` is
  unknown), `cp` / `mv` (folders too), `rm`, `cd`; calls answered by an error are skipped. A file
  written by something else (redirection, `tee`, `cp` of an unknown file) is unknown (`text` None); a
  known file changed by `sed -i`, a program naming it near a write, or a replacement that cannot be
  replayed keeps its last content with `complete` False. `reconstruct(raw)` gives, by message key, the
  files it hands over (`present_files`, `SendUserFile`, `/mnt/user-data/outputs/…` links) as they were
  when handed over, numbered by distinct content (`version` / `versions`). Checked on a real archive
  (49 versions identical to the user's files). `TRACE` (diagnosis) is called at each step. The renderer
  shows them at the end of the message (`_created_file`: pill, "version n/N", open / save / copy, content
  folded, warning when incomplete), copied once per content to `files/<page>/_claude/<sha256 12>/<name>`
  (`attachments.save_created`, recorded in `files.json` "claude" so that the cleaning keeps them); they
  are in the Markdown exports (`message_body(files=…)`); only files without content (or changed afterwards)
  become links to the user's files (`userfiles.links_in`).
- **`userfiles.py`** + `static/files.js` — the user's files, associated **link by link**: a link is one file
  named by one message (`files`, `attachments`, files of Claude the export lacks), id
  `<message>/<kind>/<name>[#n]` (`view_key`, the renderer counts the same way). At each run (`update`,
  `cli._find_user_files`) the folders chosen on the index are scanned for the exact names and the copies
  renamed by the browser (`name (1).ext`, candidates kept in `archive/files.json`); every link the user has
  not set gets the most recent file of its exact name (status `auto`), a joined text document the candidate
  with the same text (`same`, any name; else `modified`), none (`none`); a file found once stays when it
  leaves the computer. The user's choice (`how: "user"`: a candidate, a file sent by the browser, or no
  file) is never changed; "auto" removes it. Copies once per content: `files/<page>/<sha256 12>/<link name>`. The copy an automatic association leaves for a newer file is removed at once (`_drop_replaced`, G2), unless another link still uses it; the user's choices are never replaced by `update`.
  `shared()` flags links associated automatically with one file along one branch (successive versions,
  not sibling branches: an edited message repeats its files) — "⚠ Association sûrement fausse". Pages show
  each link (`renderer._linked`: preview of an image, open icon, status line except for the user's own
  choice, button 🔗 with `data-cands`); through the server `files.js` opens the menu and POSTs
  `/__cev__/link` ({page, link, action: path | none | auto, path}: only a path the menu offered) or
  `/__cev__/link-file?page&link&name` (raw body, staged in `archive/depot/lien-*`, removed before the answer), then reloads. Orphans
  (copies no link uses; Claude's copies of pages not rendered since are kept): GET / POST
  `/__cev__/orphans`, button "Nettoyer" ("Nettoyer les fichiers inutilisés" until 14/11) of the index (`admin.js`, frame `#clean-panel`). An earlier
  `files.json` (one answer per name, Yes / No) is dropped; its copies become orphans.
- **`static/run.js`** + `static/run-libs.js` — programs of Claude: React / HTML artifacts, visuals of claude.ai
  (tool `show_widget` of "visualize": `ToolUseContent.widget` = input `title`, `widget_code`, HTML without
  <html>/<body> or SVG; not a resource) and .jsx / .tsx / .html files of Claude shown whole and complete. Each
  is one frame `renderer._runnable` (`.cev-runnable`, `data-run` jsx | tsx | html | widget): a bar (`.cev-bar`:
  ▸ title · type (none for a visual), or the bar of the file; against the line of the frame) with ▶ Visualisation
  ("Visualiser ici"), </> Code, [html 🔗 for a visual], ↓, and ONE strip under it after `data-state` (style.css):
  "closed" at first, "result" (Visualisation, again on each click), "code" (10 lines, with "Copier"), "full";
  ↓ goes code → full → code, and from "closed" to "code" (its title says what it will show); a click on the
  bar outside its buttons only folds an open strip, never opens anything (cursor default when folded); 🔗 folds the strip before its menu
  (files.js), a choice reloads the page (folded); a button with nothing to do is greyed out (pointer-events
  none). A visual has no Code and no ↓ (its code only draws it, kept hidden for run.js). Code cut at
  10 lines (`.cev-longcode`, code frames `.cev-long` of the text) fades on its last line (mask-image). The search of a page shows the whole code
  of a hit (`CEV.showCode`). The result runs in an iframe `sandbox="allow-scripts allow-forms allow-modals"`
  (no allow-same-origin: no access to the site, its storage, the parent) whose srcdoc starts with a CSP
  (default-src 'none', connect-src 'none'); what must come from the Internet (packages not bundled, external
  script / link / img hosts) is asked first with `CEV.confirm` (Oui: https: allowed for that run, a note says
  so; Non: nothing run). JSX/TSX: run-libs.js (5 MB, loaded on the first Lancer, `window.CEV_RUN_LIBS`) is
  posted to the frame, which makes blob: URLs and an import map (one React: `cev-react-all`; react,
  react-dom(/client), jsx-runtime, recharts 2.15, lucide-react, lodash (+ `lodash/<name>`), d3, `cev-tailwind`
  (Tailwind 4 compiling the classes found, with the Tailwind 3 defaults), TypeScript translating JSX + types);
  `@/components/ui/*` get shadcn stand-ins (STUBS); packages downloaded come from
  `https://esm.sh/<name>?external=react,react-dom` (not run here: no network); project files (`./`, `@/`) can
  never be had. **`esm_cache.py`** (PT-m3, 08/11): served, those packages are downloaded ONCE after `CEV.confirm` (`web.run.keep_esm`,
  run.js `withPackages`, POST `/__cev__/esm` {specs}, token): from `entry_url` (`?external=react,react-dom&target=es2022`)
  every module reached (`_IMPORT`: from / import / import() / export … from; paths `/`, `./`, `../` or https://esm.sh/
  written out as full addresses, bare names left to CEV; ≤ 400 modules, 40 MB) into `archive/esm/` (index.json
  {spec: {entry, modules, size, date}}), written to the site as `esm-cache.js` (`window.CEV_ESM`, at each build and after
  each download); the runner maps each module address to a blob and the name to its entry: no Internet (CSP closed),
  also opened as a file. A failure is said once (`data-keep-failed`, then the Internet for that run only, asked).
  Tests: tests/test_esm_cache.py (a stand-in for esm.sh: real esm.sh never reached here, not checked). Visuals: claude.ai's design tokens (`widgetCss`: surfaces, text, borders, roles, `c-{ramp}`
  SVG classes, t / ts / th, pre-styled controls; values by guess) light or dark after the page theme,
  `sendPrompt` / `openLink` do nothing, height fitted to the content (postMessage `cevHeight`); Tabler icons
  absent. The bubble holding a program takes the whole width. A visual has a link "html": the file the user
  saved from the chat, named `<title>.html` by claude.ai (`userfiles.widget_file`, link kind "widget", found
  like the other files, 🔗 to change it; "html ?" when none); with one, Lancer runs that very file: its text is held in
  the page (`<script type="application/octet-stream" class="cev-saved">`, base64) and run as srcdoc with the
  CSP of the frame and the height reporter put first in its <head> (`savedDoc`).
  **`cdn_cache.py`**: the scripts and style sheets a visual or an HTML page loads from https (Chart.js from
  cdnjs, the Tabler icons from jsdelivr…) are downloaded ONCE with the user's agreement ("Les télécharger
  une fois et les garder dans l'archive", POST `/__cev__/cdn` {urls}, token; https only) into `archive/cdn/`
  (index.json {url: {file, type, size, date}}; a style sheet keeps its woff2 fonts as data: URIs, other
  formats dropped) and written to the site as `cdn-cache.js` (`window.CEV_CDN` {url: text}, at each build
  and after each download): run.js (`withLibraries`) puts them inline in the frame, so that every page using
  the same address runs without asking and without the Internet (CSP closed), also opened as a file. Without
  the server, or for images / frames / JSX packages (esm.sh): the Internet for that run only, asked each time. A
  download that fails is said once in the strip (`web.run.keep_failed`, the reason per address; 404 = a server
  of an older program still running, `web.run.old_server`), never followed by a second question; the next
  click asks for that run only (`data-keep-failed`). **`widget_host.py`**: such a saved file is claude.ai's
  page (`<html data-saved>`, its whole style sheet in the first <style>, the code in `#vis-container`): the
  sheet is learnt from it (most recent) into `archive/claude-widget.css` — Anthropic's, never shipped — and
  written to the site as `claude-widget.js` (`window.CEV_WIDGET_CSS`, empty when none): run.js then draws every
  visual inside it (data-mode light / dark), else with `widgetCss`. run-libs.js is built by
  `tools/build_run_libs.mjs` from local packages and git clones (see its header; licences:
  `static/run-libs-LICENSES.txt`). Tests: tests/test_run_browser.py (isolation checked through the CSP
  violation events, the network being absent here anyway).
- **`math_plugin.py`** — mistune plugin protecting `$…$`, `$$…$$`, `\(…\)`,
  `\[…\]` (independent of `mistune.plugins.math`); KaTeX 0.16.47 bundled in
  `static/katex/` (copied under `conversations/` so file:// font loading works)
  renders them lazily via `render.js`, and all of them before printing.
- **`markdown_export.py`** — Markdown of a conversation (main branch, other
  versions as quote blocks with italic labels; no thinking/tool calls;
  `versions=False` for the main thread only). Both variants are embedded as JSON
  in each page; `static/export.js` builds the .md file and drives the .pdf
  (browser print window) and .odt/.docx buttons. One message (PT-m1, 08/11): icon `.export-msg` (renderer, after
  `.copy-msg`) → box `dialog.cev-export-one` (end of export.js): .md .odt .docx .txt .pdf + "Annotations" (served);
  served: `/export/<page>.<fmt>?msg=<uuid>` (server `_export(message=…)` → `office_export.archived_markdown(message=…)`
  → `markdown_export.message_markdown`, file name + `message_suffix` " (message 2026-11-08 14h03)"); as a file: .md from
  the `data-md` of the copy with a head, .pdf = print with `body.print-one` / `.print-this`, the others greyed. Printing
  (one message or the whole) leaves out "Masquer les ressources" (`.view-option`) and the head frames (`.fav-list`).
  Tests: tests/test_office.py `test_one_message_exported`.
- **`office_export.py`** — .odt/.docx through Pandoc: `prepare_for_pandoc`
  splits `\text{…\textbf{…}…}` (rejected by Pandoc) and turns Markdown images
  into links (Pandoc would otherwise embed local files or fetch URLs);
  `--sandbox` is not usable with Debian's Pandoc (it cannot read its own data
  files).
- **`fetch.py`** — guided download from the manifest: finds ZIPs already
  downloaded (browser renames like `x (1).zip`, files older than the manifest
  ignored), opens missing `https://claude.ai/` links one by one, waits for
  complete downloads, moves them to `archive/exports/<date>/`.
- **`server.py`** — local server on 127.0.0.1 (`--serveur`, `--ouvrir`):
  serves the site (not the raw archive, `Cache-Control: no-cache`),
  `/export/<page>.<md|odt|docx>[?versions=0]`, the import job (POST
  `/__cev__/import`, secret token from `/__cev__/token` in `X-CEV-Token`,
  Host/Origin checks), idle shutdown. `/__cev__/ping` reports the program
  signature: a new launch stops a server running older code (`stop_outdated`)
  instead of reusing it. GET/POST `/__cev__/settings` (token required) read and
  change the downloads folder; the import job searches every folder of
  `settings.search_folders()` and takes the most recent manifest.
- **`topics.py`** + `static/topics.js` — topics chosen by the user, one per
  conversation, in `archive/topics.json` ({"topics": [...], "assign": {uuid:
  name}}); names are case-insensitive, 40 characters at most. Every build and
  every change writes `topics-data.js` (`window.CEV_TOPICS`) in the site folder,
  read by the index even as a file (read only: badges + filter). Through the
  server (POST `/__cev__/topics`, token; actions assign / rename (merges into an
  existing name) / delete / create (a topic without conversation)) each conversation gets a menu, completed only when it
  opens so that a thousand menus stay cheap; `admin.js` hands the token over with
  the `cev-admin` event, and `topics.js` sends `cev-topics` after each change so
  that the index filters again. The filter "Rubrique" is always shown ("Toutes les rubriques",
  "Sans rubrique" before any topic); through the server it ends with "Nouvelle rubrique…" (value `\u0001new`,
  never filters: the filter goes back to its previous value while a name field takes its place). The server never answers 304 (file dates have a
  one-second precision: a file rewritten within the same second would look
  unchanged).
- **`annotations.py`** + `static/favorites.js` — what the user adds to the conversations,
  in `archive/annotations.json` (one file, meant also for the notes and the highlighter):
  for now `{"favorites": {conversation uuid: {message uuid: {added, sender, date, excerpt}}}}`.
  Every build and every change writes `annotations-data.js` (`window.CEV_ANNOTATIONS`), read
  by the pages even as files (read only); POST `/__cev__/annotations` (token; `{"action":
  "favorite", "conversation", "message", "on"}`, the message must be in the archive, extra
  messages included). Each `.message` has `data-uuid`, a star after its date; a favorite gets
  `cev-fav` (neon frame: `--fav-human` / `--fav-assistant`, green in light, vivid tint of each
  frame in dark; a favorite is never skipped by `content-visibility`, which would cut the
  halo). Each page has the frame "Favoris (n)" (`#fav-list`, under the export buttons, shown even
  at 0) listing them; the index shows their number in the line of each conversation (`.fav-count`,
  none at 0); `page.html#msg=<uuid>` shows a message.
- **`searchdata.py`** + `static/search.js` — the text of every conversation for the search in the content,
  taken from the pages themselves, kept ONCE (point 22, big archives) in parts of about `PART_SIZE` (100)
  conversations in the site folder: `search/pNNN.js` (`CEV_SEARCH_PART({page key: {t, m}})`), a conversation
  in the part its uuid hashes to (modulo a power of two: the parts are spread again only when the archive
  doubles), `search/index.json` (the keys of each part, for the program) and `search/index.js` (the list of
  the parts, for the browser). The page signature of each conversation's data is in the archive meta
  (`search`): a launch with nothing changed reads and writes no part; a page generated again loads and
  writes only its part; the builder handles the conversations part by part (`Store.focus`: one part in
  memory, even for a full rebuild). The earlier storage (`archive/search.json` + `search-data.js`, the whole
  text twice) is moved into parts once, without generating the pages again, then removed. The browser reads
  the parts one after the other (one at a time), shows the results as they come ("Recherche en cours…"),
  keeps the parts read up to 40 million characters (`window.CEV_SEARCH_KEEP` for the tests), beyond: read
  again at the next search. Measured on 1000 conversations of 30 messages (tests/test_big_archive.py,
  timings by hand): a launch with nothing changed 0.5 s and 50 MB of RAM (1.0 s and 150 MB before),
  36 MB of search data on disk (70 MB before).
- **Index filters** (inline script of `index.html.j2`): titles, content (`search.js`; both boxes on one row,
  half and half, `.filter-searches`, 08/11), user,
  project, deleted, topic, period (`#filter-period`: 7 / 30 days, this / last month, this / last
  year, "Du … au …" with two date fields, end day included), all combined. A conversation is in a
  period when created before its end and last exchange after its start (overlap, local days).
  Filters kept in sessionStorage, the order in localStorage.
- **`backup.py`** — the whole site folder in one dated ZIP `<site>-YYYY-MM-DD.zip` (" (2)"…),
  written under a temporary name then renamed, in the downloads folder chosen on the index else
  the system's, never inside the site folder; files already compressed are stored. Button
  "Sauvegarder" of the index (server job `/__cev__/backup`, so never during an import; the page
  is not reloaded at the end) and `--sauvegarder`.
- **`drop.py`** + end of `static/admin.js` — manifest and/or export ZIPs dropped anywhere on the
  index (a veil while dragging; as a file, the veil says to use the desktop icon). Each file goes
  in 4 MB pieces (POST `/__cev__/upload?id&name&offset[&last&mtime]`, token, refused during a job)
  to `archive/depot/<id>/` (temporary name, then the original file date: the "ZIP older than the
  manifest" rule still holds); POST `/__cev__/import-dropped` starts the job: a manifest and the
  ZIPs it lists go to its export folder and the usual guided import runs (other ZIPs left out);
  ZIPs alone go to `archive/exports/depot-<time>/` and are imported as one export, refused when
  the same name appears twice (`x.zip`, `x (1).zip`: exports mixed); two manifests refused.
  Staging removed at the end and at server start; left out of the backup.
- **`tokens.py`** — rough evaluation ("évaluation grossière", never "approximation") of the tokens
  a conversation made claude.ai use: 3.5 characters a token; each reply reads again its
  ancestors (other versions count), once more after each tool result; written = text, thinking,
  tool calls. Without claude.ai's instructions, images, project files, caching: rather a
  minimum, an order of magnitude to compare conversations. Stored in the archive meta
  (`tokens`: {v, content, tools, total}), shown short (`i18n.Tokens`, `$tok` in the pages:
  850, 4,2 k, 480 k, 1,4 M) on each line of the index and on the page, after the messages.
- **Frames of the data frame** (`admin.js`): each button opens its frame at the bottom (topics, the log of
  import / search / backup / drop, unused files), closed only by its cross or a second click on its button,
  never automatically (11/11: the reload after a job that changed the site — "Rechercher maintenant"… — opens again
  the frames of topics and cleaning that were open, `REOPEN` + sessionStorage `cev-reopen`); a job ends with "✓ Opération terminée." (`web.admin.finished`; `web.admin.done` when
  the site changed: the index is reloaded when the frame is closed). The button of the job shown is marked.
- **`static/dashboard.js`** — index layout: small titles above the frames ("Vue d'ensemble",
  "Gestion des données", "Filtres"), version top left; `.fold-head[data-fold]` lines fold their
  element (arrow onto a line, tooltip, state in localStorage `cev-fold-<id>`, folded by default):
  the overview (one line; unfolded: 5 tiles (11/11: messages "≈ n en moyenne par conversation", tokens without the 30 days line nor the note under the tiles) — the 4th: size of the site and date of the last backup ZIP found in the backup folder (`backup.site_size`, `last_backup`), updated after a backup (`cev-backup`); the size is measured again by the server when the index opens through it and after a cleaning (`site_size` of GET `/__cev__/settings` and POST `/__cev__/orphans`, event `cev-site-size`) — and the conversations active each week over 52 weeks,
  "<" / ">" move them by 26 weeks down to the oldest conversation, a click on a bar sets the period
  filter on that week) and the data frame (folded: one line summing up the folders; unfolded:
  the buttons, "Sauvegarder <site folder>", and the folders). The drop hint follows the title, in
  normal size, **manifest.json** in bold, in red when nothing is imported yet (first launch).
- **`settings.py`** — `archive/settings.json`: the downloads folder chosen by
  the user (index page, `--telechargements`), searched before the system's;
  ignored when it no longer exists (USB key removed).
- **`system.py`** — what differs between Linux, macOS and Windows: `py` vs
  `python3` and quoting of the commands shown in the pages, `python.exe` for
  child processes even under `pythonw.exe`, `CREATE_NO_WINDOW`, console output
  that never stops on an unknown character, Windows shell folders from the
  registry, install hints for the libraries and Pandoc. Windows support has not
  been run on Windows; `tests/test_windows.py` simulates it on Linux.
- **`desktop.py`** — launcher "Bibliothèque Claude" (`--installer-icone`; "Archives Claude" until 14/11):
  freedesktop entry on Linux; on Windows, `.lnk` shortcuts (Start menu, desktop)
  written by PowerShell/WScript.Shell with values passed in environment
  variables, target `pythonw.exe`, icon `static/icon.ico` (rendered from
  `icon.svg`).
- **`static/nav.js`** — the right column (`_page_nav.html.j2`): scrolling (wheel over ▶:
  speed), top / middle / bottom; always shown, even on short pages (class `short`): the theme
  (system → light → dark, localStorage `cev-theme`, set in the page head before drawing; the
  dark CSS exists twice: `prefers-color-scheme` unless `data-theme="light"`, and
  `data-theme="dark"`) and the background music (Web Audio only, volume level
  `cev-music-volume`, wheel or + / − over ♪). `msg.js`: the search bar of a page (editable,
  closed and opened again by the magnifier). Approximate search (AE-m1, 08/11): `CEVQuery.counter` "Tolérance ◂ n ▸"
  (0–2 since 08/11 evening, localStorage `cev-fuzzy`, shared by the index — beside `#content-search`, the number under
  its label — and the pages — second line of the bar; its buttons never close the bar —, the index links add `&f=n`); `CEVQuery.fuzzy(terms, wordsOf(text), n)` adds to each plain word the words of
  the text at a Levenshtein distance ≤ `allowed(len, n)` (< 4 letters: 0, 4–6: 1, else n; compound words and their
  parts); "Aussi trouvé : …": on the index only as tooltip of the box and of the counter (dotted label), on a page on the
  second line (`.hit-also`, cut, tooltip). The index boxes and lists have one height (2.25rem). `scrollTo` keeps aiming
  1.5 s after arriving (formulas and messages drawn late above moved the passage), and stops as soon as the passages go
  away (`clear`: bar closed, new search; the page went up by itself on closing). Tests: tests/test_search_content.py
  `test_approximate_search`.
- **`static/plan.js`** + `static/plan.css` — the plan view of a conversation (AE-c1, maquette B3 v2, steps 1
  and 2, 02/11), beside the reading view, which is left unchanged (everything of the plan is under
  `html.cev-plan`, on screen only: printing keeps the reading view). Bar `#plan-bar` above the messages: the
  switch "Vue : Lecture · Plan · Structure" (alone in the reading and structure views), "Lignes : 1 · 3 · 5 · Tout" (`html[data-plan-lines]`),
  "Montrer : début · surlignages" (the charter, 11/11: every chip "Titre : a · b · c" — Vue, Lignes, Montrer, Ordre — a click on
  a value chooses it, on the title or a dot the next one), "Branches non suivies repliées" (opens / folds every `details.removed-part`); kept in localStorage
  (`cev-view`, `cev-plan-lines`, `cev-plan-fold`, `cev-plan-show`, folded chapters `cev-plan-chap:<uuid>`) and the
  first two set on <html> by the head of the page before drawing.
  "Hide Claude's answers" is the button of the right column (fold.js). The plan works on the same `.message`
  elements (favorites, notes, highlighter, code frames, programs, exports, right column, keys stay), built
  once when first shown: depth `--d` (the followed thread stays at its depth, each other branch one step to
  the right; indent and thin lines up to 4 levels), `.plan-fork` "◆ n versions", `.plan-vt` "version i/n ·
  suivie" and `.plan-vlabel` in the summary of each other branch (numbered by the date of their first
  message); `.plan-sep` (a thin line above) on your message following an answer of Claude, or on the fork
  of such messages — a reply `.cev-cut` does not end a block. Each entry: a bar (blue / grey, halo of a
  favorite `--fav-human` / `--plan-fav-a`, grey in dark), flex `order`: the icons `.message-time` on top
  (always shown, brick under the mouse; speaker and date hidden): on the left `.plan-icons`, what the bubble
  holds (`holds()`: attachments, files / artifacts created, runnable programs, formulas, thinking, cut reply;
  a click opens the bubble), on the right the actions (`.plan-add-title` "T" and the note icon only while
  there is none) and last `.plan-dn` (arrow of the frames "Favoris"; class `plan-flip`: the reverse of the
  setting); then the title `.cev-title` (`.plan-tri`, `.plan-title-text`, `.plan-chap-info`), the bubble, the
  note (green bars, window background). Titles are chapters: the triangle folds the following siblings up to
  the next titled entry of the same thread (a fork whose followed entry is titled belongs to it):
  `plan-chap-closed` (one grey line "Titre · n entrées" with the icons summed), `plan-chap-hidden`.
  An entry is cut with -webkit-line-clamp on its bubble, showing only `.content-text` without code, tables,
  images (`plan-notext`: a bubble without text shows the rest, cut at the same height); `plan-cut` (measured:
  the text goes beyond) fades its last line from 2 lines (overlay `::after`, not a mask: the blue background
  stays). `place()`: a cut bubble holding the current passage found, another passage found or (with
  "surlignages") a highlighted passage becomes a window (`plan-at`: block, max-height of n lines, scrollTop on
  that line; `plan-above`: a top fade; the fades are sticky); `.plan-tick`: a brick mark on the bar at the
  height of a passage found. msg.js sends `cev-hits` {marks, current} after each search / step; a current
  passage in a folded chapter opens it, one not drawn (code of a cut bubble) opens the bubble.
  `.plan-strip`: markers (favorite, note, passage found) proportional to the page, left of `#page-nav`, only the
  markers take the mouse; redrawn (`refresh`, 60 ms) after a ResizeObserver on the messages, a toggle, the
  annotations, the search. Title = annotation "titles" (one line; Enter or leaving the field saves, Escape cancels;
  in every view since 04/11: `titleButton` "T" after the star of each message, `.cev-title` above the bubble with
  a green bar, flex order time / title / bubble / note; printed with "Annotations"). Frame `#title-list` "Titres (n)"
  of the head (as "Notes (n)", `paintList`): the titles in the order of the page, a cross (served) removes one.
  "Lignes" in the reading and the structure too (07/11): their own setting `html[data-read-lines]` /
  `cev-read-lines` (default Tout; the plan keeps `data-plan-lines`), chip shown in every view; `html.cev-read-cut`
  (head and `readCut()`) applies the same clamp rules (fade on the colour of each bubble, `overflow-clip-margin:
  content-box`), `.plan-icons` after the date and `.plan-dn` (only with `plan-cut`, `plan-flip` or `plan-more` =
  something beside the text); `prepare()` runs for every entry at load; `plan-flip` is cleared on a change of
  view; a passage found in a cut bubble of the reading opens it. Tests: tests/test_plan.py.
- **`static/structure.js`** (styles at the end of `plan.css`) — the structure view (AE-c1, maquettes « Structure »
  of 03/11), third choice of the switch "Lecture · Plan · Structure" (`cev-view` = structure, `html.cev-structure`
  set in the head; plan.js `view()` calls `CEV.structure.show()`; the messages are hidden, `.st-panel` is put
  before them). Read from the page (messages and `details.removed-part` frames): a drawing (SVG) where the
  followed thread is one continuous line, every other version a dotted line in a lane below; column = rank in
  the thread (the versions of one question or answer in one column); the branches leaving one branch are
  placed from the one leaving furthest right (nearest lane) to the furthest left, each followed by its own
  branches, so that the lines do not cross (usual cases, not proved). Questions: blue circles (filled on the
  followed thread), answers: small empty grey circles. Numbers: followed thread 1, 2…; a branch leaving after
  question k of its thread (0 before the first) is k.1, k.2… in the order of time, its questions k.b.1…, except
  a branch starting with a question, which takes the number of the branch. Under the drawing the list: one
  line per question (its title in bold, else the start of its text) and per other answer of Claude, shifted by
  level. The mouse over a point or a line: its date as tooltip (the `<time>` of the message), the point and the
  line lit together (`st-hi`). A click (`choose`): under the list, after `hr.st-sep`, as in the reading view, the
  question with its answer — on a question its answer on the same thread (`after`), on an answer its question
  (`before`, out of the frame); the other answers of that question in their frames, folded (`st-alt`). These are
  the messages of the page themselves (`st-shown`; frames on the way `details.st-path` opened, summary and frame
  hidden; every other message hidden; `html.st-has`), so that everything of the reading view works on them;
  the point and line chosen `st-sel`; a double click (`stretch`): from that question to the end of its branch, in
  the order shown. The list is drawn again after each change of the annotations (titles, moves, links).
  A click shows the question with ALL its answers (consecutive ones too, as an interrupted answer and its
  continuation; 07/11). "Ordre : réel · logique" (localStorage `cev-struct-order`): the logical order applies the
  annotations "moves" {conv: {question: {to, how: under | after | cut, bend}}} (`logical`; under: the question and
  all that follows it on its thread becomes a frame just before its target question, i.e. another version of it;
  after: dropped on an answer, it goes on after that answer, what followed it becomes a branch `pushed` in the lowest
  lane — after its real parent answer = back in place, removed; cut: "✂" on the line coming to a question (shown
  under the mouse) makes it and what follows an independent subject, lowest lane, no line; 11/11: ✂ also on the line of a
  question moved (its move becomes a cut); a part moved under the first question of a cut part is cut too (`owner`, no line
  from the answer before); `lead` = the first message of a part moved / pushed / cut, whose line is its curve or none even
  when other versions come before it; a cut part is at the left of the list, depth 0); a move under what
  follows itself is refused, `under`; connectors are curves from the real parent answer, every thick line and green
  link has a handle in the middle (drag = `bend`, along the normal; double click = automatic); "↶ Annuler" (action
  undo_structure, `structure_history` of 10 snapshots in annotations.json, its length in annotations-data.js);
  numbers stay those of the actual order (`labels`); a moved part takes the lowest lane, drawn thick (`solid`,
  filled questions, a thick vertical line in its column, the moved question ringed `st-moved`), listed right
  under its target with "déplacée sous n" and "↺" (back in place). Drag (pointer events, served only): a question
  onto a question (logical order) = a move; Shift + drag from a point to another = a logical link (annotations
  "relations" [{a, b, dir: to | back | both}], one per pair; green curve bent to the right `st-rel`, arrows after
  `dir`, a click on `st-rel-hit`: to → back → both → removed), drawn in both orders, written at the end of the
  lines ("→ 4", "← R3"…). "Réinitialisation" (`CEV.confirm`): action reset_structure. Server: annotations.py
  `_change_structure` (actions move / relation / bend / reset_structure / undo_structure). Tests: tests/test_plan.py (`_alpha_site`, the shape of the user's test thread).
- **`speech.py`** + `static/speak.js` — reading a bubble aloud (07/11) with Piper (piper1-gpl, GPL-3: never
  shipped nor imported, run as a separate program, so CEV stays MIT). Folder (settings.json "speech" "dir"), by
  default `~/.local/share/cev-piper` (Windows `%LOCALAPPDATA%\cev-piper`): `env/` (or `bin/` at the top: made by
  hand) and `voices/` (or the top). Installed by CEV after a yes (POST /__cev__/speak/install, a thread, its state
  in /speak/status "job"): venv from `sys.executable` (Debian without python3-venv: `--without-pip` + get-pip.py),
  `pip install --upgrade piper-tts[http(,ja)]`, the voices of the pair; `installed()` = piper + flask (+ pyopenjtalk
  for ja); otherwise `manual_command()`. Voices downloaded when first needed (`download`, piper.download_voices
  --data-dir voices/). `_Piper`: one `piper.http_server` (127.0.0.1, free port, every data dir) kept running,
  POST /synthesize {text, voice, speaker}, stopped after IDLE (600 s) without use and at exit; /speak/warm (under
  the mouse) downloads the two voices and starts it. The voices (07/11): `catalog()` =
  voices.json of piper-voices (kept a week in the cache folder), `choices(lang)` the best quality of each voice, each
  speaker of a voice with ≤ MANY (8) one choice, more = one choice with "speakers" (picked by number), the sex from
  the speaker's name or `SEX`, else "?", sample = the mp3 of rhasspy.github.io/piper-samples; `listed()` adds the
  voices in use; `voices(lang)` = settings.json "speech" "voices" {lang: {human, assistant}} (`choose`, checked by
  `VOICE`) else `DEFAULTS`; a voice is "name" or "name#speaker" (checked in the .onnx.json); `single()` (same voice
  for both: "Question." / "Réponse." said first). WAV kept out of the site (08/11) in `cache_dir()` = ~/.cache/cev-speech
  (XDG_CACHE_HOME; Windows %LOCALAPPDATA%\cev-speech; sha256 of voice + text), at most settings.json "speech" "cache_mb"
  (default 100, at least 50); the old archive/speech/ is removed by the CLI (`drop_old_cache`); the cleaning frame of the
  index shows them (POST /__cev__/speech-cache {action: state | clear | size, mb}; admin.js `soundsSection`: size,
  largest size, "Effacer les sons" after CEV.confirm; greyed with the normal cursor when there is nothing to delete). Tests: each has its own XDG_CACHE_HOME (tests/conftest.py). POST /__cev__/speak {text, lang, role, cached_only} (token) → audio/wav, 204, or 503 with the
  message; /speak/status, /warm, /install, /voices, /choose (JSON). speak.js (served only): loudspeaker `.cev-speak` after the other icons (before `.plan-dn`; none
  without text); `words()`: every `.content-text` of the bubble (not the files / resources between them), without code / tables /
  formulas (named), a list of links (the sources; with its short title ending in ":") said once
  `web.speak.sources`, a written address = `web.speak.link`, a final mark added to each line; `pieces()`:
  whole sentences, at most 120 / 200 / 300 / 400 characters; `read(msgs, all)` reads bubbles in a row; the
  round button `data-go="speak"` of the page (nav, under Back | Next now one round button cut in two `.nav-pair`)
  reads every bubble shown from the first one on the screen, each scrolled into view, aria-pressed, a second click
  stops; with the slow scrolling of nav.js on, the scrolling follows the reading (`parse()` marks where each
  part of the text comes from {pos, el}, `split()` gives each piece its start, `CEV.speak.target()` = the line read
  from the time of the sound, a third down the screen; nav.js goes there smoothly instead of its speed; wheel,
  keys, touch or scroll bar then stop the scrolling, the reading goes on; `CEV.scrolling()`); the speak buttons do
  not stop the scrolling (KEEP); speeds 6 / 9 / 12 … 150 px/s (localStorage `cev-scroll-level`, the old
  `cev-scroll-speed` + 2); chip `.cev-voices` "Voix" in the bar → box `.cev-voice-box`: a list per speaker (optgroups ♀ /
  ♂ / others, a number for a voice with many speakers, ▶ Écouter = the sample, the note downloaded or its size),
  saved at once (/speak/choose); a speed 0.75–1.5 for each voice, under its menu (14/11; localStorage `cev-speak-rate-human` /
  `-assistant`, else the former `cev-speak-rate`; `playbackRate`, pitch kept). The box has a fixed width (`.cev-voice-box`).
  Languages (08/11): `segments()` gives each line of the text read the language `detect()` finds (script for ru / ja / ko /
  zh; frequent words of each Latin language, a word shared by k languages counting 1/k, a few letters; ≥ 4 words, best
  ≥ 1.5 and ≥ 1.5 × the second; 08/11 evening: words of 2 letters or more, the labels of CEV taken out, no one-letter stop
  word — the variables a, e, o, i of the formulas made Portuguese —, ≥ 5 words, best ≥ 2 and ≥ 2 × the second, and another
  language than CEV's only with ≥ 3 and ≥ 20 % of its words and CEV's score ≤ a third), else the one of the line before; the lines CEV adds (`isLabel`: "Bloc de code."…) stay
  in the language of CEV. `prepare()` asks /speak/check {langs} (speech.check: readable, skip, missing voices with their
  size) and `CEV.confirm` (now with an onNo) for a voice to download (Non: not read this time); `build()`: an announcement
  `web.speak.passage` in the voice of CEV when a foreign run starts (once while it lasts, labels between do not end it),
  `web.speak.passage_skip` and nothing else for a language skipped, a pause item of 1 s when the language of CEV comes back,
  pauses of 450 ms around a line CEV announces (code block, table, formula alone); the icons Claude writes are not said
  (`unicons`: Extended_Pictographic, flags, skin tones, variation selectors; "lecture. 🎯." → "lecture.");
  each piece is asked with its `lang` (its voice). Box "Voix": a select of the 12 languages (`open(lang)`), "Ne pas lire
  les passages en …" (/speak/skip {lang, on}: settings.json "speech" "skip"), and a `<details>` of the voices installed
  (/speak/installed: speech.installed_voices — every .onnx of voice_dirs, size, `duplicate` (same name in two folders),
  `used`; 🗑 → /speak/remove {name, dir index} after CEV.confirm, Piper stopped first). Tests: tests/test_speak.py
  `test_languages_and_voices_installed`, `test_passage_in_another_language`.
  Tests: tests/test_speak.py (a stand-in for Piper: pip, download_voices, http_server).
- **`extras.py`** + `templates/extras.html.j2` + `static/extras.js` — the other data of the export (11/11), read from the
  ZIPs kept in `archive/exports/<date>/` (shapes in the module docstring, seen on the user's export of 23/10): the memory
  (`memory_versions`: one version per export where it changed; page `extras/memory.html`, a select of the versions and
  "Comparer avec la précédente" = `diff_html`, lines added `ins.ex-add` / removed `del.ex-del`), the reflections
  (`reflections.html`), the Claude Design chats (`design.html` + `design-<uuid>.html`: bubbles, your attachments folded,
  the tools Claude Design used folded `.ex-tools`; the text of a message is `content.content`, `_text_of` is tolerant,
  else the raw JSON), the artifacts of "frames" (`artifacts.html`: versions, boards of `project/canvas.json`, size;
  "Ouvrir" → POST `/__cev__/artifact` {id, version} → `extract` (once, into `extras/artifacts/<id>/<version>/`, paths
  checked by `_safe_path`, ≤ 300 MB) → `artifact_server(folder)`: ONE small server per version opened (its folder at the
  root: the application asks "/…" paths), another port = another origin (no access to the site, its storage, its
  token), CSP without the Internet, Host checked; the page opens it in a new tab). The data are merged over the exports
  (the latest wins). `html_builder.write_extras` writes the pages at each index (stale ones removed) and gives the index
  (`extras.summary`) one line at the end of the unfolded data frame (11/11, served only, as the whole frame):
  "Autres données importées de claude.ai : Mémoire : n fichiers · Bilans : n · Discussions Claude Design : n ·
  Artefacts : n", each name a link to its page, the empty ones left out. A category CEV does not know (a split ZIP
  `<category>-000.zip` of a name not in `extras.KNOWN`: scheduled tasks, Claude Code… whatever claude.ai adds;
  the old single ZIP `data-….zip` is not one) is found by itself (`other_categories`, latest export holding it)
  and shown as it is on `other-<category>.html` (each file folded, JSON indented, cut at 200 000 characters). The versions extracted are left out of the backup
  (`clear_extracted` exists, not yet in the cleaning frame). Tests: tests/test_extras.py.
- **`dates.py`** — ISO parsing, UTC/local conversions.
- **`jsonfile.py`** (review of 11/11, S1) — `read(path)` for the user's JSON files of `archive/` (annotations, topics,
  settings, files): a file that cannot be read is renamed `<name>.illisible-<date>` instead of being taken as empty (the next
  change would have written over the user's work); `damaged()` gives them to the index (`web.damaged`, red line).
- **Review of 11/11 (S2–S10)**: a lone half of a character in an export is replaced (`loader._valid_text`); a POST body up to
  256 KB; the server answers only a Host 127.0.0.1 / localhost of its port (`_host_ok`, every GET / HEAD / POST: DNS
  rebinding), no folder listing, HEAD checked like GET; icons of a message always star, note, T; `CEV.alert` / `CEV.prompt`
  (confirm.js) instead of the browser's boxes; `icon.svg` as the icon of every page. Tests: tests/test_review_fixes.py.
- **First launch (P1, 11/11)**: `--ouvrir` / `--serveur` without an archive builds an empty site (`cli.first_run`) instead of
  stopping on "no export" (the icon did nothing); `--installer-icone` works before any import too. An index without
  conversation shows `#welcome` ("Pour commencer": the 3 steps to get the export, `web.welcome.*`) and hides the filters;
  served, its button "Importer" clicks `#admin-import`, and the end of a job that changed the site reloads the page.
- **Review P2–P11 (11/11)**: `install.py` + `--installer` (P2): the program folder copied whole to `~/claude-export-viewer`
  (`place_program`: the earlier version replaced through `.nouveau` / `.ancien`, never a folder without
  claude-export-viewer.py nor one holding the site), the icon (`cli._install_icon`), a Pandoc hint, then the archives opened by
  the program installed (detached `--ouvrir`; -o defaults to `~/claude_site`); the README quick start uses it, and it is the update.
  P4: icons of the line of a message 16 px, stroke 2; the indicators ∑ (formulas) and lamp (thinking) removed. P6: one name,
  `web.site_title` = `desktop.name` ("Bibliothèque Claude" since 14/11), button "Importer un export". P7 (replaced 14/11): an empty topic menu
  always shown, faded (opacity 0.5) until the mouse. P8: under 1170 px the page moves left of the right column. P9: `.st-help` "Comment réorganiser" folded under the
  Structure bar. P10: one token check for every POST (`do_POST`); i18n-data.js = the languages + a loader writing the
  `<script>` of `i18n/<lang>.js` for the language shown and English only (another one loaded when chosen in the menu).
  P11: 3 screenshots (docs/accueil.png, conversation.png, structure.png, French) at the top of the 12 READMEs.
  P3: the four frames of the head (Liens, Favoris, Notes, Titres) are tabs on one line (`.fav-tabs`: details in
  `display: contents`, summaries as tabs, `::details-content` under them), one open at a time (end of favorites.js).
  CLI (11/11 afternoon): `-o` defaults to `~/claude_site` (was `site/` in the current folder); no abbreviation of the options
  (`allow_abbrev=False`: an older program took `--installer` for `--installer-icone`); a launch with no archive and nothing
  asked opens the welcome as `--ouvrir` does.
- **`i18n.py`** + `i18n/<lang>.json` + `static/i18n.js` — every visible text
  is a key (`cli.*` console, `warn.*`, `fetch.*`, `server.*`, `office.*`,
  `web.*` pages, `md.*` Markdown labels, `fmt.*` date/number patterns; plural
  texts are objects of CLDR categories). English is the reference and fallback.
  The console uses the system language (`CEV_LANG`, `LANGUAGE`, `LC_ALL`,
  `LC_MESSAGES`, `LANG`) or `--langue`. Pages are written in that language with
  each text marked (`data-i18n`, `data-i18n-args`, `data-i18n-attr`, `data-i18n-rich`
  for a text with the markers `[v]…[/v]` (verb) and `[b]…[/b]` (bold), see `i18n.rich`,
  `<time data-fmt>`); `i18n.js` rewrites them in the language chosen in the
  index menu (localStorage `cev-lang`), else the browser's, else English, using
  `i18n-data.js` (texts `web.`/`md.`/`fmt.` of every language, written in the
  site folder). The embedded Markdown holds markers ⟦cev:key:{args}⟧ resolved
  by the browser; the server receives the page language (`X-CEV-Lang`,
  `?lang=`) for the import job (env `CEV_LANG` of the subprocess) and the
  .odt/.docx exports. Python (`plural_category`) and the browser
  (`Intl.PluralRules`) agree on plural forms for 0–1000 in all 12 languages.
  Tests run in French (`tests/__init__.py` sets `CEV_LANG=fr`).

## Running the tests

`python3 -m pytest tests/` (needs pytest). All text I/O names its encoding:
`python3 -X warn_default_encoding -W error::EncodingWarning -m pytest tests/`
must pass (with `PYTHONWARNDEFAULTENCODING=1` to check subprocesses too).

## Claude.ai data export

The e-mail link downloads a small manifest JSON (`created_at`, `data_files`:
`category`, `filename`, `export_url`). Each ZIP link works only in a browser
signed in to claude.ai and expires after 24 hours. Categories seen:
`conversations` (`conversations.json`), `projects` (`projects/<uuid>.json`),
`light_metadata` (`users.json`…), `memories`, `feedback`, `design_chats`,
`frames`. All are downloaded and kept in `archive/exports/<date>/` (08/11; before, only the first three
without `--tout`, now hidden and without effect); conversations, projects (names) and users make the site, the others
are shown read-only by `extras.py` (11/11).

### conversations.json

```json
[
  {
    "uuid": "string (required)",
    "name": "string (optional, default '')",
    "summary": "string (optional, default '')",
    "created_at": "ISO 8601 datetime | null (optional)",
    "updated_at": "ISO 8601 datetime | null (optional)",
    "account": {"uuid": "string"} | null,
    "project_uuid": "string | null (optional)",
    "chat_messages": ["ChatMessage (see below, default [])"]
  }
]
```

### ChatMessage

```json
{
  "uuid": "string (required)",
  "text": "string (optional, default '')",
  "content": ["ContentBlock (see below, default [])"],
  "sender": "'human' | 'assistant' (required)",
  "created_at": "ISO 8601 datetime | null (optional)",
  "updated_at": "ISO 8601 datetime | null (optional)",
  "attachments": [
    {
      "file_name": "string (default '')",
      "file_size": "int bytes (default 0)",
      "file_type": "string (default '')",
      "extracted_content": "string (default '')"
    }
  ],
  "files": [
    {
      "file_name": "string (default '')"
    }
  ]
}
```

Note: `text` is a flattened plaintext version of the message. `content` is the structured block array used for rendering.

### Content Blocks

Discriminated union on the `type` field. A message's `content` array can contain any mix of these.

#### type: "text"

```json
{
  "type": "text",
  "text": "string (default '')",
  "citations": ["object (default [])"]
}
```

#### type: "thinking"

```json
{
  "type": "thinking",
  "thinking": "string (default '')",
  "summaries": [
    {"summary": "string (default '')"}
  ],
  "cut_off": "bool (default false)",
  "alternative_display_type": "string | null (optional)"
}
```

**Quirk**: `summaries` is an array of `{summary: string}` objects, not plain strings.
Recent exports have an empty `thinking` and only the summaries: the page then shows the list of
summaries, titled by the last one, as claude.ai does.

#### type: "tool_use"

```json
{
  "type": "tool_use",
  "id": "string | null (optional)",
  "name": "string (default '')",
  "input": "object (default {})",
  "message": "string | null (optional)",
  "integration_name": "string | null (optional)",
  "display_content": "string | object | null (optional)"
}
```

When `name` is `"artifacts"`, the `input` object is an artifact descriptor:

```json
{
  "command": "'create' | 'update' | 'rewrite' (default 'create')",
  "id": "string (default '')",
  "type": "string | null (artifact MIME type)",
  "title": "string | null",
  "language": "string | null (programming language)",
  "content": "string | null (full content for create/rewrite)",
  "old_str": "string | null (for update command)",
  "new_str": "string | null (for update command)",
  "version_uuid": "string | null"
}
```

**Artifact MIME types observed**: `text/markdown`, `text/html`, `application/vnd.ant.code`, `application/vnd.ant.react`, `application/vnd.ant.mermaid`, `image/svg+xml`

**Artifact commands**:

- `create` — New artifact. Has `content`, `type`, `title`, `language`.
- `rewrite` — Full replacement. Same fields as `create`.
- `update` — Partial edit. Has `old_str` and `new_str` instead of `content`.

`rewrite` / `update` may hold only `id` and `content` (no `type`, `title`, `language`):
`tree.items_from_raw` gives them those of the earlier blocks with the same id.

#### type: "tool_result"

```json
{
  "type": "tool_result",
  "tool_use_id": "string | null (optional, links to tool_use.id)",
  "name": "string (default '')",
  "content": "string | [{type: 'text', text: string}] | null (any)",
  "is_error": "bool (default false)",
  "structured_content": "object | null (optional)",
  "message": "string | null (optional)",
  "integration_name": "string | null (optional)",
  "display_content": "string | object | null (optional)"
}
```

**Quirk**: `content` can be a plain string, a list of `{type, text}` objects, `null`, or other structures. The renderer handles string and list-of-objects forms.

#### type: "token_budget"

```json
{
  "type": "token_budget"
}
```

Marker block with no data. Skipped during rendering.

### Known Quirks and Edge Cases

These were discovered by validating against real export data:

- `ThinkingContent.summaries` contains `[{summary: str}]` objects, not plain strings
- `ToolUseContent.id` and `ToolResultContent.tool_use_id` can be `None`
- `display_content` on both tool_use and tool_result can be either a string or a dict (rich_link objects like `{type: "rich_link", link: {url: "..."}}`)
- Artifact `input` has `command` field: `create` has full content, `update` has `old_str`/`new_str`, `rewrite` has full content
- Artifact types seen: `text/markdown`, `text/html`, `application/vnd.ant.code`, `application/vnd.ant.react`, `application/vnd.ant.mermaid`, `image/svg+xml`
- `ToolResultContent.content` can be a string, a list of `{type, text}` objects, or `null`
- `project_uuid` and `account` on conversations are both optional/nullable
- `ChatMessage.text` and `ChatMessage.content` coexist — `text` is a flattened plaintext form, `content` is the structured block array
- ZIP files may have JSON files in subdirectories; the loader classifies files by name (and folder)
- Missing files are treated as empty (partial exports are valid)
- `parent_message_uuid` links every message to its parent; the root sentinel is
  `00000000-0000-4000-8000-000000000000`. Edits and retries are sibling branches, all kept in the export
- Block types beyond the ones above appear: `document` (only a file uuid: content not exported),
  `injected_prompt_block` (`prompt`, `injection_source`: instructions added by claude.ai), images,
  web search blocks… They become `UnknownContent` and are shown generically
- Deleted conversations may stay in the export, empty or with leftovers only (an attachment, an empty
  reply): a conversation counts only if some `text` block has text
- Dates stored in the ZIP are 1980-01-01: the export date comes from the manifest (or the data)
- The user's text is shown as typed (no Markdown, no formulas, as on claude.ai); exports keep it
  through `markdown_export.typed` (punctuation escaped, hard line breaks), the copy gives the raw text; a line
  starting a list item ("1.", "2)", "-", "*", "•", indented or not) gets a hanging indent as on claude.ai
  (`renderer._plain_lists`: `.li-line`, its marker in a box `.li-mark` as wide as the indent, its newline in a
  hidden `.li-nl`), the characters of the bubble staying exactly those typed
- A text pasted into claude.ai is an attachment without a name, with a nameless `files` entry: shown
  as "Texte collé", the nameless file is left out
- `injected_prompt_block`s are filed in the user's message: `tree.items_from_raw` moves them into each
  reply of Claude to it, after its opening thinking (kept in the user's message without a reply; claude.ai does not show them). The box "Masquer les ressources de
  claude.ai" (checked whenever a page opens, fold.js) hides every folding line of claude.ai in every
  message: thinking, frames "Ressources de claude.ai", the cut replies; not the user's files nor
  the files made by Claude (`body.cev-show-resources` when unchecked)
- A reply of Claude without text, holding only thinking or empty text (or nothing)
  (`html_builder._cut_reply`): interrupted by the user or where claude.ai compacted the conversation, the
  export does not tell which: its bubble keeps the thinking and ends with "Message interrompu ou
  compaction"; the whole message (`.cev-cut`) is hidden with claude.ai's resources, never an empty bubble
- Code frames of more than 10 lines (`renderer.PREVIEW_LINES`, text and artifacts; not the files of
  Claude, already folded) show their first 10 lines: class `cev-long`, triangle before the label, arrow
  of the frames "Favoris" on the right, a click on the header (not on "Copier") toggles `cev-open`
  (code.js); the search of a page opens the frame of a hit; printed whole
- Annotations (archive/annotations.json, annotations.py; changed only through the local server,
  shown read-only on a page opened as a file): favorites (favorites.js), links between
  conversations (links.js: drag on the index, both ways, never transitive), one note per message,
  yours or Claude's, under its bubble (notes.js: one written at a time, opening another one or clicking
  its icon again saves it; 11/11, the charter: a head "Note" + icons undo / redo / save / erase and a thin line, the text
  written in the colours of the note, saved by a click elsewhere (blur while the window keeps the focus), Escape cancels,
  undo by steps of typing (0.6 s), erasing a note of more than 7 s of reading (`readSeconds`, words or CJK characters
  by language) asks first — also from the cross of "Notes (n)"), one title per message (plan.js, action "title", white
  space folded; in the exports above the message, with the box "Annotations"), highlighted passages (marks.js: kept as {s, q[, c]} in the text of the
  message as marks.js reads it; 11/11: 5 colours `annotations.MARK_COLORS` y g r p c (yellow not written), `--hl-*`,
  chosen by the wheel over the button (box `.nav-hl-box` of squares, the current one ringed, localStorage `cev-hl-color`),
  the button never disabled (class `off`, grey unless selected text or the mouse); a click on passages of the colour
  chosen removes them, of another colour recolours them ("mark" with "replace"); 1 px more above and below; the exports
  stay yellow; found again by their text when they moved; the white space that only
  separates blocks, list items or table cells is never wrapped). annot.js shares the
  token, the posting and the counts of the index; confirm.js is the one confirmation box. The
  box "Annotations" of the export line puts titles, notes and highlights in the exports (Pandoc +mark only
  then; .odt: marks U+E000/U+E001 made yellow spans afterwards, office_export.odt_highlights)
- nav.js: `CEV.stopScroll()` stops the slow scrolling; a click on any control, typing or a choice
  stops it already (capture listener), except its own button, the theme and the music

## 14/11 (2026.11.14.1)
- Name: "Bibliothèque Claude" in the 12 languages (desktop.name = web.site_title; READMEs too). A Windows shortcut of the
  former name is not removed (Windows untested).
- Notes (style.css `.cev-note`): no bubble any more (a note is not part of the conversation): the colour of the window,
  a 4 px yellow bar on the side of the message (right for "Moi", mirrored) carried on by a 1 px line at the bottom to
  the grip in the other corner; text in `--note-ink` (dark ochre / pale yellow); variables `--note-bar/-ink/-soft` per
  theme. Save icon = a floppy disk. Placeholder: "Votre note… (enregistrée en cliquant ailleurs)".
- Claude's bubbles framed in `--claude-border` (soft green); `--assistant-border` stays for the other messages.
- Tabs of the page: a space between an open frame and the line under the tabs; the plan bar closer to that line.

## 14/11 (2026.11.14.2)
- Title and note set in 1rem from the bubble (right for Claude, left for "Moi"); both bars on the left (`.cev-title::before`,
  `.cev-note::before`, rounded at the top; the note's carried on by its 1 px bottom line; the grip of "Moi" stays
  bottom-left). `.cev-note-head` min-height = its tools: nothing moves when writing starts.
- The T icon (plan.js `titleButton`/`paint`) always shown when served, `.has-title` green, `readonly` otherwise (key
  `web.title.readonly`); while its title is written its click saves (`writingTitle`/`finishTitle`, mousedown kept from
  blurring). The title field is written in place (`.cev-title-edit`: no border/padding, a thin outline): no jump.
- "Masquer les notes" / "Masquer les titres" (fold.js, `body.cev-hide-notes` / `cev-hide-titles`, screen only):
  unchecked whenever a page opens; the note or T icon clicked while hidden unchecks it.

## 14/11 (2026.11.14.3)
- AF-f1: "Nettoyer les fichiers inutilisés" shows the versions of artifacts extracted (extras.extracted_state, POST
  /__cev__/artifacts-cache {"action": "state" | "clear"}, admin.js `artifactsSection`; only when there are some).
- AF-f3: `icons.py` = the drawings used in several places (cross, fold, chevron, star, note, title, link, copy,
  speaker): templates `icon(name, size, cls)`, renderer.py `icons.svg`, scripts `CEV.icon` (icons.js written with the
  site, loaded after i18n.js). Dark theme written once: the head line of base.html.j2 always sets `data-theme`
  (the saved choice, else the system's, followed by a matchMedia listener; nav.js "system" does the same), so the CSS
  has only `:root[data-theme="dark"]` rules (no `prefers-color-scheme` block any more).
- README.fr.md is the model of the README (14/11): the 11 others are to be rewritten from it later.

## 14/11 (2026.11.14.4) — the index in tabs
- index.html.j2: no count nor date under the title any more; `.index-tabs` (buttons `#tab-overview`, `#tab-data`,
  `#tab-filters`, role tab) over three panels `#overview`, `#admin-bar`, `#filter-bar` (role tabpanel). One open at a
  time, a click on the open one closes it, ← → Home End (dashboard.js `openTab`, `CEV.indexTab(name, open)`). At each
  opening: the overview; `#tab-data` comes with the server (admin.js after the token), opened when there is no
  conversation (welcome) or for the frames opened again after a reload (`cev-reopen`). The panels lose their top
  line (the tab joins them). `#result-count` stays under the tabs. "Filtres (n)": the filters set (inline script of
  the index, `#filters-n`).
- Overview: no fold, no small bars (`dash-spark`), no tile of the topics. Data: no "Dossiers" line (fold-head and
  folders-sum removed); first the frame of dashes `#admin-import` (a button: drop anywhere on the page, or a click:
  POST /__cev__/has-manifest → the import of the latest manifest of the downloads, else `#admin-files-pick`, the
  window of the system, its files taken as dropped), with the date of the latest export and how to ask one
  (`web.drop.how`, or `web.drop.how_new` once an export is imported: 2026.11.14.5).
  `web.drop.hint` replaced by `web.drop.zone` / `web.drop.how`. A drop opens the tab of the data (its log).
- "Nettoyer" (button), "Nettoyage" (its frame), tooltip naming the copies, the sounds and the artifact versions.

## 14/11 (2026.11.14.6) — AF-m1 (a): the first opening after an update
- Measured at the user's (Celeron): 84 pages made again in ~90 s after each update (the signature of the program
  changes), the browser only opened at the end. Now `--ouvrir` without an import (the icon, `--installer`) calls
  `server.serve(build=…)`: the server answers at once, the pages are made in a thread (cli `_render_site`, which
  reports (n, total)); while `ctx.building` is not done, "/" and "/index.html" are `_building_page()` (self-contained,
  texts `web.build.*` of the 12 languages inside, polls GET `/__cev__/build-state`, opens the index at the end; on an
  error: the message and a link to the former index). The browser waits 1.5 s at most: a quick build opens the index
  directly. Imports (`--manifeste`, files given) keep the former flow (build, then serve).

## 14/11 (2026.11.14.7) — AE-m11 and AF-m1 (b)
- `allexport.py` (AE-m11): `build_all` → "<site>-markdown-AAAA-MM-JJ.zip" in the folder of the backups: one
  "<export_filename>.md" per conversation (all versions, notes / titles / highlights via office_export.annotations_of),
  a number on equal names, its files in "fichiers/<name>/" (zipexport.Bundle with a slot replaced once the name is
  known), "Sommaire.md" (i18n `allexport.summary_file`). Button `#admin-export-all` (job `/__cev__/export-all`),
  `--tout-exporter`.
- `uninstall.py` (AF-m1 b): `targets(site, program, home)` (site, program folder only if CEV's and not holding the
  site / home, icon files Linux or Windows incl. former names, Piper folder, sounds cache; only what exists, sizes),
  `copies_dir` (= backup.destination / "CEV-sauvegarde-<date>"), `check_dest` (never inside a target), `make_copies`
  (exports copied, site ZIP via backup.make_backup, Markdown ZIP, program ZIP laid out as given out, LISEZMOI.txt
  i18n `uninstall.readme`; any error → UninstallError and nothing removed), `remove`, `backup_root` / `restore`
  (ZIP of a site, into a folder without archive only; names leaving the folder ignored).
  Server: POST `/__cev__/uninstall-plan`, job `/__cev__/uninstall` {copies, dest} (program = ctx.launcher.parent;
  copies under the lock, then removal; the server stops 4 s after); the page clears localStorage / sessionStorage.
  A backup ZIP dropped on the index is restored (drop_job, refused when an archive exists). CLI `--desinstaller`
  (questions in the terminal, every server of the site stopped: server.stop_running), `--restaurer ZIP` (then opens).
  Tests: tests/test_uninstall.py (own HOME and program folder: never the real ones).

## 15/11 (2026.11.15.1)
- The tab "Gestion des données" is always shown. Without the server (a page opened as a file, or no token) it shows
  `#admin-noserver` (`web.data.no_server`) instead of its content (admin.js `noServer`). At the opening, dashboard.js
  opens the overview, else the data (no conversation yet), or the data when admin.js asked first
  (`CEV.dataTabLater`: the token can come before dashboard.js after an update or an import — the bug of the tab
  missing after an import, 14/11).
- First launch: the welcome has no button any more (step 3 points to the frame of the import); `#admin-folders` is
  hidden while there is no conversation (nothing to manage).
- Imports run by the server: `run_streaming` sets CEV_PROGRESS=1; cli `_render_site` then prints
  "\x1fCEV-PROGRESS n total" lines, kept out of the log as `Job.progress` ([n, total] in /__cev__/job); admin.js
  shows a bar `#job-progress` at the top of the log (texts `web.build.*`).

## 15/11 (2026.11.15.2) — installing again without a terminal
- "Installer CEV.sh" (Linux, executable), "Installer CEV.command" (macOS), "Installer CEV.cmd" (Windows, CRLF) at the
  root of the program: a double-click runs `--installer` from their own folder (on an error: kdialog / zenity /
  notify-send / osascript, log in $TMPDIR/cev-installer.log). The ZIP of the program made at the uninstall keeps their
  modes (zipfile stores st_mode).
- An empty Library (no conversation; its state file may hold settings only) offers the most recent backup found in
  the downloads or their "CEV-sauvegarde-*" folders (uninstall.find_backup; POST /__cev__/backup-found), one button
  `#restore-go` in the welcome → job POST /__cev__/restore {path} (server.restore_job: uninstall.restore, then the
  pages made again; the page reloads). `restore` refuses only a Library holding conversations.
- After an uninstall, the page keeps only `.site-header` and shows `.uninstalled` (web.uninstall.final with the
  folder of the copies, or web.uninstall.closed), the log moved into its "Détails".

## 15/11 (2026.11.15.3) — backups checked
- Seen at the user's: a backup of a test Library (0 conversation, 2 MB) in the downloads had the same name as the
  full copy of the uninstall (140 MB, in CEV-sauvegarde-…) and, more recent, was the one offered. Now
  `uninstall.backup_count(zip)` (the conversations of its archive/etat.json): `find_backup` offers the backup holding
  the most conversations (most recent among equals), never an empty one; the offer names its folder and its count.
- `make_copies` checks the ZIP of the site before anything is removed (its count = the archive's, else
  `uninstall.copy_incomplete`); `restore` refuses an empty backup (`restore.empty`) and checks the archive read back
  (`restore.incomplete`).
- Tests faster: the test servers of test_admin are closed once stopped (as serve() does: −25 s), the content search
  tests wait for the `cev-content` event and the position of the first passage instead of fixed delays.

## 15/11 (2026.11.15.4)
- AF-f4: the index gets `data-import` (html_builder `_last_import`: the latest `imported_at` of the exports); the
  tile of the size (dashboard.js) turns brick, clickable (opens the tab of the data), with `web.dash.save_due_*`
  when there is no backup, when it is over 30 days old or older than the latest import; `#admin-backup` gets
  `.due` and the same tooltip. backup.last_backup ignores the Markdown export.
- Tabs of the index drawn closed too (thin outline, light ground), in small capitals.
- "<" ">" after the title of the index and of each conversation (`.hist-nav`, icons back / forward, nav.js):
  history.back / forward, greyed with the Navigation API (canGoBack / canGoForward; without it ">" stays on).

## 15/11 (2026.11.15.5) — AF-f5
- annotations.save keeps the former file in archive/annotations-copies/ (`_keep_copy`, never in the way of the
  saving): at most one copy every SPACING (300 s), always one when more than one annotation goes at once (or
  `force`), KEEP (5) at most. `copies()` (name, date, `counts()`), `recover(name)` (the current state kept first).
  POST /__cev__/annotations-copies {"action": "list" | "recover", "name"}; button "Récupération des annotations…"
  (`#admin-annot`, panel `#annot-panel`, reopened after the reload). Tests: tests/test_annot_copies.py.

## 15/11 (2026.11.15.6) — AF-f6: the tests lightened (361 tests, ~4 min 45 → ~3 min 50)
- fetch.POLL (module constant, default 1.0 s) is the second between two looks at the downloads; run_cli of
  test_fetch sets it to 0.05 (14 s → 1 s).
- test_search_content: helpers `_armed` / `_content` (the "cev-content" event of search.js counts the searches
  done), `_pos` (the ".hit-pos" written once after the whole count), `_aimed` (the current passage reached);
  test_index_and_page_count_the_same opens the index once. test_speak (scrolling): waits on
  |scrollY − CEV.speak.target()| < 25. test_fold_browser: `arrived(i)` instead of 900 ms waits; after an aimed
  jump, wait for scrollY stable 150 ms before moving (its aim would pull back). The "no reload by itself"
  negative checks: 2.5 s → 1 s.
- No test removed: each still covers its own fix or feature.

## 15/11 (2026.11.15.7) — faster rebuilds (measured under cProfile at the user's: 52 % search text, 14 % Pygments)
- html_builder: the text of the search (searchdata.from_page, which parses each page again) is keyed on
  `search_signature()` (searchdata.py, renderer.py, conversation.html.j2) + the conversation's hashes + the
  language, no longer on the whole program signature: an update that leaves the reading of the messages alone
  makes the pages again without reading them. A page not made again but whose key changed is read from its file.
  (The first update after 2026.11.15.7 still reads every page once: the former keys differ.)
- renderer._lexer_for keeps the failures too (None): for an unknown language name Pygments scanned every installed
  Python package for a plugin at each block (23 ms each).
- No computing on several cores (the computer must stay usable).
- (2026.11.15.8) `--reconstruire` (force) no longer reads the pages again for the search (its own key); and
  renderer `_plugins_once()` looks for the Pygments plugins once per run (older Pygments, as Ubuntu's, scanned every
  installed package at each lookup, by language name and by file name — created.language: 18 s more under cProfile).
- (2026.11.15.9) `_plugins_once` patches the namespace the functions of pygments.lexers really read
  (`find_lexer_class_for_filename.__globals__`: pygments.lexers replaces its module by a lazy one, so setting the
  attribute changed nothing — measured at the user's: still 781 scans). Test with a counter in that namespace
  (counter-check: the former patch fails it). Measured at the user's after the search fix: 176 s → 84 s under
  cProfile; this one should take ~19 s more off.
- (2026.11.15.10) `codecache.py`: the HTML of each coloured block kept in the user's cache (cev-highlight.sqlite next
  to cev-speech; key = Pygments version + language + code; synchronous=OFF; over 100 MB started again; any error →
  colouring as before). renderer._highlight_code reads it first. The uninstall removes it (key "cache").
  Measured at the user's before it: 64 s under cProfile, ~26 s of it Pygments colouring.
- (2026.11.15.11) renderer.render_markdown keeps the HTML of each Markdown text in the same cache (namespace
  "md:" + `_markdown_signature(lang)`: renderer.py, math_plugin.py, icons.py, i18n/<lang>.json, mistune and Pygments
  versions). Measured at the user's before it: 39.6 s under cProfile, 23.7 s of it mistune (an older mistune of
  the distribution: 248 000 slow regex searches). conftest gives each test its own codecache.
- (2026.11.15.12) One page, each thing once: `_render_page` builds the tree once (items_from_raw copies the messages
  it changes, so a second call gives other objects), validates each message once (memo by id, the payload kept so
  that its id cannot be reused), and writes each message once for both Markdown versions
  (`conversation_markdown(kept=…)`). `created.reconstruct_kept` keeps the files handed over by Claude in codecache
  (namespace "created:" + hash of created.py and tree.py; key = the conversation's hash and removed_hash);
  `created.language` cached by base name. Measured at the user's before it: 15.9 s under cProfile (was 176 s).
- (2026.11.15.13) `i18n.dumps`: the text of json.dumps(…, ensure_ascii=False) for str/int/dict without making an
  encoder at each call (markdown_export.marker and i18n args attributes; 21 000 calls, 0.55 s of the 10 s measured
  under cProfile at the user's). Test: same text as json.dumps on a set of values. PT-m6 closed for now:
  176 s → 10 s under cProfile; what remains is spread (archive reading, validation, page writing).
- (2026.11.15.14) Tabs of a conversation (`.fav-tabs > .fav-list > summary`: Liens, Favoris, Notes, Titres) drawn as
  the tabs of the index (`.index-tab`): closed ones outlined on a light ground, small capitals, accent on hover; the
  open one joins its frame (bottom line in the surface colour) in bold. CSS only (style.css).
- (2026.11.15.15) AE-m10 "Vérifier l'archive" (`verify.py`): `check(site, say)` reads again etat.json, each
  conversations/<name>.json.gz (present, gzip check sum, JSON, same uuid), the user's JSON files (annotations, topics,
  files, settings, annotations-copies/*) and those set aside (`jsonfile.damaged`), the indexes of cdn/ and esm/ and
  each file they name, every ZIP of exports/** in full (`testzip`) and its JSON files; one line per problem
  (`verify.*`), then "Tout est lisible (…)" or "Problèmes trouvés : n" with how many conversations are repairable.
  `repair(site, uuids, say)` (lock held by the caller): every version of the conversation in the exports kept
  (`loader.export_date`, moved from cli) merged as an import does (the version of meta["version_export"], else the
  latest; the others' messages kept as removed), meta hash set to that version (the page is made again). Messages
  only the lost file held cannot come back. CLI `--verifier` (asks "Rétablir… ?" in a terminal) / `--reparer`
  (without asking), then the pages; run by the server it prints `verify.REPAIRABLE_MARK n` → `job.extra.repairable`
  → the page adds a "Réparer" button in the log (Oui/Non, then `/__cev__/verify {"repair": true}`). Button "Vérifier
  l'archive" in Gestion des données (`/__cev__/verify`). Checked first by the backup (warning, made all the same:
  CLI and job) and the uninstall (CLI: "Désinstaller quand même ?"; job: stops before any copy with
  `job.extra.problems`, the page asks and starts it again with `ignore_problems`). Tests: tests/test_verify.py
  (a test of uninstall_job must use a program folder of its own, test_uninstall._home: the real one would be
  removed).
- (2026.11.15.16) test_speak_in_the_browser 12.9 s → 4.7 s: `CEV.speak.timing` ({pause: 1, poll: 1000}: the factor of
  the pauses of the reading, the look at an installation of Piper in ms), shortened by that test only; the fake Piper
  answers 20 ms of sound (was 100 ms). Nothing changed for the user (defaults as before); every check kept.
- (2026.11.15.17) AE-f1 formulas read aloud (speak.js `parse`): a formula in a sentence (`.math-inline`, rendered or
  not yet — the lazy rendering leaves its TeX — or a lone `.katex`) is read when short (`mathSaid(tex)`: letters,
  numbers, Greek letters as characters, = + − < > ( ) , and a one-character exponent / index, at most 5 items:
  "\alpha" → "α", "x^2 + 1" → "x 2 + 1"), else named "formule"; a formula on its own line (`.math-display`,
  `.katex-display`) "formule." (before: every formula "formule", and a formula not yet rendered read as its TeX).
  No space before , . ; in the text read. How Piper says α, −, = is not checked (fake Piper here).
  Test: test_speak.test_formulas_said.
- (2026.11.15.18) AE-f1 continued, after listening at the user's (β said "vita", "=" silent, "Le terme formule
  s'annule"): `mathSaid` says Greek letters by their names (`web.speak.greek`, 24 names a language) and = + − < > in
  words, "f(x)" as "f de x" (`web.speak.math_words`: equals|plus|minus|less|greater|of), takes ; and , as pauses, \left
  \right ignored, up to 6 items. A longer formula in a sentence is named by one of 10 nouns without article
  (`web.speak.formula_inline`), one on its own line announced by one of 10 short sentences
  (`web.speak.formula_line`): `pick` takes one at random, the first 3 times as often, never the same twice in a row.
  All are labels (`labelTexts`, longest first: out of the language detection, said in CEV's language).
  `web.speak.formula` removed. Option chosen by the user: no Speech Rule Engine for now (it covers only part of the
  12 languages). The words for a formula are in CEV's language even inside a paragraph in another one.
- (2026.11.15.19) Formulas read aloud: ≤ ≥ ≠ ≈ said in words (in a formula: also \le \leq \leqslant \ge \geq
  \geqslant \ne \neq \approx \simeq \lt \gt, `MATH_CMD`; in the text too), `web.speak.math_words` has 10 words now
  (… of | ≤ | ≥ | ≠ | ≈); a short pause (a comma) after a formula read of 2 items or more; the lines lose a comma
  before another mark or at their end.
- (2026.11.16.1) AE-m3 step 1, suites ("suite de"): a suite is a link with a direction. annotations "series": lists
  of 2+ conversations (sorted uuids; each conversation in one suite at most, `_clean_series`), read in the order of
  their dates; actions `series_join` {a, b, here} (the three and the suites they were in become one) and
  `series_leave` {conversation} (its links stay; a suite of one is no more); `clear_links` also takes the
  conversation out of its suite; `convs` (titles for the pages) covers the members of suites (`_with_series`).
  links.js — page: in "Liens", the suite in a frame (`.series-box`: brick line on the left, numbers, icon
  `series` of icons.py — two pages and an arrow, never the chain), this conversation in it ("ce fil", italic, not
  dragged); the simple links under it; a link dragged onto another one (or onto the frame) → `series_join` with
  this conversation; a member dragged out of the frame, or its cross → `series_leave` (the cross of a simple link
  still unlinks); hint `web.series.hint` when 2+ links; "Liens (n)" counts the links only, as the index (a member of the suite not linked is shown, not counted). The
  line `.series-line` "Suite : fil k sur n · ← previous … next →" after the tabs and after the messages (bottom:
  "Fil suivant : …"), not printed. The index is unchanged (the user's choice, 16/11: links made there, suites on the pages). Step 2 (to do, after the user's choices): a checkbox "Afficher
  la suite d'un seul tenant". Tests: tests/test_series.py.
- (2026.11.17.1) Suites with one link: not yet in a suite, with a link at least (served), this conversation is a row
  among the links ("date Titre — ce fil", by date, `.series-here` with `.series-spacer` in place of the icon, no
  cross, not dragged); a link dragged onto it → `series_join` of the two. Hint from one link, text of the user:
  "Glisser un lien sur un autre, ou sur « ce fil » forment une suite classée chronologiquement." Nothing else changed.
- (2026.11.17.2) AE-c1: the plan view removed (the user's choice: Structure preferred). plan.js keeps the bar
  "Vue : Lecture · Structure" (a view "plan" kept by the browser opens the reading), "Lignes" of the reading
  (`data-read-lines`, `html.cev-read-cut`, icons `.plan-icons` and arrow `.plan-dn` of a cut bubble), the titles and
  "Titres (n)"; gone: `html.cev-plan`, `data-plan-lines`, versions/forks (`walk`), chapters, "Montrer", "Branches non
  suivies repliées", the strip of markers, `place`/`ticks`; their CSS and i18n keys (web.plan.plan, show, fold,
  versions…). The description of plan.js above is partly history. README.fr.md says "deux vues" (the other READMEs:
  AF-f2). Test: test_plan.test_no_plan_view.
- (2026.11.18.1) AE-c1 point 1: the numbers of the structure in the reading — structure.js `badges()`: before the
  name of each bubble (`.message-time`), `.st-badge` = its number in the actual order (`label` of `layout(tree(root))`,
  counted once: the structure view only adds classes) and its logical links (`.st-badge-link` "→ 4", a click opens
  the frames above that bubble, scrolls to it, `.st-flash`); repainted on `cev-annotations`/`cev-language`; not
  printed; checkbox "Masquer les numéros" (`#hide-numbers`, body.cev-hide-numbers, unchecked whenever a page
  opens, fold.js). AE-m3, the suites in the order set by the user: one action `series_set` {here, order} (made,
  ordered, added to, left; a conversation of another suite moved here leaves it — the page asks first,
  `web.series.move_ask`; fewer than 2: no suite); the suites of 16-17/11 (sorted uuids) put once in the order of
  their dates (`series_ordered` in annotations.json, not sent to the pages). links.js: a sortable list with
  pointer events (no HTML5 drag): the row lifted follows the mouse (`.series-ghost`), an empty place
  (`.series-slot`) opens where it would go; in the frame: new order; out of it: leaves the suite; no suite yet: a
  row let go next to another one (or "ce fil") makes the suite of the two and this conversation, in the order
  shown; Escape cancels; the click that ends a drag is swallowed. The lines "Suite : fil k sur n" follow that
  order. Tests: test_series.py (rewritten), test_plan.test_structure_numbers_in_the_reading.
- (2026.11.18.2) A suite is a link: `_link_suites` (in `load`, so also for the suites made before, and after each
  change of links) links the conversations of a suite together; taken out of the suite, a conversation keeps
  those links; "unlink" of two of one suite takes b out of it. "Liens (n)" and the list agree on every page.
- (2026.11.18.3) Structure list (structure.js `list`): in the order and with the indents of the drawing (the
  user's example of 18/11): a tree from `rows[].prev` — the starts (prev null, and the heads of a cut part) in the
  order asked, at 0; after a question: its other answers (+1, in the order of the lanes) then its own answer
  (same level); after an answer: one question alone at the same level, several (versions, a part moved after
  it, a part pushed) +1 each, in the order of the lanes (top first); indent = level × 22 px. The old splice
  "a part moved under a question right under it" is gone. Reading badges: a move too (`.st-badge-move`: "↳ R2"
  after an answer, "⤷ 3" under a question — a click goes there; "✂" cut). "Masquer les numéros": visibility
  hidden, the place kept (no jump).
- (2026.11.18.4) Reading: the structure on the bubbles (structure.js `badges`, the order chosen in the structure
  view, `shape()`; made again when it changes): "[before] ← [itself] → [other answers] [questions after]" —
  before: the question a question follows (through its answer) or the question of another answer; after a
  question: its other answers (lane order) then the questions after its own answer (`questionsAfter`, through
  answers going on); an answer on the line of its question: its number only; a part cut: "✂" before. Pills
  `.st-pill` drawn as the points (full blue: question of a solid line; circled blue `.st-off`; circled grey
  `.st-ans`), buttons with data-go (brick on hover; itself `.st-self`, not clickable); logical links green
  after. The move pills of 18.3 are gone.
- (2026.11.18.5) A pill clicked: in the structure view, `choose(uuid)` (as a click in the list: the bubble shown
  with its answers); in the reading, the frames opened and the bubble scrolled to. Either way its own frame turns
  brick for 0.5 s (`.st-flash`: border-color of the bubble; no more outline around it).
- (2026.11.21.1) Conversation head: line "Masquer :" (screen only, fold.js; each box kept by the browser for every
  conversation, localStorage cev-hide-*: les ressources de l'IA (checked at first), les notes, les titres, les
  numéros, les autres versions et suppressions — `#hide-versions`, body.cev-main-only, event cev-versions); the box
  "Inclure les autres versions…" of "Exporter :" acts on the files only (export.js); the boxes Annotations and ZIP
  kept too (cev-export-annot, cev-export-zip). Structure: "Ordre", "Annuler", "Réinitialiser" (`.st-bar`) at the end
  of the line of "Vue" (#plan-bar, hidden in the reading; their clicks: `barClick`). The value chosen in a chip
  drawn bold by a text-shadow (no change of width: nothing moves). Pill clicked: the bubble's frame brick 1 s.
  server.py: an invalid escape of _BUILDING_PAGE doubled (SyntaxWarning). README.fr.md: a guide with captures
  (docs/fr, docs/en; made from a demo library by the scripts of the session, not kept in the repository).

## 2026.11.21.2
- Ligne « Masquer : » alignée (.view-options en flex, libellé export-label).
- Barre Structure (Ordre, Annuler, Réinitialiser) toujours présente en fin de ligne Vue, `visibility: hidden` hors Structure : aucun déplacement en basculant Lecture/Structure. L'aide « Comment réorganiser » est revenue en tête du panneau (helpBox), plus dans #plan-bar.
- 33 chaînes « Archives Claude » restantes remplacées par web.site_title de chaque langue.
- READMEs réécrits en mode d'emploi (fr validé par Dom) ; captures docs/fr et docs/en (bibliothèque de démonstration, thème clair) ; anciennes docs/accueil|conversation|structure.png supprimées. Les 11 traductions générées par scripts hors dépôt (readmes_tpl.py + tr_*.py), non relues.

## 2026.11.21.3 — corrections de la revue de l'audit ChatGPT (tests : tests/test_audit_fixes.py, chacun échoue sur la 21.2)
- A1 : `loader._iter_array` strict (fichier coupé avant `]`, virgule manquante, doublée ou finale, contenu après `]` → JSONDecodeError, après les éléments déjà lus). Option (b) choisie par Dom : un fichier de conversations illisible jusqu'au bout (aussi un ZIP corrompu) → les conversations lues sont gardées, mais l'export est enregistré `"incomplete": true` dans etat.json : ni `latest_export` ni `deleted_since` n'en tiennent compte (aucune marque « supprimée »), message cli.import.incomplete. `import_export(read_ok=…)`, `loader.pop_read_errors()` (seuls les fichiers de conversations comptent). Réimporter l'export complet de la même date remplace l'entrée.
- Verrou : `jsonfile.one_at_a_time()` (RLock propre à chaque module) autour des lecture-modification-écriture d'annotations (change, recover, save), topics, settings et userfiles : le serveur répond en threads ; deux changements simultanés (deux onglets) pouvaient perdre l'un des deux.
- A2 : `uninstall.restore` écrit etat.json en dernier, chaque fichier via un temporaire, puis vérifie que chaque conversation a son fichier ; sinon etat.json → etat.json.incomplet : la Bibliothèque reste vide et la restauration peut être refaite. (Les quelques fichiers d'une Bibliothèque vide, pages et réglages, sont remplacés : docstring corrigée.)
- A3 : taille d'une version d'artefact = `ZipInfo.file_size` (zipfile ne rend jamais plus), plus `size_bytes` du listing ; extraction ratée → dossier temporaire supprimé.
- B1 : `cdn_cache.open_https` : redirections suivies seulement en https (5 au plus) ; pour esm_cache, seulement vers esm.sh.
- B2 : web.run.ask dit honnêtement que le programme lancé avec Internet pourra joindre d'autres sites (la CSP `https:` reste : une restriction par domaine casserait des pages et n'empêcherait pas la navigation du cadre).
- B5 : `drop.receive` refuse un morceau si le disque garderait moins de `RESERVE` (512 Mo) libres (drop.no_space).
- B6 : `install.place_program` : dossiers temporaires de noms uniques (un dossier de l'utilisateur nommé « .nouveau »/« .ancien » n'est plus supprimé ; un reste d'installation coupée seulement s'il contient le lanceur), ancienne version remise si la nouvelle ne peut pas prendre sa place.
- P2 : `write_extras` passe à `extras.summary` ce qu'il a déjà lu : chaque sorte de ZIP annexe lue une fois par génération.
- Non retenus : A4 (journaux : négligeable ; une durée maximale tuerait un gros import légitime — un bouton Annuler serait une fonction à part), P1 (seulement sans manifeste, réorganisation de l'import), P3 (quelques millisecondes).
- Tests : test_phase_c_browser attend 500 ms avant le rechargement (échec intermittent sous la charge de la suite, cause probable : localStorage pas encore enregistré — hypothèse) ; test_uninstall : encodages explicites (la suite passe de nouveau avec -W error::EncodingWarning).

## 2026.11.21.4 — revue des attaques ciblées (tests : test_audit_fixes.py, suite ; test_hostile.py)
- Dates d'export (décidé avec Dom) : trois dates contrôlées — la date de l'export, l'horloge de l'ordinateur et la conversation la plus récente de l'export. `loader.date_question` : export daté de plus de `FUTURE_MARGIN` (1 jour : fuseaux, horloge décalée de quelques heures, double démarrage Windows/Linux) après l'horloge → rien n'est importé ; la CLI affiche les trois dates et sort (code 3) ; `--date-confirmee` passe outre ; marque `DATE_MARK` lue par le serveur (`job.extra["date_question"]`, `ctx.pending_import`), la page demande (CEV.choose : date de l'export / date de la conversation la plus récente / Annuler) puis POST /__cev__/import-date (`date_job`, toujours avec --date-confirmee). Pourquoi : un export daté du futur (manifeste fabriqué, faute de frappe dans --date-export) restait pour toujours le plus récent : les exports suivants pris pour plus anciens (leurs changements jamais affichés), ses absentes marquées supprimées — reproduit sur la 21.3. Une horloge en retard (pile du BIOS) n'est pas tranchée par CEV : l'utilisateur voit les trois dates. Date antérieure à la conversation la plus récente (`ImportStats.date_before_newest`) : sans danger (export traité comme plus ancien), seulement signalée.
- `verify` : un export daté du futur est signalé ; réparable (« Réparer ») quand sa conversation la plus récente n'est pas elle-même dans le futur : il prend cette date (pas celle de l'horloge) ; `last_seen` égal à l'ancienne date → la plus récente des dates valides (vivante jusqu'au prochain import). Si la conversation la plus récente est aussi dans le futur : horloge sans doute fausse, rien n'est réparé.
- Noms de fichiers : `userfiles.short_name` (100 caractères, 180 octets UTF-8, extension gardée, 8 caractères de hachage) pour les pièces jointes, les fichiers créés et associés ; une écriture ratée laisse le fichier sans lien au lieu de faire tomber la page (reproduit : nom de 255 octets → page non générée).
- `loader.MAX_ELEMENT` (1 Gio de caractères) par élément JSON (tableau, JSONL, objet sur plusieurs lignes) ; `archive.DISK_RESERVE` (512 Mo) : l'import s'arrête avant (`DiskFull`), l'archive reste comme après un import coupé, le même export réimporté termine.
- Synthèse vocale : `speech.PIPER_VERSION` (piper-tts==1.8.0, version d'une installation réelle qui fonctionne ; 1.6.0 jamais testée).
- test_hostile.py : 21 injections dans tous les champs ; lecture de toutes les pages et ouverture dans Chromium par le serveur de CEV (aucune boîte alert ne doit s'ouvrir hors des cadres).

## 2026.11.21.5 — Piper 1.8.0 ; prototype de la lecture par morceaux (prochaine étape)
- Piper : au moins 1.8.0 (`speech.PIPER_MIN`, `piper-tts>=1.8.0` avec --upgrade : les versions suivantes sont prises, choix de Dom). `system.command_line` met entre guillemets, sous Windows, un argument avec > < | & ^ (sinon cmd.exe y voit une redirection).
- But décidé avec Dom : lire et afficher une conversation plus grande que la mémoire disponible (claude.ai l'affiche par morceaux ; la compaction automatique rend les conversations sans fin), en tenant compte des ressources de l'ordinateur de l'utilisateur, quel qu'il soit ; à garder valable pour d'autres IA plus tard.
- `tools/proto_chunks.py` (hors du programme) : lecture d'une conversation message par message (`Reader.conversation`, tableau strict comme `_iter_array`), rangement en morceaux gzip JSONL d'environ 2 Mo, en mémoire seulement l'index uuid → (parent, morceau). Mesuré le 21/11 : conversation de 1,5 Go (127 799 messages) lue sous une limite de 700 Mo d'espace mémoire (`prlimit --as`) : 18 s, 51 Mo au plus, sha256 des messages identique à la génération ; la lecture actuelle (loader, plafond levé) : MemoryError sous la même limite. Non testé : un seul message géant, des messages réels (blocs variés), le rendu.
- Plan d'intégration (un seul chemin de rendu : une conversation ordinaire = un morceau) : 1) lecture par messages dans loader ; 2) archive en morceaux + index (format d'archive à migrer, sans perte) ; 3) fusion des versions et hachage message par message ; 4) page chargeant ses messages par morceaux au défilement (aussi en file://, morceaux en scripts) ; 5) recherche, Structure, favoris, notes, exports .odt/.docx/Markdown par morceaux ; 6) seuils d'après la mémoire libre de l'ordinateur ; le plafond `MAX_ELEMENT` ne restera que pour un seul message géant (mise de côté + question).

## 2026.11.21.6 — étape 1 de la lecture par morceaux : les conversations lues message par message
- `loader._Reader` (une seule lecture stricte pour tous les tableaux, remplace l'ancien `_iter_array`) et `loader.Events` : avec `iter_json_items(f, STREAMED)`, chaque objet d'un tableau est donné champ par champ, et les éléments de `chat_messages` un par un ; `Events.assemble()` refait l'objet exactement comme json.loads (ordre des clés, clé répétée : première place, dernière valeur). `_iter_events` (lecture + erreurs comptées) ; `_iter_raw` refait les conversations entières (l'archive les garde encore entières : étape 2) ; `data_date` ne garde que les champs : une conversation plus grande que la mémoire est lue (mémoire mesurée identique pour 28 et 114 Mo).
- `MAX_ELEMENT` s'applique désormais à chaque valeur lue (un message, un champ), plus à une conversation entière.
- Nombre coupé par la fin d'un bloc (« 12345. » puis « 678 ») : lu en entier (défaut trouvé par le test d'équivalence aléatoire, présent aussi dans l'ancienne lecture pour les nombres au premier niveau).
- Mesuré : export de 200 Mo à une conversation géante lu en 0,6 s (1,5 s avant : l'ancienne relisait le tampon qui grandissait) ; 5 000 petites conversations (89 Mo) : 0,3 s avant comme après.
- Tests (test_audit_fixes.py) : équivalence avec json.loads sur 750 structures aléatoires (blocs de 1, 2, 3, 7 caractères et 1 Mio ; clés « chat_messages » à toutes les places, valeurs qui ne sont pas des objets, caractères spéciaux) ; clé répétée et conversation coupée ; mémoire de `data_date` indépendante de la taille.
- Étape suivante (2) : l'archive range une conversation en morceaux (gzip JSONL) + index, en consommant les Events au lieu de `assemble()` ; migration de l'archive existante sans perte.

## 2026.11.21.7 — étape 2 de la lecture par morceaux : une conversation rangée ligne par ligne
- `archive/conversations/<nom>.jsonl.gz` : ligne 1 `{"cev": 2, "meta": {…}}` (tous les champs dans leur ordre ; les listes `chat_messages`, `tree.EXTRA_KEY`, `tree.LEGACY_REMOVED_KEY` à [] à leur place), puis une ligne `[clé, élément]` par élément de ces listes. `write_raw` (par un .tmp), `iter_raw_file` (ligne par ligne : mémoire indépendante de la taille, mesurée), `read_raw_file` (entière, comme avant), `Archive.raw_file` (la forme actuelle, sinon l'ancienne), `Archive.iter_raw(uuid)`.
- Ancienne forme `<nom>.json.gz` (JSON entier) toujours lue (`iter_raw_file` la donne de la même façon) ; une conversation passe à la nouvelle forme quand elle est réécrite (import qui la change, réparation), l'ancien fichier est alors supprimé. Pas de conversion en masse. Hachages inchangés (calculés sur la conversation, pas sur le fichier) : un import ne voit rien de changé de plus.
- verify lit les deux formes (en-tête illisible = conversation illisible) ; la vérification d'une restauration compte les deux.
- Mesuré sur 5 000 conversations (100 000 messages) : import 5,4 s avant, 5,3 s après ; relecture complète de toutes les conversations 0,3 s avant, 0,6 s après (un `json.loads` par ligne ; négligeable devant le rendu des pages) ; même place sur le disque.
- Tests : aller-retour sur 200 conversations aléatoires (valeurs et ordre des clés), ancienne forme lue puis convertie à la réécriture (l'inchangée reste dans l'ancienne forme, aucun changement vu en trop), mémoire de lecture indépendante de la taille, en-tête illisible signalé par verify.
- Étape suivante (3) : l'import n'assemble plus la conversation : hachage calculé au fil des messages (même valeur que `_hash`), fusion des versions et comptage du fil principal d'après un index (uuid → parent), validation message par message, écriture au fil de la lecture (`write_raw` en flux).

## 2026.11.21.8 — étape 3a : `archive.RawSpool` (pas encore branché sur l'import)
- Reçoit une conversation champ par champ et message par message (les Events de loader : `field`, `start`, `item`), écrit chaque message aussitôt dans un fichier temporaire (`archive/conversations/conversation-*.tmp`, supprimé à la fermeture) ; `hash()` = `_hash(conversation entière)` (calculé en relisant le temporaire : préfixe des clés triées, puis les messages canoniques) ; `write(path)` = le fichier de l'archive (forme de `write_raw`), ligne par ligne. Les messages sont gardés clés triées (forme canonique ; l'ordre des clés d'un message n'a pas de sens).
- Test : 200 conversations aléatoires lues par Events : même hachage que `_hash`, même conversation relue, temporaires supprimés.
- Limite connue : une clé `chat_messages` répétée dans un même objet (json.loads garde la dernière) n'est pas gérée par le spool (les deux listes seraient hachées) ; jamais vue dans un export.
- Reste de l'étape 3 (un import qui n'assemble plus jamais une conversation) :
  - 3b : validation message par message (le modèle d'un message de models.py ; un message invalide rejette la conversation comme aujourd'hui), `_valid_text` par message, `has_text`, `_note_blocks` au fil des messages (loader.iter_conversation_records donnera un RawSpool rempli au lieu de (raw, convo)).
  - 3c : un squelette léger par message (clé, parent, date, ordre, last_seen, LINEAR_PARENT et ce dont `_inherit_artifact_fields` / `_move_injected` ont besoin) pour `visible_count` sans les contenus ; à vérifier : même résultat que `main_path(items_from_raw(raw))` sur des conversations réelles et aléatoires.
  - 3d : `merge_versions` en flux (clés de la version affichée en mémoire ; les messages de l'autre version lus ligne par ligne et recopiés dans `EXTRA_KEY`), `removed_hash` calculé au fil de l'eau ; puis `import_export` branché sur les spools ; la suite complète doit passer, plus un import de 1,5 Go sous mémoire bridée (tools/proto_chunks.py pour générer le fichier).

## 2026.11.21.9 — étape 3b : `loader.iter_conversation_spools` (pas encore branché sur l'import)
- Mêmes conversations gardées et écartées, mêmes avertissements et mêmes comptes de `LeftOut` que `iter_conversation_records`, sans jamais une conversation entière en mémoire : donne (spool, conversation, has_text) — `archive.RawSpool` rempli (messages dans un temporaire de `folder`, supprimé quand la suivante est demandée), `Conversation` validée sur ses seuls champs (`chat_messages` vide), `has_text` = `not is_empty_conversation`. Possible parce que la validation des messages est déjà tolérante (`models._lenient_list` : un message illisible est écarté du modèle, jamais la conversation).
- `_valid_value` : `_valid_text` valeur par valeur (champ, message) ; les blocs comptés (`broken_blocks`, `unknown_blocks`) ne sont ajoutés qu'une fois la conversation acceptée, comme `_note_blocks`.
- Test : 40 jeux aléatoires (messages vides, outils, blocs inconnus ou cassés, non-objets, dates illisibles, demi-caractères isolés, uuid manquant / vide / numérique / répété, titres invalides, tableau et JSONL) : mêmes uuid, mêmes champs validés, même `has_text`, même hachage, mêmes avertissements et comptes. Vérifié qu'il détecte deux erreurs introduites exprès (texte blanc compté comme texte ; blocs inconnus non comptés).
- Reste : 3c (squelette pour `visible_count`), 3d (fusion en flux, import branché, essai 1,5 Go sous mémoire bridée).

## 2026.11.21.10 — étapes 3c et 3d : l'import ne tient plus jamais une conversation entière
- 3c : `tree.skeleton(msg[, extra])` (clé, parent, date, last_seen ; jamais le contenu) et `tree.count_main(courants, extras)` = `len(main_path(items_from_raw(raw)))` : main_path ne regarde pas les contenus (`_inherit_artifact_fields`/`_move_injected` ne changent que les payloads). Test : 1 500 conversations aléatoires (clés répétées, parents inconnus, sans parents, extras, ancien format `_cev_removed_parts`, non-objets).
- 3d : `archive.StoredConversation` (une conversation de l'archive relue ligne par ligne, autant de fois que nécessaire), `_extras_of` (`extra_messages` élément par élément), `merge_stream(current, other, date, dossier)` = `merge_versions` écrit dans un temporaire (en mémoire : les clés et les squelettes), avec `removed_hash`, `removed_messages`, `n_messages` ; `Archive._install` le met en place (comme `_store_merged`). Test : 400 paires aléatoires dans les deux sens, spool en mémoire ou sur disque tiré au hasard : même conversation (champs dans leur ordre, valeurs), mêmes `added`, `removed_hash`, `removed_messages`, `n_messages`.
- `import_export` prend des (spool, conversation, has_text) (`loader.iter_conversation_spools`, ce que la CLI donne) ou des (raw, conversation) (convertis par `RawSpool.from_raw` : tests, anciens appels) ; hachage par `RawSpool.hash()`, nouvelle conversation écrite par `RawSpool.write`, versions fusionnées par `merge_stream`. `merge_versions`/`_store_merged` restent pour la réparation de verify (qui relit des exports entiers).
- `RawSpool` : lignes gardées en mémoire jusqu'à `MEMORY` (8 M caractères), au-delà dans un temporaire de `archive/temporaire` (`archive.TEMP_DIR`, vidé au début de chaque import, exclu des sauvegardes).
- Mesuré : conversation de 1,5 Go (127 799 messages) importée sous une limite de 700 Mo (`prlimit --as`) : 24 s, 107 Mo au plus ; puis une version modifiée (fusion de deux versions de 1,5 Go) : 37 s, 140 Mo, la modification prise, aucun temporaire restant. La mémoire suit désormais le nombre de messages (clés, squelettes : environ 1 Ko par message), plus leur taille. Import ordinaire de 5 000 conversations : 5,4 s avant, 5,3 s après (bruit ±0,6 s).
- Reste (étape 4, la plus visible) : le rendu d'une page relit encore la conversation entière (`html_builder` → `load_raw`) ; une conversation géante est importée et gardée, mais sa page ne peut pas encore être faite sur un petit ordinateur. Ensuite : page chargée par morceaux au défilement (aussi en file://), recherche, Structure, favoris, notes, exports par morceaux ; seuils d'après la mémoire libre.
- Suite : 426 tests ; un échec isolé lors d'une des trois exécutions complètes du 21/11 (nom non relevé : la sortie avait été coupée), les deux suivantes sans échec : un test instable de plus à identifier (lancer avec -rf).

## 2026.11.21.11 — étape 4 et fin de la lecture par morceaux (travail fait en l'absence de Dom, choix ci-dessous)
- **Affichage d'une très longue conversation : en plusieurs pages** (choix : plutôt qu'une page qui chargerait ses messages au défilement, qui aurait demandé de réécrire recherche dans la page, Structure, favoris, notes, export pour des messages absents du DOM ; chaque partie est une page ordinaire où tout marche, aussi en file://). `html_builder` : au-delà de `SPLIT_ABOVE` (8 M caractères de messages) → parties d'environ `PART_CHARS` (4 M) ; `part_limits()` les baisse si la mémoire libre est faible (`system.available_memory()` : /proc/meminfo, Windows GlobalMemoryStatusEx, sinon os.sysconf ; macOS : valeurs par défaut). Une conversation ordinaire = une page, faite comme avant (même chemin `_render_page`) ; fichier stocké < `SMALL_FILE` (512 Ko compressés) : pas même mesurée.
- `tree.plan_parts` : découpe le fil principal ; chaque message emporte les branches qui partent de lui (cadres dans sa partie) ; arbres hors du fil principal → partie 1 ; une partie se termine avant un de vos messages (question et réponse ensemble ; au plus 2× la taille en attendant). `Item.forced` : fin imposée du fil principal d'une partie (`_best_leaf`, `_root_of` suivent). `html_builder.iter_part_raws` : une lecture de la conversation répartit les messages dans un temporaire par partie (`archive/temporaire/parties-<nom>`), puis une partie à la fois en mémoire. Pages `<nom>.html`, `<nom>.p2.html`… ; barre « Partie k sur n » (haut et bas, `web.parts.*`) ; en-tête : nombre de messages de toute la conversation (`n_total`) ; `<nom>.parties.js` (`window.CEV_PART_OF`), lu par `static/parts.js` seulement quand un lien `#msg=…` vise un message d'une autre partie (favoris, notes, recherche) → redirection. Parties en trop d'un rendu précédent et carte supprimées ; redevenue courte : une page.
- Sommaire : `other_versions`, `removed_parts`, `last_message` calculés sur toute la conversation (squelettes), pas sur la dernière partie.
- Autour : `tokens.evaluate_messages` (au fil des messages ; `evaluate` l'appelle) ; `Archive.stored`, `iter_messages`, `find_message`, `message_source` → `archive.MessageSource` pour les annotations (une conversation longue lue une fois en un petit index uuid → parent, auteur, date, début du texte, gardé pour les deux dernières ; `annotations.find_message` l'accepte) ; `userfiles.links_of` (liens d'une conversation longue partie par partie) ; `office_export.archived_markdown(..., part=)` / `markdown_of_raw` / `part_suffix` : export .md/.txt/.odt/.docx d'une partie (celle de la page : `export.js` envoie `part` ; un message seul : sa partie), nom « … (partie k sur n) » (`export.part_suffix`) ; `allexport` : un fichier par partie, écrit au fur et à mesure.
- **Un message géant** : `loader.element_limit()` = un cinquième de la mémoire libre (au moins 64 M caractères ; `MAX_ELEMENT` le fixe pour les tests ; `MESSAGE_LIMIT` = `--limite-message` Mo). Au-delà, `_Reader._skip` le parcourt sans le garder (un bloc à la fois, chaînes et échappements suivis) → `TooBig`, la lecture continue ; la conversation est gardée sans ce message ; après l'import, la CLI dit sa taille, la mémoire qu'il faudrait et celle qui est libre (`cli.import.too_big`) ; marque `BIG_MARK` → la page demande « Le lire quand même » (`web.import.big_question`) → l'import relancé avec `--limite-message` (`date_job` choix "big"). Réimporté avec la limite : la conversation complète devient la version affichée.
- **Limites connues (choix)** : recherche dans la page, Structure, export = la partie affichée (dit dans la barre) ; la recherche du sommaire couvre les premières parties d'une conversation coupée (`SEARCH_CAP` 16 M caractères ; `meta["search_partial"]`) ; un fichier créé par Claude puis modifié dans une partie suivante n'y est reconstitué que d'après cette partie ; un artefact réécrit dans une autre partie que sa création peut perdre son type ou titre (héritage `_inherit_artifact_fields` limité à la partie) ; une branche (autre version) géante reste entière dans la partie de son message ; la réparation de `verify` (relecture des exports gardés) charge encore une conversation entière.
- Mesuré : conversation de 200 Mo (17 040 messages) importée et affichée par la CLI sous une limite de 700 Mo : 64 s, 215 Mo au plus, 43 pages (site : 616 Mo pour elle, dont le Markdown d'export intégré à chaque page).
- Mesuré : conversation de 1,5 Go (127 799 messages), import et affichage par la CLI sous une limite de 700 Mo : 445 s, 271 Mo au plus, 317 pages, aucun temporaire restant ; site : 4,6 Go pour elle (environ 14 Mo par page, dont deux fois le Markdown d'export intégré : piste d'allègement si besoin).
- Tests instables : (1) test_phase_c_browser (rechargement avant l'enregistrement de localStorage, hypothèse ; attente de 500 ms) ; (2) test_big_archive : les dates de modification bougent par pas de quelques ms, une réécriture dans le même pas que la construction précédente passait inaperçue → dates mises dans le passé avant la reconstruction (déterministe ; cause probable de l'échec isolé du 21/11, non prouvée faute de reproduction). Non reproduits : deux suites complètes simultanées, trois passages sous processeur saturé des 80 tests à minutage (attentes fixes des tests de navigateur, verrous, serveurs). En cas de nouvel échec : `pytest -rf` pour le nom.

## 2026.11.21.12 — audit de l'interface (présentation et manipulation), points 1 à 36 sauf 17
- **Une icône, un sens** : l'export d'un message et l'enregistrement d'un fichier de Claude ont leur dessin (`icons.ICONS["export"]`, une page avec une flèche ; c'était la flèche de pliage) ; « masquer / réafficher les réponses » (un message ou toutes) : l'œil barré / l'œil (`hide`, `show`), plus le chevron ni les flèches ; défilement lent : double chevron (plus le ▶ des programmes) ; vos messages précédent / suivant : chevrons ↑ ↓ (plus ← →, pris pour l'historique ‹ ›) ; milieu de page : deux flèches vers une ligne (plus « = ») ; « Copier » du code avec l'icône de copie ; « Écouter » des voix : le haut-parleur. Test `tests/test_icons_consistency.py` : un même dessin pour des commandes de sens différents échoue (familles admises : `FAMILIES`) ; vérifié qu'il échoue avec l'ancienne icône d'export et l'ancienne d'enregistrement.
- **Manipulations** : case d'export « sans les autres versions et suppressions » (même sens que « Masquer », cochée = sans ; `cev-export-main`, l'ancien choix `cev-export-versions` repris) ; clic dans une bulle coupée à N lignes = l'ouvrir (pas sur un lien, un bouton, ni après une sélection) ; pièce jointe sans fichier d'origine : « l'icône ouvre le texte extrait par claude.ai » (plus « Aucun fichier associé » à côté de « Ouvrir ») ; barre flottante : sur le sommaire une colonne (plus de trous), boutons grisés avec leur bulle d'aide (clics ignorés par nav.js / msg.js) ; fermetures : la croix ronde partout (dialogue des voix compris), la croix bleue des champs de recherche grisée ; « Désinstaller… » à droite, en rouge ; « Créer » une rubrique dans « Gérer les rubriques » ; stylo « Surligner » à côté de la sélection (`.hl-near`, marks.js) ; lier une conversation depuis sa page (liste `.link-pick` dans « Liens », serveur local).
- **Couleurs, textes (12 langues)** : conseil (« Sauvegarde conseillée ») en ambre `--warn`, le rouge orangé restant « ouvert / choisi », le rouge les erreurs et la désinstallation ; passages trouvés en violet (le jaune était celui du surligneur) ; « version active » neutre ; chemins de « Gestion des données » sur le fond du cadre, police à chasse fixe gardée (demande de Dom) ; libellés : « Sauvegarder la Bibliothèque », « Récupérer des annotations… », « Libérer de la place… », « Fautes tolérées − n + », « Rechercher » ; pluriels des cartes (« 1 conversation », « dont 1 supprimée ») ; « évaluation grossière » une seule fois ; « conversation » partout (plus « discussion »), « Bibliothèque » (plus « les archives ») dans les messages de lecture seule, « Effacer » pour les quatre effacements d'annotations ; sons : plus de chemin technique dans la phrase (au survol) ; artefacts : plus « artifact » ni « 0,0 Mo » (Ko).
- `attr2` (html_builder) : deux attributs traduits sur un élément en un seul `data-i18n-attr` (deux, le navigateur gardait le premier : l'`aria-label` de ‹ › ne changeait pas de langue — c'était le point 13).
- **Pages** : filtres à leur largeur (retour à la ligne plutôt que coupés) ; pages « Autres données » avec ‹ › et la barre flottante ; note : coche « Terminer » (plus la disquette : la note s'enregistre d'elle-même) ; dialogue des voix aux styles des pages ; anneau de focus sur les numéros « Aller à cette bulle » ; fenêtre ≤ 640 px : la barre flottante en bas, le texte sur toute la largeur.
- Vérifiés sans changement : pastilles « Vue » et « Lignes » (même règle déjà : un mot le choisit, ailleurs le suivant ; le point 7 venait du script d'audit) ; « Lignes » et « Voix » utiles en Structure (bulles affichées sous l'arbre). Non fait : « Mot entier » dans la recherche du sommaire (demande la recherche côté serveur).
- `tools/add_keys.py` (hors dépôt) écrit aussi les pluriels. Suite : 433 tests.

## 2026.11.21.13 — boutons en bas à droite, l'œil, groupes « Masquer » / « Exporter » (demandes de Dom, 22/11)
- **Même disposition partout** : cadre du haut, sommaire 2×2 (musique, thème ; ‹ précédent, › suivant), conversation 2×4 (surligner, sommaire ; rechercher, masquer les réponses ; musique, thème ; ‹, ›) ; cadre du bas 2×3 partout (haut, milieu, bas à droite ; défilement lent en bas à gauche ; sur le sommaire, les deux autres places vides). ‹ › (historique du navigateur) quittent le titre pour ces cadres, cerclés comme les autres (`data-go="hist-back"` / `"hist-forward"`, mêmes id, nav.js inchangé ; aussi sur les pages « Autres données »).
- **L'œil dit l'état** : ouvert = réponse affichée, barré = masquée (le titre au survol dit l'action) ; pour un message et pour toutes.
- **« Masquer » et « Exporter » en groupes** (option C sur trois maquettes) : titre en gras dans une colonne de 6,5 rem (place pour « Exportieren : »), les options sur une bande claire (`.opt-body`) ; en fenêtre étroite, le titre au-dessus.
- Suite : 433 tests.

## 2026.11.21.14 — en-tête des conversations allégé : onglets « Bulles » et « Exporter » (demande de Dom, 22/11)
- Onglets fermés, l'en-tête tient en deux lignes sous le titre (comme le sommaire). Une rangée d'onglets, deux familles séparées par un espace : réglages « Bulles », « Exporter » ; annotations Liens, Favoris, Notes, Titres (`.fav-first`). Un seul ouvert à la fois (favorites.js, inchangé).
- « Bulles » (`#bubbles-tab`) : trois groupes, titre en gras dans une colonne, un trait entre eux : « Masquer : » (les cinq cases), « Affichage : » (Lignes 1 · 3 · 5 · Tout, `#lines-slot`), « Voix : » (le bouton des voix, posé par speak.js dans `#voices-slot` ; groupe caché sans serveur local). Nom « Bulles » choisi par Dom : tout s'y applique aux bulles.
- « Exporter » (`#export-tab`) : « Formats : » (.md … .pdf) et « Options : » (Annotations, ZIP, sans les autres versions) ; l'aide des commandes dans l'onglet.
- « Vue : Lecture · Structure » sur la ligne du titre, à droite ; `#plan-bar` ne garde que les outils de la Structure, caché en Lecture. plan.js cherche les pastilles dans le document (plus dans la barre).
- Tests : les cases et boutons des onglets sont ouverts avant usage ; le test « rien ne bouge » mesure maintenant la pastille Vue. Suite : 433 tests.

## 2026.11.21.19 — sommaire et onglet « Bulles » (demande de Dom, 22/11)
- Sommaire : référence = sommaire des articles de Wikipédia (clé MediaWiki `toc`) : Sommaire, Inhaltsverzeichnis, Índice, Indice, Inhoud, Spis treści, Índice (pt-BR), Содержание, 目次, 목차, 目录. Changés : en « index » → « table of contents » (l'index d'un livre est alphabétique), de Übersicht → Inhaltsverzeichnis, nl overzicht → inhoudsopgave (« overzicht » servait aussi à la section Aperçu, « inhoud » au contenu cherché). Gardés : es/it/pt índice/indice, pl spis, ru оглавление (synonyme de содержание), ja/ko/zh.
- Onglet « Bulles » : là où « bulle » ne se dit pas, le mot de Thunderbird pour « affichage » (« Lecture et affichage ») : es Visualización, it Visualizzazione, ru Отображение (au lieu de « Messages »). Le groupe « Affichage : » de ces langues devient « Hauteur : » (Altura, Altezza, Высота), fidèle à sa note « hauteur de chaque bulle, en lignes ».
- Doublons d'étiquettes supprimés (même mot pour deux commandes voisines) : nl « Weergave » (groupe et Vue) → groupe « Hoogte » ; pt « Visualização » → groupe « Exibição » (mot de Thunderbird) ; ja 表示 → Vue « ビュー » (mot de Thunderbird, テーブルビュー). Contrôle : onglet, groupes et Vue distincts dans les 12 langues.

## 2026.11.21.18 — fil principal et sauvegarde vérifiés (Thunderbird, Firefox)
- « Fil » : Thunderbird (`mail/messenger/about3Pane.ftl`) traduit le fil de discussion par conversación, discussione, conversatie, Thema, tópico, тема, 글타래, 话题, wątek : jamais un calque de « fil » (sauf pl). D'où, pour « fil principal » (branche principale d'une conversation) : de Hauptverlauf (au lieu de Hauptfaden), nl hoofdlijn (au lieu de hoofddraad), ja 本筋 (au lieu de メインスレッド, sens informatique). Gardés : es hilo principal, it filo principale, pt fio principal (expressions courantes « hilo / filo / fio da conversa »), pl główny wątek, ru основная ветка, ko 기본 흐름, zh 主线.
- Sauvegarde : Firefox (`browser/browser/places.ftl`) dit Sichern, Copia/respaldar, Salva, Backup, Создать резервную копию, Reservekopie maken, kopia zapasowa, 백업, 备份, バックアップ. Le bouton suivait « enregistrer » en es, pt, ru : désormais « Copia de seguridad de la Biblioteca », « Fazer backup da Biblioteca », « Создать резервную копию Библиотеки », comme le reste de ces catalogues ; nl « Back-up van de Bibliotheek maken ». Renvois au nom du bouton mis à jour.
- Importer : ko 가져오기, zh 导入 conformes à Firefox.

## 2026.11.21.17 — termes alignés sur Firefox (demande de Dom, 22/11)
- Référence : traductions officielles de Firefox (dépôt mozilla-l10n/firefox-l10n, visionneuse PDF `toolkit/toolkit/pdfviewer/viewer.ftl` et assistant d'import `browser/browser/migrationWizard.ftl`) ; Transvision refuse les accès automatiques.
- « Mots entiers » au pluriel dans les 12 langues (Whole words, Ganze Wörter, Palabras completas, Parole intere, Hele woorden, Całe słowa, Palavras completas, Слова целиком, 単語一致, 단어 단위로, 全词匹配).
- « Introuvable dans cette page » : phrase avec majuscule partout ; ja このページには見つかりません.
- Recherche approximative fr : « Moins / Plus de fautes tolérées » (un seul mot avec l'étiquette « Fautes tolérées »).
- Surlignage : de Hervorhebung (Markierung = sélection), pl wyróżnienie (zaznaczenie = sélection et case cochée) ; les autres langues correspondaient déjà à Firefox.
- ja : インポート partout (Firefox n'emploie jamais 取り込む) ; bouton « エクスポートファイルをインポート ».
- Gardés malgré Firefox : ja ハイライト (Firefox 強調, ambigu avec la mise en gras) ; « Notes » (Firefox « Commentaires »).

## 2026.11.21.16 — relecture phrase par phrase des 11 langues (demande de Dom, 22/11, « toutes »)
- Chaque catalogue (929 chaînes) relu en entier ; corrections par langue dans des fichiers `fx_<lang>.py` (outil `/home/claude/work/applyfx.py`, hors dépôt).
- Partout : « ouvrez la Bibliothèque avec l'icône « Claude Library » » remplace « icône du bureau » / « archives » (toutes les variantes : serveur ancien, rubriques en lecture seule, serveur muet) ; « bibliothèque de code » pour verify.lib_missing ; « fichiers audio » pour les sons de lecture (distinct de « voix ») ; noms des boutons de sauvegarde alignés sur web.backup ; options CLI en anglais hors fr (--uninstall, --restore).
- en : orthographe US (canceled…) — attention, la substitution avait aussi renommé la clé `uninstall.cancelled` en anglais : rétablie (test test_i18n).
- es : « equipo », « repositorio » ; it : tutoiement ; nl : vouvoiement « u » ; pt : brésilien ; de : Hauptfaden, Audiodateien ; pl, ru : minuscules pour internet, « pliki audio » / « аудиофайлы ».
- ja : エクスポート partout (plus 書き出し), 音声ファイル, ライブラリ ; ko : 보관함 (plus 아카이브), 라이브러리, 음성 파일, 회고 ; zh : 你 partout (plus 您), 网站 (plus 站点), 存档 (plus 归档), 语音 (plus 声音) pour les voix, 音频文件 pour les sons.
- Non vérifié par des locuteurs natifs ; restent : fr « Rechercher » / « Mot entier » sur la recherche du sommaire ; ja インポート (CLI) / 取り込む (interface).

## 2026.11.21.15 — vocabulaire des 12 langues (demande de Dom, 22/11 : un mot juste par pays, le moins de termes différents)
- Méthode : pour ~22 notions (conversation, bulle, Bibliothèque, sommaire, rubrique, surlignage, sauvegarde, annotation, note, lien, fil, version, supprimé / effacé, pièce jointe, partie, artefact, lecture à voix haute, rechercher, serveur, dossier…), relevé des mots employés dans chaque fichier de langue (`/home/claude/work/gloss.py`, `gloss2.py`, hors dépôt), puis un seul mot par notion et par langue.
- « Bulles » : gardé là où le mot imagé est naturel (fr, en, pl Dymki, pt Balões, ja 吹き出し, ko 말풍선, zh 气泡) ; ailleurs de Sprechblasen, nl Tekstballonnen (plus « bel / bubbel / ballon »), es Mensajes, it Messaggi, ru Сообщения (« Blasen, Bolle, Пузыри » = bulles de savon) ; les 12 chaînes « bulle » alignées sur l'onglet.
- « Suite » de conversations : « fil k sur n » devient « conversation k sur n » (« fil » ne veut plus dire que le fil principal) ; en Series, de Reihe, es/it Serie, nl Reeks, pl Seria, pt Série, ru Серия, ja/ko シリーズ/시리즈, zh 系列 (plus « continuation »).
- Les quatre « Effacer tous les … ? » avec le verbe de leur titre (fr « Retirer » corrigé) ; ru « разговор » → « беседа » partout ; zh 笔记→备注, 批注→注释, 制品→工件, 链接→关联 (liens entre conversations) ; ja 音読→読み上げ, 流れ→スレッド ; nl inhoudsopgave→overzicht ; rubriques (es/it/pt/ja) ; « Rechercher » (en/pt/ko/zh/ja/ru) ; pl/ko surligner.
- Portugais : le fichier mêlait Brésil et Portugal (arquivo / ficheiro, baixar / transferir, tela / ecrã, guardar / salvar, ligação = « appel téléphonique » au Brésil). Choix : portugais du Brésil (la grande majorité des lecteurs) ; « arquivo » = fichier, l'archive = « acervo », liens = « vínculo », guillemets “ ”, gérondif (« Verificando »). ~130 chaînes.
- Espagnol : « ordenador » (Espagne) → « equipo » (compris partout).
- Non fait : relecture phrase par phrase des 929 chaînes de chaque langue par un locuteur natif.

## 2026.11.22.1 — README des 12 langues mis à jour, captures refaites (demande de Dom, 22/11)
- README.fr.md (validé par Dom) : en-tête des conversations en onglets (Bulles : Masquer / Affichage / Voix ; Exporter ; Liens, Favoris, Notes, Titres ; Vue sur la ligne du titre), l'œil, stylo de surlignage près de la sélection, très longues conversations en plusieurs pages, « Ordre : réel · logique » dans la barre de la Structure, boutons de droite en deux cadres ; noms de boutons actuels (Sauvegarder la Bibliothèque, Libérer de la place, Récupérer des annotations) ; chemin d'export claude.ai vérifié sur l'aide d'Anthropic (pas depuis les applications mobiles, lien valable 24 h) ; remerciement à Judson Neer (projet d'origine) dans « Compléments et licence ».
- Les 11 autres README retraduits en entier d'après le français, avec les libellés de chaque fichier de langue (contrôle par script : tous les libellés cités présents) et les choix du 22/11 (anglais américain, portugais du Brésil, italien au tutoiement, néerlandais « u », chinois 你, japonais インポート ; es/it « mensaje / messaggio » pour les bulles, comme l'interface).
- Les 10 captures docs/fr et docs/en refaites (bibliothèque de démonstration : scripts demo.py et shots.py hors dépôt, perdus après la session ; Playwright, fenêtre 1000 px, captures de 832 px, thème clair, HOME factice et « ~ » remis dans la page pour le dossier des téléchargements).

## 2026.11.25.1 — Corrections de sécurité après l'audit Gemini et CodeQL (AF-f3, 25/11)
- renderer.py : la chaîne « copy-label » sortie de la f-string (guillemets réutilisés = erreur de syntaxe sous Python 3.11, la version annoncée). Test : chaque module compile sous python3.11 quand il est présent (les bibliothèques n'y sont pas installées dans le cloud : la suite tourne sous 3.13).
- archive.iter_raw_file : ligne abîmée (JSON faux, pas une paire, clé hors des listes de l'en-tête), gzip tronqué ou abîmé = toujours ValueError. Les clés de listes sont relevées avant de donner l'en-tête (read_raw_file le remplit).
- extras : JSON d'artefact (artifact.json, .files.json, canvas.json) ignoré au-delà de MAX_META (20 Mo) ; extract contrôle en plus de _safe_path que chaque chemin final reste dans le dossier (sinon ValueError, rien d'écrit).
- cdn_cache.public_host : open_https sans ``host`` (bibliothèques des artefacts, polices, redirections) refuse toute adresse dont une IP n'est pas publique (localhost, 127/8, 10/8, 172.16/12, 192.168/16, 100.64/10, liaison locale, réservées, IPv6 locales, IP en clair ou en décimal). esm.sh garde sa règle (ce site seulement). Reste possible : un DNS qui change de réponse entre le contrôle et la connexion (après deux accords de l'utilisateur).
- speech : get-pip.py par open_https, redirections limitées à bootstrap.pypa.io (pas d'empreinte : le fichier change à chaque version de pip, et piper-tts vient ensuite de PyPI sans empreinte).
- Pièces jointes : un type qui pourrait s'exécuter (system.RUNNABLE : .sh, .desktop, .exe, .bat, .ps1, .vbs, .js, .jar, .py…) n'est jamais ouvert ; son dossier l'est, et l'infobulle dit « Fichier exécutable : dossier ouvert par prudence » (web.attachment.folder_opened, 12 langues).
- tests/test_gemini_fixes.py ; contre-épreuves faites sur une copie.
