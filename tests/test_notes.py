import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engine import notes as n

EX = pathlib.Path(__file__).resolve().parents[1] / "example"


def test_detects_planted_error_first():
    # Lernprotokoll 13.09.: erst einen Treffer erzeugen, dann messen
    groups, errors = n.load_notes(EX / "notes", {"notes": [{"group": "", "items": [{"slug": "missing"}]}]})
    assert errors and "missing.md" in errors[0]
    assert groups == [{"group": "", "items": []}]


def test_frontmatter_lists_and_strings():
    meta, body = n.split_frontmatter('---\ntitle: "Quoted"\ncovers: [1.1, "svc:x", concept:y]\ntags: []\n---\n# H\ntext\n')
    assert meta["title"] == "Quoted"
    assert meta["covers"] == ["1.1", "svc:x", "concept:y"]
    assert meta["tags"] == []
    assert body == "# H\ntext\n"
    assert n.note_covers(meta) == ["1.1", "svc:x", "concept:y"]


def test_note_without_frontmatter():
    meta, body = n.split_frontmatter("# Only heading\n\ntext")
    assert meta == {} and body.startswith("# Only heading")
    assert n.note_covers(meta) == []


def test_covers_scalar_becomes_list():
    assert n.note_covers({"covers": "1.1"}) == ["1.1"]
    assert n.note_covers({"covers": ""}) == []


def test_render_keeps_mermaid_and_tables():
    html = n.render("## H\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert '<pre class="mermaid">flowchart LR\n  A --&gt; B\n</pre>' in html
    assert "<table>" in html and "<h2>H</h2>" in html
    assert "EXAMKITMERMAID" not in html


def test_render_wikilinks():
    html = n.render("See [[../x/other|Other]] and [[intro#What a basic is]] and [[intro]].")
    assert "Other" in html and "[[" not in html and 'note-other' not in html
    assert 'href="#note-intro"' in html


def test_load_notes_default_is_every_file_sorted(tmp_path):
    (tmp_path / "b.md").write_text("---\ntitle: B\n---\n# B\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("# A heading\n", encoding="utf-8")
    groups, errors = n.load_notes(tmp_path, {})
    assert errors == []
    assert [i["slug"] for i in groups[0]["items"]] == ["a", "b"]
    assert groups[0]["items"][0]["title"] == "A heading"
    assert groups[0]["items"][1]["title"] == "B"


def test_load_notes_from_example_config():
    exam = json.loads((EX / "exam.json").read_text(encoding="utf-8"))
    groups, errors = n.load_notes(EX / "notes", exam)
    assert errors == []
    assert groups[0]["group"] == "Reading"
    item = groups[0]["items"][0]
    assert item["slug"] == "intro" and item["title"] == "Intro" and item["subtitle"] == "The only note"
    assert item["covers"] == ["1.1"]
    assert 'class="mermaid"' in item["html"] and "<h2>What a basic is</h2>" in item["html"]


def test_load_notes_bad_config_shapes():
    _, errors = n.load_notes(EX / "notes", {"notes": "intro"})
    assert errors == ["exam.notes: must be a list of groups"]
    _, errors = n.load_notes(EX / "notes", {"notes": [{"group": "G", "items": [{"title": "no slug"}, "x"]}]})
    assert len(errors) == 2 and all("slug" in e for e in errors)


def test_frontmatter_survives_crlf():
    meta, body = n.split_frontmatter("---\r\ntitle: X\r\ncovers: [1.1]\r\n---\r\n# X\r\n")
    assert meta["title"] == "X" and n.note_covers(meta) == ["1.1"]
    assert body.startswith("# X")


def test_covers_duplicates_are_dropped():
    assert n.note_covers({"covers": ["1.1", "1.1", "svc:x"]}) == ["1.1", "svc:x"]
