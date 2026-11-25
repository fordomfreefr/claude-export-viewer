"""Prototype (21/11), outside CEV: read a conversations.json whose one conversation is bigger than the memory allowed,
message by message, and store it in pieces (gzipped JSONL of ~2 MB) with a small index in memory.

    python3 proto_chunks.py gen FILE SIZE_MB        # a file: small conv, one huge conv, small conv
    python3 proto_chunks.py read FILE OUT_DIR        # streamed reading + pieces; prints peak memory
    python3 proto_chunks.py whole FILE               # the current way (each conversation decoded whole), for comparison
"""
import gzip, hashlib, json, os, resource, sys, time
from pathlib import Path

CHUNK = 1 << 20
PIECE = 2 << 20  # bytes of messages per piece
ROOT = "00000000-0000-4000-8000-000000000000"
dec = json.JSONDecoder()


class Reader:
    """A text file read by blocks: buf/pos, refilled on demand (as loader._skip_ws)."""
    def __init__(self, f):
        self.f, self.buf, self.pos = f, "", 0

    def more(self) -> bool:
        chunk = self.f.read(CHUNK)
        if not chunk:
            return False
        self.buf, self.pos = self.buf[self.pos:] + chunk, 0
        return True

    def peek(self) -> str:
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos] in " \t\r\n":
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if not self.more():
                raise json.JSONDecodeError("fin de fichier inattendue", "", 0)

    def expect(self, c: str) -> None:
        if self.peek() != c:
            raise json.JSONDecodeError(f"'{c}' attendu", self.buf, self.pos)
        self.pos += 1

    def value(self):
        """One JSON value decoded whole (a message, a title...): the buffer grows until it is complete."""
        self.peek()
        while True:
            try:
                v, end = dec.raw_decode(self.buf, self.pos)
                # a number at the very end of the buffer may be cut: read on to be sure
                if end == len(self.buf) and self.more():
                    continue
                self.pos = end
                return v
            except json.JSONDecodeError:
                if not self.more():
                    raise

    def items(self):
        """The elements of an array, one by one (the '[' read here), strict as loader._iter_array."""
        self.expect("[")
        if self.peek() == "]":
            self.pos += 1
            return
        while True:
            yield self.value()
            c = self.peek()
            self.pos += 1
            if c == "]":
                return
            if c != ",":
                raise json.JSONDecodeError("',' attendue", self.buf, self.pos)

    def conversation(self, streamed=("chat_messages",)):
        """One conversation object: ("meta", key, value) for its small fields, ("message", m) one by one."""
        self.expect("{")
        if self.peek() == "}":
            self.pos += 1
            return
        while True:
            key = self.value()
            self.expect(":")
            if key in streamed and self.peek() == "[":
                for m in self.items():
                    yield ("message", m)
            else:
                yield ("meta", key, self.value())
            c = self.peek()
            self.pos += 1
            if c == "}":
                return
            if c != ",":
                raise json.JSONDecodeError("',' attendue", self.buf, self.pos)


class Pieces:
    """Messages written in pieces; in memory only the index: uuid -> (parent, piece number)."""
    def __init__(self, folder: Path):
        self.folder, self.index, self.n, self.size, self.out = folder, {}, 0, 0, None
        folder.mkdir(parents=True, exist_ok=True)

    def add(self, m: dict) -> None:
        line = json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n"
        if self.out is None or self.size >= PIECE:
            if self.out:
                self.out.close()
            self.n += 1
            self.out, self.size = gzip.open(self.folder / f"part-{self.n:05d}.jsonl.gz", "wt", encoding="utf-8"), 0
        self.out.write(line)
        self.size += len(line)
        self.index[m["uuid"]] = (m.get("parent_message_uuid"), self.n)

    def close(self) -> None:
        if self.out:
            self.out.close()


def gen(path: Path, size_mb: int) -> None:
    """Written as it goes (never whole in memory); prints the sha256 of the messages of the huge conversation."""
    h, text = hashlib.sha256(), "éléphant à côté de la tour " * 380  # ~10 KB with accents
    with path.open("w", encoding="utf-8") as f:
        small = {"uuid": "s1", "name": "petite", "chat_messages": [{"uuid": "s1-0", "parent_message_uuid": ROOT, "text": "x"}]}
        f.write("[" + json.dumps(small, ensure_ascii=False) + ',\n{"uuid": "big", "name": "énorme", "chat_messages": [')
        parent, i, written = ROOT, 0, 0
        while written < size_mb << 20:
            m = {"uuid": f"m{i}", "parent_message_uuid": parent, "sender": "human" if i % 2 == 0 else "assistant",
                 "created_at": "2026-01-01T00:00:00Z", "content": [{"type": "text", "text": f"{i} {text}"}]}
            s = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
            h.update(s.encode("utf-8"))
            f.write(("," if i else "") + s)
            written += len(s.encode("utf-8"))
            parent, i = f"m{i}", i + 1
        f.write('], "updated_at": "2026-01-01T00:00:00Z"},\n' + json.dumps({**small, "uuid": "s2"}, ensure_ascii=False) + "]\n")
    print(f"généré : {path.stat().st_size >> 20} Mo, {i} messages dans la grande conversation, sha256 {h.hexdigest()[:16]}")


def read(path: Path, out: Path) -> None:
    t0, h = time.time(), hashlib.sha256()
    with path.open(encoding="utf-8") as f:
        r = Reader(f)
        r.expect("[")
        n = 0
        while r.peek() != "]":
            meta, pieces = {}, None
            for ev in r.conversation():
                if ev[0] == "meta":
                    meta[ev[1]] = ev[2]
                else:
                    if pieces is None:
                        pieces = Pieces(out / f"conv-{n}")
                    pieces.add(ev[1])
                    if meta.get("uuid") == "big":
                        h.update(json.dumps(ev[1], ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if pieces:
                pieces.close()
                # the main path rebuilt from the index alone (parents), as the page would need it
                last, depth = next(reversed(pieces.index)), 0
                while last in pieces.index:
                    last, depth = pieces.index[last][0], depth + 1
                print(f"  {meta.get('name')} : {len(pieces.index)} messages, {pieces.n} morceaux, fil principal {depth}")
            n += 1
            if r.peek() == ",":
                r.pos += 1
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss >> 10
    print(f"lu en {time.time() - t0:.0f} s ; mémoire maximale du processus {peak} Mo ; sha256 {h.hexdigest()[:16]}")


def whole(path: Path) -> None:
    sys.path.insert(0, "/home/claude/cev/claude-export-viewer/src")
    from claude_export_viewer import loader
    loader.MAX_ELEMENT = 1 << 40  # the cap of 2026.11.21.4 out of the way: the current way itself is measured
    t0 = time.time()
    with path.open(encoding="utf-8") as f:
        n = sum(1 for _ in loader.iter_json_items(f))
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss >> 10
    print(f"lecture actuelle : {n} conversations en {time.time() - t0:.0f} s ; mémoire maximale {peak} Mo")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "gen":
        gen(Path(sys.argv[2]), int(sys.argv[3]))
    elif cmd == "read":
        read(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        whole(Path(sys.argv[2]))
