"""Files created by Claude, rebuilt from the export.

Claude writes files in its workspace with tools whose calls are in the export, input
included: ``create_file`` / ``Write`` (whole content), ``str_replace`` / ``Edit`` (one
replacement), and shell commands (``bash_tool`` / ``Bash``): ``cat > f << 'EOF'``,
``cp``, ``mv``, ``rm``. Replaying them along the branch of a message gives the content
each file had at the end of that message, so every file the message hands over
(``present_files``, ``SendUserFile``, ``/mnt/user-data/outputs/…`` links) can be shown with
the exact version of that message.

What the export does not show (a file written by a program, ``sed -i``, a redirection of a
command's output…) is never guessed:

- a file whose whole content comes from such a command is unknown (``text`` None);
- a known file changed afterwards by such a command, or by a replacement that cannot be
  replayed, keeps its last known content with ``complete`` False.

A call answered by an error on claude.ai changed nothing and is skipped.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import tree

HOME = "/home/claude"
OUTPUTS = "/mnt/user-data/outputs/"
TRACE: Any = None  # for diagnosis: called with (date, operation, path, detail) at each step
_now = [""]


def _t(op: str, path: str | None, detail: Any = "") -> None:
    if TRACE is not None:
        TRACE(_now[0], op, path, detail)


LINK = re.compile(r"/mnt/user-data/outputs/[^\s\"'<>|()\[\]`]+\.[A-Za-z0-9]{1,8}")


@dataclass(frozen=True)
class _State:
    text: str
    complete: bool = True


@dataclass(frozen=True)
class Presented:
    """A file handed over by a message, with its content at the end of that message."""

    name: str
    path: str
    text: str | None  # None: content not in the export
    complete: bool  # False: changed afterwards in a way the export does not show
    version: int = 0  # n-th distinct content of that name in the conversation (from 1; 0 without content)
    versions: int = 0  # distinct contents of that name in the conversation


def language(name: str) -> str:
    """Pygments name of the language of a file, from its name ("" if unknown)."""
    return _language(os.path.basename(name))  # Pygments only looks at the base name


@functools.lru_cache(maxsize=4096)  # each lookup tries every pattern of every lexer (slow, PT-m6)
def _language(name: str) -> str:
    try:
        from pygments.lexers import find_lexer_class_for_filename
        cls = find_lexer_class_for_filename(name)
    except Exception:  # noqa: BLE001
        return ""
    return cls.aliases[0] if cls is not None and cls.aliases else ""


# --- paths -----------------------------------------------------------------------


def _norm(path: str, cwd: str = HOME) -> str:
    path = (path or "").strip()
    if path.startswith("computer://"):
        path = path[len("computer://"):]
    if path == "~" or path.startswith("~/"):
        path = HOME + path[1:]
    if not path.startswith("/"):
        path = cwd.rstrip("/") + "/" + path
    parts: list[str] = []
    for p in path.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
        else:
            parts.append(p)
    return "/" + "/".join(parts)


def _name(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


# --- shell commands --------------------------------------------------------------

_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_REDIRECT = re.compile(r"^(\d*|&)(>>?)(.*)$")  # >f, >>f, 2>f, &>f, 2>&1
_SPLIT = re.compile(r"&&|\|\||;|\|")
_READERS = {"cat", "head", "tail", "less", "wc", "ls", "grep", "diff", "file", "stat", "md5sum",
            "sha256sum", "echo", "printf", "test", "[", "du", "od", "xxd", "cmp", "sort", "uniq"}


def _lines_with_heredocs(command: str) -> list[tuple[str, str | None, bool]]:
    """(line, here-document body or None, body taken literally) for each command line."""
    out: list[tuple[str, str | None, bool]] = []
    lines = command.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEREDOC.search(line)
        i += 1
        if not m:
            out.append((line, None, True))
            continue
        dash, quote, tag = m.groups()
        body: list[str] = []
        while i < len(lines) and (lines[i].lstrip("\t") if dash else lines[i]) != tag:
            body.append(lines[i].lstrip("\t") if dash else lines[i])
            i += 1
        i += 1  # the closing tag
        text = "\n".join(body) + "\n" if body else ""
        literal = bool(quote) or not re.search(r"[$`\\]", text)  # unquoted tag: the shell expands $…
        out.append((line, text, literal))
    return out


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return segment.split()


class _Shell:
    def __init__(self, fs: dict[str, _State | None]) -> None:
        self.fs = fs
        self.cwd = HOME

    def run(self, command: str) -> None:
        for line, body, literal in _lines_with_heredocs(command):
            for segment in _SPLIT.split(line):
                has_doc = body is not None and _HEREDOC.search(segment) is not None
                self._segment(segment, body if has_doc else None, literal)

    # one simple command
    def _segment(self, segment: str, body: str | None, literal: bool) -> None:
        _t("bash", None, segment.strip())
        segment = _HEREDOC.sub(" ", segment)
        words = _words(segment)
        if not words:
            return
        args: list[str] = []
        writes: list[tuple[str, bool]] = []  # (path, append)
        k = 0
        while k < len(words):
            w = words[k]
            m = _REDIRECT.match(w)
            if m:
                target = m.group(3)
                if not target and k + 1 < len(words):
                    k += 1
                    target = words[k]
                if target and not target.startswith("&") and target != "/dev/null":
                    writes.append((_norm(target, self.cwd), m.group(2) == ">>"))
                k += 1
                continue
            args.append(w)
            k += 1
        if not args:
            for path, append in writes:
                self._unknown(path, append)
            return
        cmd = args[0].rsplit("/", 1)[-1]
        if cmd == "sudo" and len(args) > 1:
            args = args[1:]
            cmd = args[0]
        if cmd == "cd":
            self.cwd = _norm(args[1] if len(args) > 1 else HOME, self.cwd)
            return
        if cmd == "cat" and writes:
            sources = [a for a in args[1:] if not a.startswith("-")]
            if body is not None and not sources:
                content = body if literal else None
            else:
                states = [self.fs.get(_norm(s, self.cwd)) for s in sources]
                content = None if not states or any(s is None or not s.complete for s in states) else \
                    "".join(s.text for s in states if s)
            for path, append in writes:
                self._write(path, content, append)
            return
        if cmd in ("cp", "mv", "install"):
            self._copy(cmd, args[1:])
        elif cmd == "rm":
            for a in args[1:]:
                if not a.startswith("-"):
                    for path in self._matching(_norm(a, self.cwd), tree=True):
                        self.fs.pop(path, None)
                        _t("rm", path)
        elif cmd == "tee":
            for a in args[1:]:
                if not a.startswith("-"):
                    self._unknown(_norm(a, self.cwd), "-a" in args)
        elif cmd == "sed" and any(a.startswith("-i") or a == "--in-place" for a in args[1:]):
            for a in args[1:]:
                p = _norm(a, self.cwd)
                if p in self.fs:
                    self._changed(p)
        elif cmd not in _READERS:
            self._maybe_changed(segment, body)
        for path, append in writes:
            self._unknown(path, append)

    def _matching(self, pattern: str, tree: bool = False) -> list[str]:
        """Known paths matched by a shell pattern (or under that folder)."""
        if any(c in pattern for c in "*?["):
            rx = re.compile(re.escape(pattern).replace(r"\*", "[^/]*").replace(r"\?", "[^/]"))
            return [p for p in self.fs if rx.fullmatch(p) or (tree and any(rx.fullmatch(p[:i]) for i in _slashes(p)))]
        return [p for p in self.fs if p == pattern or (tree and p.startswith(pattern.rstrip("/") + "/"))]

    def _copy(self, cmd: str, rest: list[str]) -> None:
        target_dir = None
        operands: list[str] = []
        k = 0
        while k < len(rest):
            a = rest[k]
            if a in ("-t", "--target-directory") and k + 1 < len(rest):
                target_dir = rest[k + 1]
                k += 2
                continue
            if a.startswith("--target-directory="):
                target_dir = a.split("=", 1)[1]
            elif not a.startswith("-"):
                operands.append(a)
            k += 1
        if target_dir is None:
            if len(operands) < 2:
                return
            dst_arg, sources = operands[-1], operands[:-1]
        else:
            dst_arg, sources = target_dir, operands
        dst = _norm(dst_arg, self.cwd)
        into_dir = (target_dir is not None or len(sources) > 1 or dst_arg.endswith("/") or dst + "/" == OUTPUTS
                    or any(p.startswith(dst + "/") for p in self.fs) or "." not in _name(dst))
        for s in sources:
            src = _norm(s, self.cwd)
            files = self._matching(src, tree=True)
            if not files:  # a file the export does not show: whatever was at the target is unknown now
                self._unknown(dst + "/" + _name(src) if into_dir else dst, False)
                continue
            for f in files:
                if f == src or not f.startswith(src.rstrip("/") + "/"):
                    target = dst + "/" + _name(f) if into_dir else dst
                else:  # a folder copied: keep the layout under it
                    base = dst + "/" + _name(src) if into_dir and _name(src) != _name(dst) else dst
                    target = base + f[len(src.rstrip("/")):]
                self.fs[target] = self.fs[f]
                _t(cmd, target, f)
                if cmd == "mv" and target != f:
                    self.fs.pop(f, None)

    def _write(self, path: str, content: str | None, append: bool) -> None:
        _t("cat >>" if append else "cat >", path, None if content is None else len(content.encode()))
        if content is None:
            self._unknown(path, append)
            return
        if append:
            old = self.fs.get(path)
            if old is None:
                self.fs[path] = None if path in self.fs else _State(content)
                return
            self.fs[path] = _State(old.text + content, old.complete)
        else:
            self.fs[path] = _State(content)

    def _unknown(self, path: str, append: bool) -> None:
        _t("écrit par une commande (contenu inconnu)", path)
        if append and self.fs.get(path) is not None:
            self._changed(path)
        else:
            self.fs[path] = None

    def _changed(self, path: str) -> None:
        _t("changé par une commande (incomplet)", path)
        old = self.fs.get(path)
        if old is not None:
            self.fs[path] = _State(old.text, False)

    def _maybe_changed(self, segment: str, body: str | None) -> None:
        """A program (python, node, soffice…) may change a known file it names: from then on that
        file is incomplete. Running a file is not changing it, so only a name followed or preceded
        by a sign of writing counts."""
        text = segment + "\n" + (body or "")
        if not re.search(r"""open\(|write|save|\.to_|replace\(|['"][wa]\+?['"]|shutil|copy|rename|unlink|remove""", text):
            return
        for path, state in list(self.fs.items()):
            if state is not None and _name(path) in text:
                for m in re.finditer(re.escape(_name(path)), text):
                    around = text[max(0, m.start() - 160): m.end() + 160]
                    if re.search(r"""open\([^)]*,\s*(mode\s*=\s*)?['"][wax]|write|save|\.to_\w+\(|shutil|copy|rename|unlink|remove""", around):
                        self._changed(path)
                        break


def _slashes(p: str) -> list[int]:
    return [i for i, c in enumerate(p) if c == "/" and i > 0]


# --- replay ----------------------------------------------------------------------


def _input(block: dict[str, Any]) -> dict[str, Any]:
    inp = block.get("input")
    return inp if isinstance(inp, dict) else {}


def _replay(blocks: list[Any], fs: dict[str, _State | None]) -> dict[str, _State | None]:
    """Apply the tool calls of one message to ``fs``; returns the paths it hands over, each with
    its content when it was handed over."""
    errors = {b.get("tool_use_id") for b in blocks
              if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error") and b.get("tool_use_id")}
    shell = _Shell(fs)
    presented: dict[str, _State | None] = {}

    def present(paths: list[str]) -> None:
        for p in paths:
            presented.pop(p, None)  # the last time it is handed over sets its place and version
            presented[p] = fs.get(p)
            _t("présenté", p, presented[p])

    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            present([_norm(p) for p in LINK.findall(str(b.get("text") or ""))])
            continue
        if b.get("type") != "tool_use":
            continue
        name, inp = b.get("name"), _input(b)
        if name in ("present_files", "SendUserFile"):
            paths = inp.get("filepaths") if name == "present_files" else inp.get("files")
            present([_norm(p) for p in paths or [] if isinstance(p, str)])
        if b.get("id") and b.get("id") in errors:
            _t("erreur sur claude.ai, ignoré : " + str(name), str(inp.get("path") or inp.get("file_path") or ""))
            continue
        if name in ("create_file", "Write"):
            path = inp.get("path") if name == "create_file" else inp.get("file_path")
            text = inp.get("file_text") if name == "create_file" else inp.get("content")
            if isinstance(path, str) and path and isinstance(text, str):
                fs[_norm(path)] = _State(text)
                _t(name, _norm(path), len(text.encode()))
        elif name in ("str_replace", "Edit"):
            path = inp.get("path") if name == "str_replace" else inp.get("file_path")
            old = inp.get("old_str") if name == "str_replace" else inp.get("old_string")
            new = inp.get("new_str") if name == "str_replace" else inp.get("new_string")
            if not isinstance(path, str) or not isinstance(old, str) or not old:
                continue
            p = _norm(path)
            state = fs.get(p)
            if state is None:
                continue
            n = state.text.count(old)
            if n == 1 or (n > 1 and inp.get("replace_all") is True):
                fs[p] = _State(state.text.replace(old, new if isinstance(new, str) else ""), state.complete)
                _t(name, p, "rejoué")
            else:
                fs[p] = _State(state.text, False)
                _t(name, p, f"NON rejoué : texte à remplacer trouvé {n} fois")
        elif name in ("bash_tool", "Bash"):
            cmd = inp.get("command")
            if isinstance(cmd, str):
                shell.run(cmd)
    return presented


def _signature() -> str:
    h = hashlib.sha256()
    for f in ("created.py", "tree.py"):
        h.update((Path(__file__).parent / f).read_bytes())
    return "created:" + h.hexdigest()[:16]


def reconstruct_kept(raw: dict[str, Any], key: str) -> dict[str, list[Presented]]:
    """:func:`reconstruct`, kept in the cache of the coloured code from one build to the next
    (``key``: what identifies the content of ``raw``, its hashes in the archive; PT-m6)."""
    from . import codecache
    sig = _signature()
    kept = codecache.get(sig, key)
    if kept is not None:
        try:
            return {k: [Presented(**p) for p in ps] for k, ps in json.loads(kept).items()}
        except (ValueError, TypeError):
            pass
    out = reconstruct(raw)
    codecache.put(sig, key, json.dumps({k: [dataclasses.asdict(p) for p in ps] for k, ps in out.items()},
                                       ensure_ascii=False))
    return out


def reconstruct(raw: dict[str, Any]) -> dict[str, list[Presented]]:
    """For each message (by ``tree.message_key``) handing over files, those files as they were
    at the end of that message, along its own branch."""
    items = tree.items_from_raw(raw)
    roots = tree._link(items)
    out: dict[str, list[Presented]] = {}
    stack: list[tuple[tree.Item, dict[str, _State | None]]] = [(r, {}) for r in reversed(roots)]
    when: dict[str, tuple[str, int]] = {}
    while stack:
        item, fs_in = stack.pop()
        when[item.key] = (item.created, item.order)
        fs = dict(fs_in)  # states are immutable: a shallow copy keeps the branches apart
        msg = item.payload if isinstance(item.payload, dict) else {}
        _now[0] = str(msg.get("created_at") or "")[:16].replace("T", " ")
        presented = _replay(msg.get("content") or [], fs) if msg.get("sender") == "assistant" else []
        if presented:
            out[item.key] = [Presented(_name(p), p, s.text if s else None, bool(s and s.complete))
                             for p, s in presented.items()]
        for child in reversed(item.children):
            stack.append((child, fs))
    return _numbered(out, when)


def _numbered(out: dict[str, list[Presented]], when: dict[str, tuple[str, int]]) -> dict[str, list[Presented]]:
    """Version numbers: the distinct contents of each name, in the order of the messages."""
    seen: dict[str, list[str]] = {}
    for key in sorted(out, key=lambda k: when.get(k, ("", 0))):
        for p in out[key]:
            if p.text is not None and p.text not in seen.setdefault(p.name, []):
                seen[p.name].append(p.text)
    return {key: [replace(p, version=seen[p.name].index(p.text) + 1, versions=len(seen[p.name]))
                  if p.text is not None else p for p in places]
            for key, places in out.items()}
