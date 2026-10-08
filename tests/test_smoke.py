"""Smoke test in a real headless browser: the built page runs without JS errors and shows every card.

The test page is index.html plus (a) an error listener right after the charset meta and (b) a probe
script at the end that, 500 ms of page time later, writes everything the test reads into one element
<div id="smoke" data-...>. Skipped when no Chrome is found.
"""
import html as html_mod
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import chrome  # noqa: E402

EX = ROOT / "example"
BUILD_PY = ROOT / "engine" / "build.py"
CHARSET = '<meta charset="utf-8">'
LISTENER = CHARSET + ('<script>window.__smokeErrors=[];'
                      'addEventListener("error",e=>__smokeErrors.push(String(e.message||e)));'
                      'addEventListener("unhandledrejection",e=>__smokeErrors.push("rejection: "+String(e.reason)));'
                      '</script>')
PROBE = """
<script>
setTimeout(()=>{
  const d = document.createElement('div'); d.id = 'smoke';
  d.dataset.errors = JSON.stringify(window.__smokeErrors);
  d.dataset.cards = (document.querySelector('#chips [data-deck=alle] small')||{}).textContent || '';
  %s
  document.body.appendChild(d);
}, 500);
</script>
"""
pytestmark = pytest.mark.skipif(chrome.find_chrome() is None, reason="no headless Chrome found (set EXAMKIT_CHROME)")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """example/ copied and built once per module; returns (index.html text, cards list)."""
    ex = tmp_path_factory.mktemp("exam") / "ex"
    shutil.copytree(EX, ex, ignore=shutil.ignore_patterns("build"))
    r = subprocess.run([sys.executable, str(BUILD_PY), str(ex)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    cards = json.loads((ex / "cards" / "basics.json").read_text(encoding="utf-8"))
    return (ex / "build" / "index.html").read_text(encoding="utf-8"), cards


def harness(html, extra_js="", planted=""):
    """index.html -> test page: listener after the charset meta, planted scripts, then the probe."""
    assert html.count(CHARSET) == 1, "template must contain the charset meta exactly once"
    return html.replace(CHARSET, LISTENER, 1) + planted + PROBE % extra_js


def smoke(tmp_path, html, extra_js="", planted=""):
    """Run the test page in Chrome with a fresh profile; returns the probe's data-* attributes, unescaped.

    Probe keys set via `d.dataset.<name>` must be single lowercase words (the regex `data-([a-z]+)`
    ignores hyphenated names).
    """
    page = tmp_path / "smoke.html"
    page.write_text(harness(html, extra_js, planted), encoding="utf-8")
    dom = chrome.dump_dom(page, tmp_path / "profile")
    m = re.search(r'<div id="smoke"([^>]*)>', dom)
    assert m, "probe element missing: the page's scripts did not finish"
    return {k: html_mod.unescape(v) for k, v in re.findall(r'data-([a-z]+)="([^"]*)"', m.group(1))}


def test_detects_planted_error_first(tmp_path, built):
    html, _ = built
    planted = ('<script>throw new Error("planted smoke error")</script>'
               '<script>Promise.reject(new Error("planted rejection"))</script>')
    errors = json.loads(smoke(tmp_path, html, planted=planted)["errors"])
    assert len(errors) == 2 and all("planted" in e for e in errors), errors


def test_page_loads_without_errors_and_shows_all_cards(tmp_path, built):
    html, cards = built
    got = smoke(tmp_path, html)
    assert json.loads(got["errors"]) == []
    assert int(got["cards"]) == len(cards)


PROGRESS = """
const P = (cards) => ({examkit_progress: 1, exam_id: CONFIG.id, storage_key: CONFIG.storage_key,
                       exported_at: '2026-10-07T00:00:00Z', cards, hist: [], plan: {}});
"""


def test_export_has_format_and_every_section(tmp_path, built):
    html, _ = built
    got = smoke(tmp_path, html, extra_js="d.dataset.export = JSON.stringify(window.examkitExport());")
    e = json.loads(got["export"])
    assert e["examkit_progress"] == 1 and e["exam_id"] == "example" and e["storage_key"] == "examkit-example-v1"
    assert e["cards"] == {} and e["hist"] == [] and e["plan"] == {}
    assert e["exported_at"].endswith("Z")


def test_import_then_export_round_trip(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    const r = window.examkitImport(P({'ex-basic-def': {b:2, r:2, w:0, t:5, k:2, dn:9}}));
    d.dataset.result = JSON.stringify(r);
    d.dataset.export = JSON.stringify(window.examkitExport());
    d.dataset.boxes = ['n0','n1','n2','n3'].map(i=>document.getElementById(i).textContent).join(',');
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["result"]) == {"ok": True, "cards": 1}
    assert json.loads(got["export"])["cards"]["ex-basic-def"]["b"] == 2
    assert got["boxes"] == "2,0,1,0"          # three cards: two unseen, one in box 2
    assert json.loads(got["errors"]) == []


def test_import_keeps_newer_grade(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    window.examkitImport(P({'ex-basic-def': {b:2, r:2, w:0, t:5, k:2, dn:9}}));
    window.examkitImport(P({'ex-basic-def': {b:1, r:1, w:0, t:1, k:1, dn:3}}));
    d.dataset.export = JSON.stringify(window.examkitExport());
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["export"])["cards"]["ex-basic-def"]["b"] == 2


def test_import_refuses_other_exam_and_junk(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    const other = P({'ex-basic-def': {b:3, t:9}}); other.storage_key = 'someone-else-v1';
    d.dataset.other = JSON.stringify(window.examkitImport(other));
    d.dataset.junk = JSON.stringify(window.examkitImport({hello: 'world'}));
    d.dataset.nothing = JSON.stringify(window.examkitImport(null));
    d.dataset.export = JSON.stringify(window.examkitExport());
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["other"]) == {"ok": False, "reason": "import_wrong_exam"}
    assert json.loads(got["junk"]) == {"ok": False, "reason": "import_bad"}
    assert json.loads(got["nothing"]) == {"ok": False, "reason": "import_bad"}
    assert json.loads(got["export"])["cards"] == {}


def test_import_skips_malformed_entries_and_keeps_good_ones(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    const r = window.examkitImport(P({'ex-basic-def': null, 'ex-svc-thing': {b:'two', t:5}, 'ex-model': {b:1, r:1, w:0, t:7, k:1, dn:3}}));
    d.dataset.result = JSON.stringify(r);
    d.dataset.export = JSON.stringify(window.examkitExport());
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["result"]) == {"ok": True, "cards": 1}
    assert list(json.loads(got["export"])["cards"]) == ["ex-model"]
    assert json.loads(got["errors"]) == []


def test_import_rejects_array_cards(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    const p = P({}); p.cards = [{b:3, t:9}];
    d.dataset.result = JSON.stringify(window.examkitImport(p));
    d.dataset.export = JSON.stringify(window.examkitExport());
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["result"]) == {"ok": False, "reason": "import_bad"}
    assert json.loads(got["export"])["cards"] == {}


def test_notes_search_hides_group_label_when_no_link_is_left(tmp_path, built):
    html, _ = built
    js = """
    const q = document.getElementById('notes-q'); q.value = 'zzz-no-note-matches-this'; q.dispatchEvent(new Event('input'));
    d.dataset.grpoff = document.querySelectorAll('#notes-nav .navgrp.off').length;
    d.dataset.grpall = document.querySelectorAll('#notes-nav .navgrp').length;
    q.value = ''; q.dispatchEvent(new Event('input'));
    d.dataset.grpafter = document.querySelectorAll('#notes-nav .navgrp.off').length;
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert got["grpall"] == "1" and got["grpoff"] == "1" and got["grpafter"] == "0"


def test_import_newer_grade_overwrites_existing_card(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    window.examkitImport(P({'ex-basic-def': {b:1, r:1, w:0, t:1, k:1, dn:3}}));
    window.examkitImport(P({'ex-basic-def': {b:3, r:3, w:0, t:9, k:3, dn:20}}));
    d.dataset.export = JSON.stringify(window.examkitExport());
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["export"])["cards"]["ex-basic-def"]["b"] == 3
    assert json.loads(got["errors"]) == []


def test_import_filters_history_and_plan_entries(tmp_path, built):
    html, _ = built
    js = PROGRESS + """
    const p = P({});
    p.hist = [{id: 'ex-model', g: 'richtig', t: 5}, {id: 3, t: 1}, null, {id: 'ex-svc-thing'}, 'junk', {id: 'ex-basic-def', t: '7'}];
    p.plan = {day1: true, day2: false, day3: 0, day4: 1};
    d.dataset.result = JSON.stringify(window.examkitImport(p));
    d.dataset.export = JSON.stringify(window.examkitExport());
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert json.loads(got["result"]) == {"ok": True, "cards": 0}
    e = json.loads(got["export"])
    assert [h["id"] for h in e["hist"]] == ["ex-model"]
    assert sorted(e["plan"]) == ["day1", "day4"]
    assert json.loads(got["errors"]) == []
