"""Optional formulas (exam.json "math": "mathjax"): note protection, build opt-in, print check, browser smoke."""
import json
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import chrome  # noqa: E402
from engine import notes as n  # noqa: E402

EX = ROOT / "example"
BUILD_PY = ROOT / "engine" / "build.py"
PRINT_PY = ROOT / "engine" / "print.py"
TEMPLATE = ROOT / "engine" / "template" / "index.html"
MATH_NOTE = r"""
## Cones

Let $\sigma_1 = \operatorname{cone}(e_1, e_2)$ and $\sigma^\vee_*$ be the *dual* cone.

$$
S_\sigma = \sigma^\vee \cap M, \qquad \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}
$$

| Cone | Semigroup |
|---|---|
| $\lvert x \rvert$ | $|y|_2$ |
"""


def math_exam(tmp_path, math="mathjax"):
    """example/ copied, math switched on, a formula on a card and a section with formulas in the note."""
    ex = tmp_path / "ex"
    shutil.copytree(EX, ex, ignore=shutil.ignore_patterns("build"))
    f = ex / "exam.json"
    exam = json.loads(f.read_text(encoding="utf-8"))
    if math is not None:
        exam["math"] = math
    f.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")
    f = ex / "cards" / "basics.json"
    cards = json.loads(f.read_text(encoding="utf-8"))
    cards[0].update(q=r"What is a basic, as $x_1^2$?", a=r"It is $$\sum_{i=1}^n a_i$$ and \(b_*\).")
    f.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    note = ex / "notes" / "intro.md"
    note.write_text(note.read_text(encoding="utf-8") + MATH_NOTE, encoding="utf-8")
    return ex


def build(ex):
    return subprocess.run([sys.executable, str(BUILD_PY), str(ex)], capture_output=True, text=True)


# --- notes: TeX spans survive Markdown ---

def test_markdown_mangles_tex_without_math():
    # the planted failure: without protection Markdown turns *b* into emphasis and eats a backslash of `\\`
    html = n.render(r"$a *b* c$ and $$x \\ y$$")
    assert "<em>" in html and r"x \\ y" not in html


def test_underscore_star_and_double_backslash_survive():
    html = n.render(r"Let $a_1 * b_2 * c$ and $$x \\ y_3$$ be.", math=True)
    assert '<span class="math">$a_1 * b_2 * c$</span>' in html
    assert '<span class="math">$$x \\\\ y_3$$</span>' in html
    assert "<em>" not in html and "EXAMKITMATH" not in html


def test_paren_and_bracket_delimiters_survive():
    html = n.render(r"Also \(x_1\) and \[y_2 * z_3\] ok.", math=True)
    assert r'<span class="math">\(x_1\)</span>' in html and r'<span class="math">\[y_2 * z_3\]</span>' in html


def test_formula_is_html_escaped():
    html = n.render(r"$a<b \text{ & } c>d$", math=True)
    assert '<span class="math">$a&lt;b \\text{ &amp; } c&gt;d$</span>' in html


def test_bar_inside_formula_is_no_table_cell():
    html = n.render("| a | b |\n|---|---|\n| $\\lvert x \\rvert$ | $|y|_2$ |\n", math=True)
    assert html.count("<td>") == 2
    assert '<td><span class="math">$|y|_2$</span></td>' in html


def test_prices_and_code_are_no_formulas():
    html = n.render("Costs $5 and $6. Shell `$HOME` and `$a_b$`.\n\n```\n$x_1$\n```\n", math=True)
    assert 'class="math"' not in html
    assert "<code>$HOME</code>" in html and "<code>$a_b$</code>" in html and "$x_1$\n</code></pre>" in html


def test_escaped_dollar_and_blank_line_end_a_span():
    assert 'class="math"' not in n.render("\\$a_1$ and $b\n\nc$", math=True)


def test_template_placeholder_text_inside_formula_stays_text():
    html = n.render(r"$/*NOTES*/ \text{EXAMKITMATH0END}$", math=True)
    assert html.count('<span class="math">') == 1 and "/*NOTES*/" in html


def test_mermaid_and_math_together():
    html = n.render("```mermaid\nflowchart LR\n  A --> B\n```\n\n$a_1$\n", math=True)
    assert '<pre class="mermaid">' in html and '<span class="math">$a_1$</span>' in html


def test_load_notes_follows_exam_math():
    exam = {"notes": [{"group": "", "items": [{"slug": "intro"}]}]}
    off, _ = n.load_notes(EX / "notes", exam)
    on, _ = n.load_notes(EX / "notes", {**exam, "math": "mathjax"})
    assert off == on          # the example note has no formula: switching math on changes nothing


def test_mathjax_url_is_an_exact_cdnjs_version():
    assert re.fullmatch(r"https://cdnjs\.cloudflare\.com/ajax/libs/mathjax/3\.\d+\.\d+/es5/tex-svg\.js", n.MATHJAX_URL)


# --- build: opt-in ---

def test_build_without_math_has_no_mathjax(tmp_path):
    ex = math_exam(tmp_path, math=None)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert "MathJax" not in html and "mathjax" not in html and '<span class="math">' not in html
    assert "/*MATH*/" not in html
    # the placeholder is the only change in the template, and it renders to nothing
    assert html.endswith("})();\n</script>\n")


def test_build_with_math_loads_mathjax_and_protects_notes(tmp_path):
    ex = math_exam(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert "MathJax" in r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert html.count(n.MATHJAX_URL) == 1 and "__MATHJAX_" not in html and "/*MATH*/" not in html
    assert "MathJax.typesetPromise" in html and "MutationObserver" in html
    notes = json.loads(re.search(r'<script id="notes" type="application/json">(.*?)</script>', html, re.S).group(1))
    body = notes[0]["items"][0]["html"]
    assert r'<span class="math">$\sigma_1 = \operatorname{cone}(e_1, e_2)$</span>' in body
    assert "<em>dual</em>" in body and body.count("<td>") == 4


def test_unknown_math_mode_is_an_error(tmp_path):
    ex = math_exam(tmp_path, math="katex")
    r = build(ex)
    assert r.returncode == 1 and "exam.math" in r.stderr and "'mathjax'" in r.stderr


def test_template_has_math_placeholder_once():
    assert TEMPLATE.read_text(encoding="utf-8").count("/*MATH*/") == 1


# --- print pack ---

FAKE = """
import json, pathlib, re, sys
args = sys.argv[1:]
with open(%(log)r, "a") as f:
    f.write(json.dumps(args) + "\\n")
page = pathlib.Path(args[-1][len("file://"):])
for a in args:
    if a.startswith("--print-to-pdf="):
        pathlib.Path(a.split("=", 1)[1]).write_bytes(b"%%PDF-fake " * 300)
if "--dump-dom" in args:
    html = page.read_text()
    html = re.sub(r'<pre class="mermaid">.*?</pre>', '<pre class="mermaid"><svg></svg></pre>', html, flags=re.S)
    if %(mode)r == "rendered":
        html = re.sub(r'<span class="math">[^<]*</span>', '<span class="math"><mjx-container jax="SVG"><svg></svg></mjx-container></span>', html)
    print(html)
"""


def fake_chrome(tmp_path, monkeypatch, mode):
    log = tmp_path / "calls.log"
    script = tmp_path / "fake_chrome.py"
    script.write_text(FAKE % {"log": str(log), "mode": mode}, encoding="utf-8")
    monkeypatch.setenv("EXAMKIT_CHROME", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}")
    return log


def run_print(ex, *args):
    return subprocess.run([sys.executable, str(PRINT_PY), str(ex), *args], capture_output=True, text=True)


def test_print_page_loads_mathjax_only_with_math(tmp_path):
    on = math_exam(tmp_path / "on")
    off = math_exam(tmp_path / "off", math=None)
    for ex in (on, off):
        assert run_print(ex, "--html-only").returncode == 0
    page_on = (on / "build" / "print" / "01-intro.html").read_text(encoding="utf-8")
    page_off = (off / "build" / "print" / "01-intro.html").read_text(encoding="utf-8")
    assert n.MATHJAX_URL in page_on and "Formulas not rendered" in page_on and "dataset.mathjax" in page_on
    assert "MathJax" not in page_off


def test_print_fails_when_formulas_stay_unrendered(tmp_path, monkeypatch):
    ex = math_exam(tmp_path)
    fake_chrome(tmp_path, monkeypatch, "raw")
    r = run_print(ex)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert "formulas not rendered in 01-intro.html (note intro)" in r.stderr
    assert (ex / "build" / "print" / "01-intro.pdf").exists()


def test_print_passes_when_formulas_are_rendered(tmp_path, monkeypatch):
    ex = math_exam(tmp_path)
    log = fake_chrome(tmp_path, monkeypatch, "rendered")
    r = run_print(ex)
    assert r.returncode == 0, r.stderr
    assert "5 of 5 formulas rendered" in r.stderr
    dumps = [json.loads(line) for line in log.read_text().splitlines() if "--dump-dom" in line]
    assert len(dumps) == 4          # two pages, each checked for diagrams and for formulas


# --- browser smoke: MathJax really typesets (needs Chrome and network to cdnjs) ---

PROBE = """
<script>
(function(){
  const d = document.createElement('div'); d.id = 'mathsmoke';
  const count = sel => document.querySelectorAll(sel + ' mjx-container svg').length;
  const wait = (ok, then, n) => (ok() || n <= 0) ? then() : setTimeout(() => wait(ok, then, n - 1), 100);
  const failed = () => document.documentElement.dataset.mathjax === 'failed';
  wait(() => count('#stage') > 0 || failed(), () => {
    d.dataset.state = document.documentElement.dataset.mathjax || '';
    d.dataset.front = count('#stage');
    document.getElementById('flip').click();
    wait(() => count('#stage .solution') > 1 || failed(), () => {
      d.dataset.back = count('#stage .solution');
      window.examkitShow('notes');
      wait(() => count('#notes-out') > 0 || failed(), () => {
        d.dataset.notes = count('#notes-out');
        d.dataset.errors = JSON.stringify(window.__mathErrors);
        document.body.appendChild(d);
      }, 80);
    }, 80);
  }, 80);
})();
</script>
"""
LISTENER = ('<meta charset="utf-8"><script>window.__mathErrors=[];'
            'addEventListener("error",e=>__mathErrors.push(String(e.message||e)));'
            'addEventListener("unhandledrejection",e=>__mathErrors.push("rejection: "+String(e.reason)));</script>')


@pytest.mark.skipif(chrome.find_chrome() is None, reason="no headless Chrome found (set EXAMKIT_CHROME)")
def test_browser_typesets_card_front_back_and_notes(tmp_path):
    ex = math_exam(tmp_path)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    page = ex / "build" / "smoke.html"
    page.write_text(html.replace('<meta charset="utf-8">', LISTENER, 1) + PROBE, encoding="utf-8")
    dom = chrome.dump_dom(page, tmp_path / "profile", budget_ms=20000)
    m = re.search(r'<div id="mathsmoke"([^>]*)>', dom)
    assert m, "probe element missing: the page's scripts did not finish"
    got = dict(re.findall(r'data-([a-z]+)="([^"]*)"', m.group(1)))
    if got.get("state") == "failed":
        pytest.skip("MathJax did not load from cdnjs (no network?)")
    assert json.loads(got["errors"].replace("&quot;", '"')) == []
    assert int(got["front"]) >= 1, got          # $x_1^2$ in the question (the first card shown)
    assert int(got["back"]) >= 2, got           # $$...$$ and \(...\) in the answer
    assert int(got["notes"]) >= 5, got         # the formulas of the note section
