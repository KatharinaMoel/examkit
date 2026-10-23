"""Optional card origin (exam.json "origins", card "origin"/"origin_detail"): validator, build, page, browser."""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import build as b  # noqa: E402
from engine import chrome  # noqa: E402
from engine import validate as v  # noqa: E402
from tests.test_smoke import smoke  # noqa: E402

EX = ROOT / "example"
BUILD_PY = ROOT / "engine" / "build.py"
TPL = ROOT / "engine" / "template"
ORIGINS = {"vl": "Lecture", "uebung": "Exercise", "literatur": "Literature"}


def card(**kw):
    c = {"id": "x", "deck": "terms", "q": "q", "a": "a", "key": ["k"], "src": "guide:1.1", "p": 1,
         "ctx": "c", "ctx_src": "guide", "_file": "t.json"}
    c.update(kw)
    return c


def check(cards, origins=None):
    exam = {"decks": {"terms": "Terms"}, "languages": ["en"]}
    if origins is not None:
        exam["origins"] = origins
    cov = {"domains": [{"id": "1", "tasks": [{"id": "1.1"}]}]}
    return v.validate(cards, exam, cov, EX / "notes", EX / "sources")


# --- validator -------------------------------------------------------------------------------

def test_origin_and_detail_accepted():
    assert check([card(origin="vl", origin_detail="VL 19.10.")], ORIGINS) == []
    assert check([card()], ORIGINS) == []       # origin stays optional


def test_unknown_origin_rejected():
    errs = check([card(origin="tutorial")], ORIGINS)
    assert len(errs) == 1 and "origin 'tutorial' not in exam.origins" in errs[0] and "'vl'" in errs[0]


def test_origin_without_config_is_a_clear_error():
    errs = check([card(origin="vl")])
    assert len(errs) == 1 and "needs exam.origins" in errs[0]


def test_origin_detail_must_be_string_and_needs_origin():
    assert any("origin_detail must be a non-empty string" in e for e in check([card(origin="vl", origin_detail=3)], ORIGINS))
    assert any("origin_detail must be a non-empty string" in e for e in check([card(origin="vl", origin_detail=" ")], ORIGINS))
    assert any("origin_detail needs origin" in e for e in check([card(origin_detail="hw01 1.1")], ORIGINS))


def test_non_string_origin_does_not_crash():
    errs = check([card(origin=["vl"])], ORIGINS)
    assert len(errs) == 1 and "not in exam.origins" in errs[0]


@pytest.mark.parametrize("bad, msg", [
    ([], "non-empty object"), ({}, "non-empty object"), ("vl", "non-empty object"),
    ({"VL": "Lecture"}, "key 'VL'"), ({"_none": "x"}, "key '_none'"), ({"vl": ""}, "label for 'vl'"),
    ({"vl": 3}, "label for 'vl'"),
])
def test_bad_origins_config(bad, msg):
    assert any(msg in e for e in check([card()], bad))


def test_broken_config_rejects_card_origin():
    errs = check([card(origin="vl")], ["vl"])
    assert any("exam.origins:" in e for e in errs) and any("x (t.json): origin 'vl'" in e for e in errs)


# --- build -----------------------------------------------------------------------------------

def origin_exam(tmp_path, origins=ORIGINS):
    ex = tmp_path / "ex"
    shutil.copytree(EX, ex, ignore=shutil.ignore_patterns("build"))
    f = ex / "exam.json"
    exam = json.loads(f.read_text(encoding="utf-8"))
    if origins is not None:
        exam["origins"] = origins
    f.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")
    cf = ex / "cards" / "basics.json"
    cards = json.loads(cf.read_text(encoding="utf-8"))
    if origins is not None:
        cards[0].update(origin="vl", origin_detail="VL <19.10.>")
        cards[1].update(origin="literatur")
    cf.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    return ex


def build(ex, *args):
    return subprocess.run([sys.executable, str(BUILD_PY), str(ex), *args], capture_output=True, text=True)


def embedded(html, script_id):
    m = re.search(rf'<script id="{script_id}" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_summary_counts_cards_per_origin(tmp_path):
    r = build(origin_exam(tmp_path), "--check")
    assert r.returncode == 0, r.stderr
    assert "origins: Lecture (vl) 1, Literature (literatur) 1, without origin 1" in r.stderr


def test_manifest_and_coverage_carry_origin_counts(tmp_path):
    ex = origin_exam(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    m = json.loads((ex / "build" / "build.json").read_text(encoding="utf-8"))
    assert m["by_origin"] == {"vl": 1, "literatur": 1} and m["no_origin"] == 1
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    task = embedded(html, "coverage")["domains"][0]["tasks"][0]
    assert task["origins"] == {"vl": 1} and task["no_origin"] == 0
    assert embedded(html, "build")["by_origin"] == {"vl": 1, "literatur": 1}


def test_page_with_origins_has_snippet_hooks_and_strings(tmp_path):
    ex = origin_exam(tmp_path)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert "window.examkitOrigin" in html and "/*ORIGIN" not in html
    for code in b.ORIGIN_HOOKS.values():
        assert code in html
    assert {"origin_aria", "origin_all", "origin_none", "origin_reset"} <= set(embedded(html, "ui"))


def test_page_without_origins_has_no_trace(tmp_path):
    ex = origin_exam(tmp_path, origins=None)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert "examkitOrigin" not in html and "/*ORIGIN" not in html and "origin_" not in html
    m = json.loads((ex / "build" / "build.json").read_text(encoding="utf-8"))
    assert "by_origin" not in m and "no_origin" not in m
    assert "origins" not in embedded(html, "coverage")["domains"][0]["tasks"][0]


def test_without_origins_hooks_vanish_from_template():
    """Without origins the page is the template with every origin placeholder removed - nothing else changes."""
    t = (TPL / "index.html").read_text(encoding="utf-8")
    for name in ("ORIGIN", *b.ORIGIN_HOOKS):
        assert t.count(f"/*{name}*/") == 1, name
    assert b.origin_values({}) == {name: "" for name in ("ORIGIN", *b.ORIGIN_HOOKS)}
    assert b.origin_values({"origins": ORIGINS})["ORIGIN"].lstrip().startswith("<style>")


def test_origin_ui_strings_exist_in_every_language():
    for f in TPL.glob("ui.*.json"):
        ui = json.loads(f.read_text(encoding="utf-8"))
        assert {"origin_aria", "origin_all", "origin_none", "origin_reset"} <= set(ui), f.name
        assert b.page_ui(ui, {}) == {k: val for k, val in ui.items() if not k.startswith("origin_")}


def test_origin_build_is_rejected_without_config(tmp_path):
    ex = origin_exam(tmp_path, origins=None)
    cf = ex / "cards" / "basics.json"
    cards = json.loads(cf.read_text(encoding="utf-8"))
    cards[0]["origin"] = "vl"
    cf.write_text(json.dumps(cards), encoding="utf-8")
    r = build(ex, "--check")
    assert r.returncode == 1 and "needs exam.origins" in r.stderr


# --- browser ---------------------------------------------------------------------------------

@pytest.mark.skipif(chrome.find_chrome() is None, reason="no headless Chrome found (set EXAMKIT_CHROME)")
def test_browser_badge_filter_and_saved_state(tmp_path):
    ex = origin_exam(tmp_path)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    js = """
    const chips = [...document.querySelectorAll('#origins [data-origin]')];
    d.dataset.chips = JSON.stringify(chips.map(c => [c.dataset.origin, c.textContent]));
    document.querySelector('#origins [data-origin=vl]').click();
    d.dataset.boxes = ['n0','n1','n2','n3'].map(i=>document.getElementById(i).textContent).join(',');
    d.dataset.badge = (document.querySelector('#stage .origin')||{}).textContent || '';
    d.dataset.badgehtml = (document.querySelector('#stage .origin')||{}).innerHTML || '';
    d.dataset.saved = JSON.stringify(JSON.parse(localStorage.getItem(CONFIG.storage_key)).ui);
    document.querySelector('#origins [data-origin=_none]').click();
    d.dataset.noneboxes = ['n0','n1','n2','n3'].map(i=>document.getElementById(i).textContent).join(',');
    d.dataset.nonebadge = String(!!document.querySelector('#stage .origin'));
    document.getElementById('reset').click();
    d.dataset.reset = document.getElementById('resetbox').textContent;
    document.querySelector('#origins [data-origin=""]').click();
    d.dataset.allboxes = ['n0','n1','n2','n3'].map(i=>document.getElementById(i).textContent).join(',');
    d.dataset.cov = (document.querySelector('#coverage-out .covorig')||{}).textContent || '';
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["errors"]) == []
    assert json.loads(got["chips"]) == [["", "Any origin3"], ["vl", "Lecture1"], ["literatur", "Literature1"], ["_none", "no origin1"]]
    assert got["boxes"] == "1,0,0,0"
    assert got["badge"] == "LectureVL <19.10.>" and "&lt;19.10.&gt;" in got["badgehtml"]
    assert json.loads(got["saved"]) == {"deck": "alle", "p1": False, "origin": "vl"}
    assert got["noneboxes"] == "1,0,0,0" and got["nonebadge"] == "false"
    assert 'origin "no origin"' in got["reset"]
    assert got["allboxes"] == "3,0,0,0"
    assert got["cov"] == "Lecture 1"


@pytest.mark.skipif(chrome.find_chrome() is None, reason="no headless Chrome found (set EXAMKIT_CHROME)")
def test_browser_restores_origin_and_ignores_unknown(tmp_path):
    ex = origin_exam(tmp_path)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    key = "examkit-example-v1"
    planted_ok = f'<script>localStorage.setItem("{key}", JSON.stringify({{cards:{{}}, ui:{{deck:"alle", p1:false, origin:"literatur"}}}}))</script>'
    # an old state without ui.origin and one with an origin that is gone both fall back to all cards
    planted_old = f'<script>localStorage.setItem("{key}", JSON.stringify({{cards:{{}}, ui:{{deck:"alle", p1:false}}}}))</script>'
    planted_gone = f'<script>localStorage.setItem("{key}", JSON.stringify({{cards:{{}}, ui:{{deck:"alle", origin:"weg"}}}}))</script>'
    js = """
    d.dataset.pressed = (document.querySelector('#origins [aria-pressed=true]')||{}).dataset?.origin ?? 'none';
    d.dataset.boxes = ['n0','n1','n2','n3'].map(i=>document.getElementById(i).textContent).join(',');
    """
    # the state is planted in <head>, before the page scripts read it at load
    out = {}
    for name, planted in (("ok", planted_ok), ("old", planted_old), ("gone", planted_gone)):
        page = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + planted, 1)
        (tmp_path / name).mkdir()
        got = smoke(tmp_path / name, page, extra_js=js)
        assert json.loads(got["errors"]) == [], name
        out[name] = (got["pressed"], got["boxes"])
    assert out["ok"] == ("literatur", "1,0,0,0")
    assert out["old"] == ("", "3,0,0,0")
    assert out["gone"] == ("", "3,0,0,0")
