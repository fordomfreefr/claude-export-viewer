"""Files created by Claude, rebuilt from the tool calls of the export (created.py)."""

from claude_export_viewer import created

ROOT = "00000000-0000-4000-8000-000000000000"
OUT = "/mnt/user-data/outputs/"


def use(i, name, **inp):
    return {"type": "tool_use", "id": i, "name": name, "input": inp}


def result(i, error=False, text="ok"):
    return {"type": "tool_result", "tool_use_id": i, "is_error": error, "content": [{"type": "text", "text": text}]}


def bash(i, command):
    return use(i, "bash_tool", command=command, description="")


def present(i, *paths):
    return use(i, "present_files", filepaths=list(paths))


def conv(*turns):
    """turns: (uuid, parent, blocks) of assistant messages, each after a human message."""
    msgs = []
    for n, (uuid, parent, blocks) in enumerate(turns):
        h = "h-" + uuid
        msgs.append({"uuid": h, "sender": "human", "parent_message_uuid": parent or ROOT,
                     "created_at": f"2026-07-01T10:{n:02d}:00Z", "content": [{"type": "text", "text": "?"}]})
        msgs.append({"uuid": uuid, "sender": "assistant", "parent_message_uuid": h,
                     "created_at": f"2026-07-01T10:{n:02d}:30Z", "content": blocks})
    return {"uuid": "c", "chat_messages": msgs}


def files(raw, uuid):
    return {p.name: p for p in created.reconstruct(raw).get(uuid, [])}


def test_create_in_outputs():
    raw = conv(("a1", None, [use("t1", "create_file", path=OUT + "a.py", file_text="x = 1\n", description=""),
                             result("t1"), present("t2", OUT + "a.py")]))
    f = files(raw, "a1")["a.py"]
    assert (f.text, f.complete, f.path) == ("x = 1\n", True, OUT + "a.py")


def test_edits_then_copy_with_cd_and_redirection():
    raw = conv(("a1", None, [
        use("t1", "create_file", path="/tmp/lancer.py", file_text="a = 1\nb = 2\n"), result("t1"),
        use("t2", "str_replace", path="/tmp/lancer.py", old_str="a = 1", new_str="a = 10"), result("t2"),
        use("t3", "str_replace", path="/tmp/lancer.py", old_str="b = 2", new_str="b = 20"), result("t3"),
        bash("t4", "cd /tmp && cp lancer.py /mnt/user-data/outputs/ 2>/dev/null && ls -la /mnt/user-data/outputs/"),
        result("t4"), present("t5", OUT + "lancer.py")]))
    f = files(raw, "a1")["lancer.py"]
    assert (f.text, f.complete) == ("a = 10\nb = 20\n", True)


def test_each_message_has_its_own_version_heredoc():
    first = [use("t1", "create_file", path=OUT + "LoiBates.bas", file_text="v1\n"), result("t1"),
             present("t2", OUT + "LoiBates.bas")]
    second = [bash("u1", "cat > /mnt/user-data/outputs/LoiBates.bas << 'ENDOFFILE'\nSub v2()\n  x = \"$a\"\nEnd Sub\n"
                         "ENDOFFILE\necho fait"), result("u1"), present("u2", OUT + "LoiBates.bas")]
    raw = conv(("a1", None, first), ("a2", "a1", second))
    assert files(raw, "a1")["LoiBates.bas"].text == "v1\n"
    f = files(raw, "a2")["LoiBates.bas"]
    assert (f.text, f.complete) == ('Sub v2()\n  x = "$a"\nEnd Sub\n', True)


def test_heredoc_written_after_the_tag_and_appended():
    raw = conv(("a1", None, [
        bash("t1", "cat <<'EOF' > /home/claude/n.md\n# Titre\nEOF\ncat >> /home/claude/n.md <<'EOF'\nsuite\nEOF\n"
                   "cp /home/claude/n.md /mnt/user-data/outputs/notes.md"),
        result("t1"), present("t2", OUT + "notes.md")]))
    assert files(raw, "a1")["notes.md"].text == "# Titre\nsuite\n"


def test_unquoted_heredoc_expanded_by_the_shell_is_unknown():
    raw = conv(("a1", None, [bash("t1", "cat > /mnt/user-data/outputs/x.txt << EOF\nnom: $USER\nEOF"),
                             bash("t2", "cat > /mnt/user-data/outputs/y.txt << EOF\nbonjour\nEOF"),
                             present("t3", OUT + "x.txt", OUT + "y.txt")]))
    f = files(raw, "a1")
    assert f["x.txt"].text is None
    assert f["y.txt"].text == "bonjour\n"


def test_branches_stay_apart():
    base = [use("t1", "create_file", path="/home/claude/a.py", file_text="v = 1\n"), result("t1")]
    retry_a = [use("u1", "str_replace", path="/home/claude/a.py", old_str="v = 1", new_str="v = 2"), result("u1"),
               bash("u2", "cp /home/claude/a.py /mnt/user-data/outputs/"), present("u3", OUT + "a.py")]
    retry_b = [bash("w1", "cp /home/claude/a.py /mnt/user-data/outputs/"), present("w2", OUT + "a.py")]
    raw = conv(("a0", None, base), ("a1", "a0", retry_a), ("a2", "a0", retry_b))
    assert files(raw, "a1")["a.py"].text == "v = 2\n"
    assert files(raw, "a2")["a.py"].text == "v = 1\n"


def test_calls_answered_by_an_error_are_skipped():
    raw = conv(("a1", None, [
        use("t1", "create_file", path=OUT + "a.txt", file_text="bon\n"), result("t1"),
        use("t2", "create_file", path=OUT + "a.txt", file_text="raté\n"), result("t2", error=True),
        use("t3", "str_replace", path=OUT + "a.txt", old_str="bon", new_str="faux"), result("t3", error=True),
        present("t4", OUT + "a.txt")]))
    f = files(raw, "a1")["a.txt"]
    assert (f.text, f.complete) == ("bon\n", True)


def test_replacement_that_cannot_be_replayed_marks_incomplete():
    raw = conv(("a1", None, [
        use("t1", "create_file", path=OUT + "a.txt", file_text="x x\n"), result("t1"),
        use("t2", "str_replace", path=OUT + "a.txt", old_str="x", new_str="y"), result("t2"),  # twice: ambiguous
        use("t3", "str_replace", path=OUT + "a.txt", old_str="absent", new_str="z"), result("t3"),
        present("t4", OUT + "a.txt")]))
    f = files(raw, "a1")["a.txt"]
    assert (f.text, f.complete) == ("x x\n", False)


def test_edit_replace_all_and_write_of_claude_code():
    raw = conv(("a1", None, [
        use("t1", "Write", file_path="/home/claude/w/a.txt", content="x x\n"), result("t1"),
        use("t2", "Edit", file_path="/home/claude/w/a.txt", old_string="x", new_string="y", replace_all=True),
        result("t2"), use("t3", "SendUserFile", files=["/home/claude/w/a.txt"], status="normal")]))
    f = files(raw, "a1")["a.txt"]
    assert (f.text, f.complete) == ("y y\n", True)


def test_changes_the_export_does_not_show():
    raw = conv(("a1", None, [
        use("t1", "create_file", path=OUT + "s.py", file_text="a\n"), result("t1"),
        use("t2", "create_file", path=OUT + "t.py", file_text="b\n"), result("t2"),
        use("t3", "create_file", path=OUT + "u.py", file_text="c\n"), result("t3"),
        use("t4", "create_file", path=OUT + "analysis.py", file_text="d\n"), result("t4"),
        use("t4b", "create_file", path=OUT + "data.csv", file_text="ancien\n"), result("t4b"),
        bash("t5", "sed -i 's/a/b/' /mnt/user-data/outputs/s.py"),
        bash("t6", "python3 - << 'EOF'\nopen('/mnt/user-data/outputs/t.py', 'w').write('x')\nEOF"),
        bash("t7", "cd /mnt/user-data/outputs && python3 u.py && python3 -c \"import ast; ast.parse(open('analysis.py').read())\""),
        bash("t8", "python3 gen.py > /mnt/user-data/outputs/data.csv"),
        present("t9", OUT + "s.py", OUT + "t.py", OUT + "u.py", OUT + "analysis.py", OUT + "data.csv")]))
    f = files(raw, "a1")
    assert (f["s.py"].text, f["s.py"].complete) == ("a\n", False)
    assert (f["t.py"].text, f["t.py"].complete) == ("b\n", False)
    assert (f["u.py"].text, f["u.py"].complete) == ("c\n", True)  # running a script does not change it
    assert (f["analysis.py"].text, f["analysis.py"].complete) == ("d\n", True)  # reading it neither
    assert f["data.csv"].text is None


def test_copy_of_an_unknown_file_rm_and_mv():
    raw = conv(("a1", None, [
        use("t1", "create_file", path=OUT + "a.ods", file_text="faux\n"), result("t1"),
        bash("t2", "cp /home/claude/vrai.ods /mnt/user-data/outputs/a.ods"),
        use("t3", "create_file", path="/home/claude/b.md", file_text="B\n"), result("t3"),
        bash("t4", "mv /home/claude/b.md /mnt/user-data/outputs/c.md"),
        use("t5", "create_file", path=OUT + "d.md", file_text="D\n"), result("t5"),
        bash("t6", "rm -f /mnt/user-data/outputs/d.md"),
        present("t7", OUT + "a.ods", OUT + "c.md", OUT + "d.md", "/home/claude/b.md")]))
    f = files(raw, "a1")
    assert f["a.ods"].text is None
    assert f["c.md"].text == "B\n"
    assert f["d.md"].text is None
    assert f["b.md"].text is None


def test_folder_copied_and_links_in_the_text():
    raw = conv(("a1", None, [
        use("t1", "create_file", path="/home/claude/proj/src/m.py", file_text="m\n"), result("t1"),
        bash("t2", "cp -r /home/claude/proj /mnt/user-data/outputs/"),
        {"type": "text", "text": "[Voir](computer:///mnt/user-data/outputs/proj/src/m.py)"}]))
    f = files(raw, "a1")["m.py"]
    assert (f.text, f.path) == ("m\n", OUT + "proj/src/m.py")


def test_version_handed_over_is_the_one_at_that_moment():
    raw = conv(("a1", None, [
        use("t1", "create_file", path=OUT + "a.txt", file_text="1\n"), result("t1"), present("t2", OUT + "a.txt"),
        use("t3", "create_file", path="/home/claude/brouillon.txt", file_text="?\n"), result("t3")]))
    assert list(files(raw, "a1")) == ["a.txt"]  # only what is handed over
    assert files(raw, "a1")["a.txt"].text == "1\n"


def test_human_messages_and_conversations_without_tools():
    raw = {"uuid": "c", "chat_messages": [{"uuid": "h", "sender": "human", "content": [
        present("t", OUT + "a.txt")]}, {"uuid": "a", "sender": "assistant", "content": "pas une liste"}]}
    assert created.reconstruct(raw) == {}


def test_versions_numbered_by_distinct_content_in_message_order():
    v1 = [use("t1", "create_file", path=OUT + "L.bas", file_text="v1\n"), present("t2", OUT + "L.bas")]
    again = [present("u1", OUT + "L.bas")]  # handed over again, unchanged: same version
    v2 = [bash("w1", "cat > /mnt/user-data/outputs/L.bas << 'E'\nv2\nE"), present("w2", OUT + "L.bas", OUT + "x.png")]
    raw = conv(("a1", None, v1), ("a2", "a1", again), ("a3", "a2", v2))
    got = [(files(raw, k)["L.bas"].version, files(raw, k)["L.bas"].versions) for k in ("a1", "a2", "a3")]
    assert got == [(1, 2), (1, 2), (2, 2)]
    assert (files(raw, "a3")["x.png"].version, files(raw, "a3")["x.png"].versions) == (0, 0)
