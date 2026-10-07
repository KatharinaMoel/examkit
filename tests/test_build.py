import json, pathlib, re, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
EX = ROOT / "example"
BUILD_PY = ROOT / "engine" / "build.py"
TEMPLATE = ROOT / "engine" / "template" / "index.html"


def build(exam_dir, *args):
    return subprocess.run([sys.executable, str(BUILD_PY), str(exam_dir), *args],
                          capture_output=True, text=True)


def copy_example(tmp_path):
    dst = tmp_path / "ex"
    shutil.copytree(EX, dst, ignore=shutil.ignore_patterns("build"))
    return dst


def edit_cards(exam_dir, fn):
    f = exam_dir / "cards" / "basics.json"
    cards = json.loads(f.read_text(encoding="utf-8"))
    fn(cards)
    f.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")


def edit_exam(exam_dir, fn):
    f = exam_dir / "exam.json"
    exam = json.loads(f.read_text(encoding="utf-8"))
    fn(exam)
    f.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")


def embedded(html, script_id):
    m = re.search(rf'<script id="{script_id}" type="application/json">(.*?)</script>', html, re.S)
    assert m, script_id
    return json.loads(m.group(1))


def outputs(exam_dir):
    return [p for p in (exam_dir / "build" / "index.html", exam_dir / "build" / "build.json") if p.exists()]


def test_check_only_writes_nothing(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex, "--check")
    assert r.returncode == 0, r.stderr
    assert outputs(ex) == []


def test_build_embeds_cards_config_and_manifest(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    for ph in ("CONFIG", "KARTEN", "PLAN", "LOOKUP", "BUILD"):
        assert f"/*{ph}*/" not in html
    cards = embedded(html, "cards")
    assert "ex-basic-def" in {c["id"] for c in cards}
    assert embedded(html, "config")["storage_key"] == "examkit-example-v1"
    assert embedded(html, "lookup") is None
    m = json.loads((ex / "build" / "build.json").read_text())
    assert m["cards"] == 3 and m["model_cards"] == 1 and m["exam_id"] == "example"
    assert embedded(html, "build")["cards"] == 3


def test_model_marker_is_wired_for_model_cards(tmp_path):
    ex = copy_example(tmp_path)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert any(c["ctx_src"] == "model" for c in embedded(html, "cards"))
    assert "=== 'model'" in TEMPLATE.read_text(encoding="utf-8")


def test_hostile_card_text_round_trips(tmp_path):
    ex = copy_example(tmp_path)
    nasty = "Close </script> open <!-- and /*PLAN*/ /*CONFIG*/ end"
    edit_cards(ex, lambda cs: cs[0].update(q=nasty))
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    cards = embedded(html, "cards")
    assert nasty in {c["q"] for c in cards}
    assert "<!--" not in html and html.count("</script>") == html.count("<script")
    assert embedded(html, "plan") == {"stand": "", "links_alle": None, "tage": []}
    assert embedded(html, "config")["id"] == "example"


def test_build_is_deterministic_except_timestamp(tmp_path):
    ex = copy_example(tmp_path)
    blank = lambda s: re.sub(r'"built_at": ?"[^"]*"', '"built_at": ""', s)
    build(ex); a = (ex / "build" / "index.html").read_text(encoding="utf-8")
    build(ex); b = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert '"built_at": ""' in blank(a)
    assert blank(a) == blank(b)


def test_build_fails_on_invalid_card(tmp_path):
    ex = copy_example(tmp_path)
    edit_cards(ex, lambda cs: cs[0].update(src="guide:9.9"))
    r = build(ex)
    assert r.returncode == 1 and "guide:9.9" in r.stderr
    assert outputs(ex) == []


def test_build_lists_all_card_errors(tmp_path):
    ex = copy_example(tmp_path)
    def two_bad(cs):
        cs[0]["src"] = "guide:9.9"
        cs[1]["src"] = "guide:8.8"
    edit_cards(ex, two_bad)
    r = build(ex)
    assert r.returncode == 1
    assert "guide:9.9" in r.stderr and "guide:8.8" in r.stderr
    assert outputs(ex) == []


def test_exam_schema_errors_are_listed_with_card_errors(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: (e.pop("grading_prompt"), e.pop("storage_key")))
    edit_cards(ex, lambda cs: cs[0].update(src="guide:9.9"))
    r = build(ex)
    assert r.returncode == 1
    assert "exam.grading_prompt" in r.stderr and "exam.storage_key" in r.stderr and "guide:9.9" in r.stderr
    assert outputs(ex) == []


def test_reserved_deck_key_alle_is_rejected(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e["decks"].update(alle="Everything"))
    r = build(ex, "--check")
    assert r.returncode == 1 and "exam.decks: key 'alle' is reserved" in r.stderr


def test_empty_decks_rejected(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e.update(decks={}, languages="en"))
    r = build(ex, "--check")
    assert r.returncode == 1 and "exam.decks" in r.stderr and "exam.languages" in r.stderr


def test_example_build_in_place():
    r = build(EX)
    assert r.returncode == 0, r.stderr
    assert (EX / "build" / "index.html").exists() and (EX / "build" / "build.json").exists()
