import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = ROOT / "engine" / "template"
DYNAMIC = {"verdict_richtig", "verdict_teilweise", "verdict_falsch", "grade_0", "grade_1", "grade_2",
           "box_0", "box_1", "box_2", "box_3"}   # keys built at runtime: T('grade_'+g) etc.


def load(lang):
    return json.loads((TPL / f"ui.{lang}.json").read_text(encoding="utf-8"))


def template():
    return (TPL / "index.html").read_text(encoding="utf-8")


def test_de_and_en_have_same_keys():
    assert set(load("de")) == set(load("en"))


def test_values_are_nonempty_strings_with_same_placeholders():
    de, en = load("de"), load("en")
    ph = lambda s: set(re.findall(r"\{(\w+)\}", s))
    for k in de:
        assert isinstance(de[k], str) and de[k] and isinstance(en[k], str) and en[k], k
        assert ph(de[k]) == ph(en[k]), k


def test_template_uses_only_known_keys_and_every_key():
    t, keys = template(), set(load("de"))
    used = set(re.findall(r"\bT\('([a-z0-9_]+)'", t)) | set(re.findall(r'data-ui(?:-placeholder|-label)?="([a-z0-9_]+)"', t))
    assert used <= keys, f"unknown keys in template: {used - keys}"
    assert DYNAMIC <= keys
    assert keys - used - DYNAMIC == set(), f"keys never used: {keys - used - DYNAMIC}"


def test_no_german_literals_left_in_template_code():
    # comments may stay German for now; code and markup must not carry UI text
    bad = []
    for line in template().splitlines():
        if line.strip().startswith("//"):
            continue   # full-line comment; inline comments with umlauts must be translated by the implementer
        if re.search(r"[äöüÄÖÜß„“]", line) and "DEWORT" not in line:
            bad.append(line.strip())
    assert bad == [], bad


def test_build_embeds_selected_language(tmp_path):
    import shutil, subprocess, sys
    ex = tmp_path / "ex"
    shutil.copytree(ROOT / "example", ex, ignore=shutil.ignore_patterns("build"))
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "build.py"), str(ex)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script id="ui" type="application/json">(.*?)</script>', html, re.S)
    assert m and json.loads(m.group(1))["tab_cards"] == "Cards"
    assert "<title>Example Exam · Flashcards</title>" in html
