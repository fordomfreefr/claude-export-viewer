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
- **`models.py`** — tolerant Pydantic v2 models: unknown keys and `null`s are
  ignored, unparseable dates become `None`, unknown or broken content blocks
  become `UnknownContent`, broken items are dropped. `parse_message`,
  `is_empty_conversation`.
- **`archive.py`** — cumulative archive. Conversations are merged by uuid and
  never deleted; one missing from the latest export (or emptied) is marked
  "supprimée sur claude.ai" (recomputed at every run). Messages that vanished
  from a conversation are kept under `tree.EXTRA_KEY` with the date of the last
  export holding them. An older export never overwrites a newer version.
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
- **`renderer.py`** — one `ChatMessage` → HTML. mistune 3 with
  `_HighlightRenderer` (Pygments; code without a language stays plain text),
  safe links, "Copier" button on code blocks.
- **`math_plugin.py`** — mistune plugin protecting `$…$`, `$$…$$`, `\(…\)`,
  `\[…\]` (independent of `mistune.plugins.math`); KaTeX 0.16.47 bundled in
  `static/katex/` (copied under `conversations/` so file:// font loading works)
  renders them lazily via `render.js`, and all of them before printing.
- **`markdown_export.py`** — Markdown of a conversation (main branch, other
  versions as quote blocks with italic labels; no thinking/tool calls;
  `versions=False` for the main thread only). Both variants are embedded as JSON
  in each page; `static/export.js` builds the .md file and drives the .pdf
  (browser print window) and .odt/.docx buttons.
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
  existing name) / delete) each conversation gets a menu, completed only when it
  opens so that a thousand menus stay cheap; `admin.js` hands the token over with
  the `cev-admin` event, and `topics.js` sends `cev-topics` after each change so
  that the index filters again. The server never answers 304 (file dates have a
  one-second precision: a file rewritten within the same second would look
  unchanged).
- **`settings.py`** — `archive/settings.json`: the downloads folder chosen by
  the user (index page, `--telechargements`), searched before the system's;
  ignored when it no longer exists (USB key removed).
- **`system.py`** — what differs between Linux, macOS and Windows: `py` vs
  `python3` and quoting of the commands shown in the pages, `python.exe` for
  child processes even under `pythonw.exe`, `CREATE_NO_WINDOW`, console output
  that never stops on an unknown character, Windows shell folders from the
  registry, install hints for the libraries and Pandoc. Windows support has not
  been run on Windows; `tests/test_windows.py` simulates it on Linux.
- **`desktop.py`** — launcher "Archives Claude" (`--installer-icone`):
  freedesktop entry on Linux; on Windows, `.lnk` shortcuts (Start menu, desktop)
  written by PowerShell/WScript.Shell with values passed in environment
  variables, target `pythonw.exe`, icon `static/icon.ico` (rendered from
  `icon.svg`).
- **`dates.py`** — ISO parsing, UTC/local conversions.
- **`i18n.py`** + `i18n/<lang>.json` + `static/i18n.js` — every visible text
  is a key (`cli.*` console, `warn.*`, `fetch.*`, `server.*`, `office.*`,
  `web.*` pages, `md.*` Markdown labels, `fmt.*` date/number patterns; plural
  texts are objects of CLDR categories). English is the reference and fallback.
  The console uses the system language (`CEV_LANG`, `LANGUAGE`, `LC_ALL`,
  `LC_MESSAGES`, `LANG`) or `--langue`. Pages are written in that language with
  each text marked (`data-i18n`, `data-i18n-args`, `data-i18n-attr`,
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
`frames`. Only conversations, projects (names) and users are used.

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
