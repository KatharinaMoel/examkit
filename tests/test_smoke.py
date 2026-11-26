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


def test_report_block_on_front_and_back(tmp_path, built):
    """The learner spots unsuitable cards before answering, so the feedback block sits on both sides."""
    html, _ = built
    js = """
    const st = document.getElementById('stage');
    const rep = () => st.querySelector('details.report');
    d.dataset.front = String(!!st.querySelector('#ans') && !!rep() && !!st.querySelector('#rep') && !!st.querySelector('#repsend'));
    d.dataset.marker = rep() ? rep().querySelector('summary').textContent : '';
    d.dataset.tap = rep() ? Math.round(rep().querySelector('summary').getBoundingClientRect().height) : 0;
    const r0 = document.getElementById('rep'); if(r0) r0.value = 'draft from the front';
    document.getElementById('flip').click();
    d.dataset.back = String(!!st.querySelector('.back details.report') && !!st.querySelector('#rep') && !st.querySelector('#ans'));
    d.dataset.draft = (document.getElementById('rep')||{}).value || '';
    d.dataset.reps = st.querySelectorAll('#rep').length;
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert got["front"] == "true", "report block missing on the front of the card"
    assert got["marker"].startswith("✎ ")
    assert int(got["tap"]) >= 44, "summary tap target below 44px"
    assert got["back"] == "true", "report block missing on the back of the card"
    assert got["draft"] == "draft from the front"
    assert got["reps"] == "1"
    assert json.loads(got["errors"]) == []


def test_report_draft_stays_with_its_card(tmp_path, built):
    """A note typed on card A must not show up on card B after "later"."""
    html, _ = built
    js = """
    const box = () => document.querySelector('#stage details.report');
    d.dataset.a = box().dataset.card;
    box().open = true; document.getElementById('rep').value = 'note for card A';
    document.getElementById('skip').click();
    d.dataset.b = box().dataset.card;
    d.dataset.draft = document.getElementById('rep').value;
    d.dataset.open = String(box().open);
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert got["a"] and got["b"] and got["a"] != got["b"]
    assert got["draft"] == "" and got["open"] == "false"
    assert json.loads(got["errors"]) == []


def test_report_without_db_says_so_on_the_front(tmp_path, built):
    """The local page has no database: sending from the front shows report_nodb and keeps the text."""
    html, _ = built
    js = """
    document.getElementById('rep').value = 'unsuitable question';
    document.getElementById('repsend').click();
    d.dataset.state = document.getElementById('repstate').textContent;
    d.dataset.want = T('report_nodb');
    d.dataset.front = String(!!document.getElementById('ans'));
    d.dataset.text = document.getElementById('rep').value;
    """
    got = smoke(tmp_path, html, extra_js=js)
    assert got["front"] == "true"
    assert got["want"] and got["state"] == got["want"]
    assert got["text"] == "unsuitable question"
    assert json.loads(got["errors"]) == []


# Fake claude runtime: a database whose feedback add() stays pending until window.__release() is called
FAKE_DB = """<script>window.__sent = []; window.__release = null;
const __doc = {get: async () => ({exists: false, data: () => ({})}), set: async () => {}, update: async () => {}, onSnapshot: () => () => {}};
window.claude = {use: async n => n === 'db' ? {doc: () => __doc,
  collection: name => ({add: doc => { __sent.push([name, doc]); return new Promise(r => window.__release = r); }})} : null};
</script>"""


def test_report_in_flight_does_not_touch_the_next_card(tmp_path, built):
    """A send still awaiting the database must not clear or write into the next card's block."""
    html, _ = built
    js = """
    document.getElementById('rep').value = 'note for card A';
    document.getElementById('repsend').click();
    d.dataset.saving = document.getElementById('repstate').textContent;
    d.dataset.wantsaving = T('report_saving');
    document.getElementById('skip').click();
    document.getElementById('rep').value = 'draft on card B';
    window.__release();
    setTimeout(() => {
      d.dataset.draft = document.getElementById('rep').value;
      d.dataset.state = document.getElementById('repstate').textContent;
      d.dataset.disabled = String(document.getElementById('repsend').disabled);
      d.dataset.sent = JSON.stringify(__sent.map(([n, doc]) => [n, Object.keys(doc).sort(), doc.status, doc.text]));
      d.dataset.done = '1';
    }, 50);
    """
    got = smoke(tmp_path, html.replace(CHARSET, CHARSET + FAKE_DB, 1), extra_js=js)
    assert got["saving"] == got["wantsaving"], "fake database not picked up: the send never started"
    assert got.get("done") == "1"
    assert got["draft"] == "draft on card B" and got["state"] == "" and got["disabled"] == "false"
    assert json.loads(got["sent"]) == [["feedback", ["id", "q", "status", "t", "text"], "offen", "note for card A"]]
    assert json.loads(got["errors"]) == []


def test_chip_rows_never_hide_buttons(tmp_path, built):
    """Every chip row shows all its buttons: many decks wrap onto further lines instead of scrolling out of view."""
    html, _ = built
    probe = """
  const row = document.getElementById('chips');
  for (let i = 0; i < 12; i++) row.insertAdjacentHTML('beforeend', '<button class="chip">Deck number ' + i + '<small>99</small></button>');
  d.dataset.overflow = JSON.stringify([...document.querySelectorAll('.chips')]
    .filter(r => r.offsetParent && r.scrollWidth > r.clientWidth + 1).map(r => r.id || r.dataset.uiLabel || '?'));
"""
    assert json.loads(smoke(tmp_path, html, extra_js=probe)["overflow"]) == []


FAKE_RUNTIME = """<script>
(()=>{ // the cloud says the open card is settled, so a careless next() would swap it for another one
  const settled = () => { const a = document.getElementById('ans'), id = a && a.dataset.cid;
    return id ? {[id]: {b: 3, r: 3, w: 0, k: 1, dn: 1e9, t: Date.now()}} : {}; };
  const doc = () => ({get: async () => ({exists: true, data: () => ({cards: settled(), done: {}, e: []})}),
  set: async () => {}, update: async () => {}, onSnapshot: () => () => {}});
  const db = {doc, collection: () => ({add: async () => {}})};
  window.claude = {use: n => new Promise(r => setTimeout(() => r(n === 'sample' ? (async () => '{}') : db), n === 'sample' ? 150 : 250))};
  addEventListener('DOMContentLoaded', () => { const a = document.getElementById('ans'); a.focus(); a.value = 'MY ANSWER';
    window.__firstCard = a.dataset.cid; window.__firstField = a; });
})();
</script>"""


def test_typed_answer_survives_late_runtime(tmp_path, built):
    """sample and db arrive after the first render: a typed answer and its card stay put."""
    html, _ = built
    html = html.replace(CHARSET, CHARSET + FAKE_RUNTIME, 1)
    probe = """
  const a = document.getElementById('ans');
  d.dataset.answer = (a||{}).value || '';
  d.dataset.same = a && a === window.__firstField && a.dataset.cid === window.__firstCard ? 'yes' : 'no';
  d.dataset.check = document.getElementById('check') ? 'yes' : 'no';
"""
    got = smoke(tmp_path, html, extra_js=probe)
    assert got["answer"] == "MY ANSWER" and got["check"] == "yes" and got["same"] == "yes", got


def test_tabs_fit_a_narrow_phone(tmp_path, built):
    """At 320 px CSS width no tab is wider than the screen (the coverage counts once pushed the page sideways)."""
    html, _ = built
    probe = """
  document.body.style.width = '320px'; document.body.style.boxSizing = 'border-box';
  const wide = [];
  for (const v of ['cards','coverage','notes','plan']) {
    document.getElementById('tab-' + v).click();
    document.querySelectorAll('#view-' + v + ' details').forEach(x => x.open = true);
    const b = document.querySelector('#view-' + v + ' details.cov summary b');
    if (b) b.textContent = 'aws-application-discovery-service';  // the longest kind of id in a real exam
    const sec = document.getElementById('view-' + v);
    if (sec.scrollWidth > document.body.clientWidth + 1) wide.push(v + ':' + sec.scrollWidth);
  }
  d.dataset.wide = JSON.stringify(wide);
"""
    assert json.loads(smoke(tmp_path, html, extra_js=probe)["wide"]) == []


def test_memo_shows_on_the_back_marked_as_memory_aid(tmp_path, built):
    """A card memo appears on the back only, under its own label, so it is never mistaken for a source."""
    html, _ = built
    head, rest = html.split('<script id="cards" type="application/json">', 1)
    data, tail = rest.split("</script>", 1)
    cards = [dict(c, memo="MEMO <b>hook</b>") for c in json.loads(data)]
    html = head + '<script id="cards" type="application/json">' + json.dumps(cards) + "</script>" + tail
    probe = """
  d.dataset.front = document.querySelector('#stage .memo') ? 'yes' : 'no';
  document.getElementById('flip').click();
  const m = document.querySelector('#stage .back .memo');
  d.dataset.text = m ? m.textContent : '';
  d.dataset.bold = m && m.querySelector('b') ? 'yes' : 'no';
"""
    got = smoke(tmp_path, html, extra_js=probe)
    assert got["front"] == "no" and got["bold"] == "no", got
    assert got["text"].startswith("Mnemonic") and "MEMO <b>hook</b>" in got["text"], got


def test_grading_lands_on_the_next_card(tmp_path, built):
    """After grading or "later" far down the page, the next card's top is in view and the card (not the answer field) has focus."""
    html, _ = built
    probe = """
  document.body.style.paddingBottom = '4000px';  // a tall page, like a long back on a phone
  const after = btn => {
    window.scrollTo(0, document.documentElement.scrollHeight);
    const before = Math.round(document.getElementById('stage').getBoundingClientRect().top);
    document.querySelector(btn).click();
    const top = Math.round(document.getElementById('stage').getBoundingClientRect().top);
    const a = document.activeElement;
    return [before, top, a && a.classList.contains('card') ? 'card' : (a ? a.tagName : '')];
  };
  document.getElementById('flip').click();
  d.dataset.grade = JSON.stringify(after('[data-g="2"]'));
  d.dataset.skip = JSON.stringify(after('#skip'));
"""
    got = smoke(tmp_path, html, extra_js=probe)
    for k in ("grade", "skip"):
        before, top, focus = json.loads(got[k])
        assert before < 0 and 0 <= top <= 20 and focus == "card", (k, got[k])


def test_history_folds_out_the_answer_and_keeps_it_open(tmp_path, built):
    """A history entry shows the model answer on demand and stays open after a re-grade."""
    html, cards = built
    probe = """
  document.getElementById('flip').click();
  document.querySelector('[data-g="0"]').click();
  document.getElementById('histbtn').click();
  const det = document.querySelector('#hist details.hsol');
  d.dataset.closed = det && !det.open ? 'yes' : 'no';
  det.open = true;
  d.dataset.answer = (det.querySelector('.solution .a')||{}).textContent || '';
  document.querySelector('#hist [data-hg="2"]').click();
  const det2 = document.querySelector('#hist details.hsol');
  d.dataset.reopen = det2 && det2.open ? 'yes' : 'no';
  d.dataset.pressed = (document.querySelector('#hist [data-hg="2"]')||{}).getAttribute('aria-pressed') || '';
"""
    got = smoke(tmp_path, html, extra_js=probe)
    answers = {c["a"] for c in cards}
    assert got["closed"] == "yes" and got["answer"] in answers, got
    assert got["reopen"] == "yes" and got["pressed"] == "true", got


def test_next_card_offers_the_last_graded_answer(tmp_path, built):
    """After grading, the next card's front carries a collapsed "last graded" block with that card's answer;
    the feedback block still belongs to the current card."""
    html, cards = built
    probe = """
  d.dataset.first = document.querySelector('#stage details.prev') ? 'yes' : 'no';
  const firstQ = document.querySelector('#stage .q').textContent;
  document.getElementById('flip').click();
  document.querySelector('[data-g="1"]').click();
  const p = document.querySelector('#stage details.prev');
  d.dataset.open = p && p.open ? 'yes' : 'no';
  d.dataset.prevq = p ? p.querySelector('.pq').textContent : '';
  d.dataset.firstq = firstQ;
  d.dataset.answer = p ? (p.querySelector('.solution .a')||{}).textContent : '';
  d.dataset.summary = p ? p.querySelector('summary').textContent : '';
  const r = document.querySelector('#stage details.report[data-card]');
  d.dataset.repcard = r ? r.dataset.card : '';
  d.dataset.cur = document.querySelector('#ans').dataset.cid;
"""
    got = smoke(tmp_path, html, extra_js=probe)
    assert got["first"] == "no" and got["open"] == "no", got
    assert got["prevq"] == got["firstq"] and got["answer"] in {c["a"] for c in cards}, got
    assert "Partly" in got["summary"] or "Teilweise" in got["summary"], got
    assert got["repcard"] == got["cur"], got
