import hashlib
import json
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import chrome  # noqa: E402

EX = ROOT / "example"
PRINT_PY = ROOT / "engine" / "print.py"


def run_print(exam_dir, *args):
    return subprocess.run([sys.executable, str(PRINT_PY), str(exam_dir), *args], capture_output=True, text=True)


def copy_example(tmp_path):
    dst = tmp_path / "ex"
    shutil.copytree(EX, dst, ignore=shutil.ignore_patterns("build"))
    return dst


def edit_exam(exam_dir, fn):
    f = exam_dir / "exam.json"
    exam = json.loads(f.read_text(encoding="utf-8"))
    fn(exam)
    f.write_text(json.dumps(exam, ensure_ascii=False, indent=1), encoding="utf-8")


def test_detects_planted_error_first(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e["notes"][0]["items"].append({"slug": "does-not-exist"}))
    r = run_print(ex, "--html-only")
    assert r.returncode == 1 and "does-not-exist" in r.stderr and "Traceback" not in r.stderr
    assert not (ex / "build" / "print").exists()


def test_html_only_writes_one_file_per_note_and_a_complete_one(tmp_path):
    ex = copy_example(tmp_path)
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    out = ex / "build" / "print"
    assert sorted(p.name for p in out.iterdir()) == ["00-complete.html", "01-intro.html"]
    assert r.stdout.strip() == str(out)
    assert "1. read config" in r.stderr and "3. --html-only" in r.stderr


def test_part_has_title_mermaid_and_xrefs_as_text(tmp_path):
    ex = copy_example(tmp_path)
    assert run_print(ex, "--html-only").returncode == 0
    html = (ex / "build" / "print" / "01-intro.html").read_text(encoding="utf-8")
    assert html.lower().startswith("<!doctype html>")
    assert "<h1>Intro</h1>" in html and "The only note" in html and "Example Exam" in html
    assert '<pre class="mermaid">' in html and "mermaid.min.js" in html
    assert 'href="#note-' not in html and '<span class="xref">intro</span>' in html
    assert '<section class="part">' in html


def test_complete_follows_config_order_and_breaks_pages(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "zeta.md").write_text("# Zeta\n\nSecond note.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "Reading", "items": [{"slug": "zeta"}, {"slug": "intro"}]}]))
    assert run_print(ex, "--html-only").returncode == 0
    out = ex / "build" / "print"
    assert sorted(p.name for p in out.iterdir()) == ["00-complete.html", "01-zeta.html", "02-intro.html"]
    html = (out / "00-complete.html").read_text(encoding="utf-8")
    assert html.index("<h1>Zeta</h1>") < html.index("<h1>Intro</h1>")
    assert html.count('<section class="part">') == 2
    assert "break-before: page" in html


def test_no_notes_config_prints_every_note_sorted(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "alpha.md").write_text("# Alpha\n\nFirst by name.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.pop("notes"))
    assert run_print(ex, "--html-only").returncode == 0
    assert sorted(p.name for p in (ex / "build" / "print").iterdir()) == ["00-complete.html", "01-alpha.html", "02-intro.html"]


def test_mermaid_script_only_when_needed(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "plain.md").write_text("# Plain\n\nNo diagram.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "plain"}]}]))
    assert run_print(ex, "--html-only").returncode == 0
    assert "mermaid.min.js" not in (ex / "build" / "print" / "01-plain.html").read_text(encoding="utf-8")


def test_html_is_deterministic_except_stamp(tmp_path):
    ex = copy_example(tmp_path)
    blank = lambda s: re.sub(r'data-generated="[^"]*"', 'data-generated=""', s)
    assert run_print(ex, "--html-only").returncode == 0
    a = (ex / "build" / "print" / "00-complete.html").read_text(encoding="utf-8")
    assert run_print(ex, "--html-only").returncode == 0
    b = (ex / "build" / "print" / "00-complete.html").read_text(encoding="utf-8")
    assert 'data-generated="' in a and blank(a) == blank(b)


def test_leading_body_heading_equal_to_title_is_dropped(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "other.md").write_text("# Different\n\nBody.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "intro"}, {"slug": "other", "title": "Configured"}]}]))
    assert run_print(ex, "--html-only").returncode == 0
    out = ex / "build" / "print"
    assert (out / "01-intro.html").read_text(encoding="utf-8").count("<h1>Intro</h1>") == 1
    other = (out / "02-other.html").read_text(encoding="utf-8")
    assert "<h1>Configured</h1>" in other and "<h1>Different</h1>" in other   # differing heading stays


def test_second_run_removes_files_of_the_previous_order(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "zeta.md").write_text("# Zeta\n\nSecond note.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "intro"}, {"slug": "zeta"}]}]))
    assert run_print(ex, "--html-only").returncode == 0
    out = ex / "build" / "print"
    (out / "01-intro.pdf").write_bytes(b"%PDF-stale")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "zeta"}, {"slug": "intro"}]}]))
    assert run_print(ex, "--html-only").returncode == 0
    assert sorted(p.name for p in out.iterdir()) == ["00-complete.html", "01-zeta.html", "02-intro.html"]


def test_subfolder_slug_prints_into_a_flat_file(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "sub").mkdir()
    (ex / "notes" / "sub" / "deep.md").write_text("# Deep\n\nNested note.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "sub/deep"}]}]))
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in (ex / "build" / "print").iterdir()) == ["00-complete.html", "01-sub-deep.html"]


def test_without_chrome_pdf_step_fails_clearly(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    monkeypatch.setenv("EXAMKIT_CHROME", "/bin/false")
    r = run_print(ex)
    assert r.returncode == 1 and "print-to-pdf failed" in r.stderr and "Traceback" not in r.stderr
    assert (ex / "build" / "print" / "01-intro.html").exists()          # HTML stays, so the user can print by hand


def test_nonexistent_chrome_binary_fails_clearly(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    monkeypatch.setenv("EXAMKIT_CHROME", str(tmp_path / "no-such-chrome"))
    r = run_print(ex)
    assert r.returncode == 1 and "Traceback" not in r.stderr and "EXAMKIT_CHROME" in r.stderr
    assert (ex / "build" / "print" / "01-intro.html").exists()


@pytest.mark.skipif(chrome.find_chrome() is None, reason="no headless Chrome found (set EXAMKIT_CHROME)")
def test_pdfs_are_written_next_to_the_html(tmp_path):
    ex = copy_example(tmp_path)
    r = run_print(ex)
    assert r.returncode == 0, r.stderr
    out = ex / "build" / "print"
    for name in ("00-complete.pdf", "01-intro.pdf"):
        data = (out / name).read_bytes()
        assert data[:5] == b"%PDF-" and len(data) > 2000, name
    assert "ok: 2 pdf files" in r.stderr


def test_mermaid_page_carries_a_load_failure_guard(tmp_path):
    ex = copy_example(tmp_path)
    assert run_print(ex, "--html-only").returncode == 0
    html = (ex / "build" / "print" / "01-intro.html").read_text(encoding="utf-8")
    assert "typeof mermaid === 'undefined'" in html and "Diagrams not rendered" in html and ".warn" in html


# --- fake Chrome: logs every call; --print-to-pdf writes a fake PDF; --dump-dom returns the page,
# with every Mermaid block drawn as <svg> ("svg") or left as source ("nosvg", as when mermaid.js fails) ---
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
    if %(mode)r == "fail":
        sys.exit(4)
    html = page.read_text()
    if %(mode)r == "svg":
        html = re.sub(r'<pre class="mermaid">.*?</pre>', '<pre class="mermaid" data-processed="true"><svg id="m"><g></g></svg></pre>', html, flags=re.S)
    print(html)
"""


def fake_chrome(tmp_path, monkeypatch, mode):
    log = tmp_path / "calls.log"
    script = tmp_path / "fake_chrome.py"
    script.write_text(FAKE % {"log": str(log), "mode": mode}, encoding="utf-8")
    monkeypatch.setenv("EXAMKIT_CHROME", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}")
    return log


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def dom_calls(log):
    return [pathlib.Path(a[-1]).name for a in calls(log) if "--dump-dom" in a]


def test_mermaid_without_svg_fails_the_run(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    log = fake_chrome(tmp_path, monkeypatch, "nosvg")
    r = run_print(ex)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert "01-intro.html" in r.stderr and "(note intro)" in r.stderr and "not rendered" in r.stderr
    assert (ex / "build" / "print" / "01-intro.pdf").exists()        # the PDFs stay for inspection
    assert sorted(dom_calls(log)) == ["00-complete.html", "01-intro.html"]


def test_mermaid_with_svg_passes(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    log = fake_chrome(tmp_path, monkeypatch, "svg")
    r = run_print(ex)
    assert r.returncode == 0, r.stderr
    assert "diagrams" in r.stderr and "ok: 2 pdf files" in r.stderr
    assert sorted(dom_calls(log)) == ["00-complete.html", "01-intro.html"]


def test_dom_check_failure_is_reported_without_traceback(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    fake_chrome(tmp_path, monkeypatch, "fail")
    r = run_print(ex)
    assert r.returncode == 1 and "Traceback" not in r.stderr and "dump-dom failed" in r.stderr


def test_notes_without_mermaid_skip_the_dom_check(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    (ex / "notes" / "plain.md").write_text("# Plain\n\nNo diagram.\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "plain"}]}]))
    log = fake_chrome(tmp_path, monkeypatch, "fail")          # a DOM call would fail the run
    r = run_print(ex)
    assert r.returncode == 0, r.stderr
    assert dom_calls(log) == [] and len(calls(log)) == 2


def test_html_only_runs_no_browser(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    log = fake_chrome(tmp_path, monkeypatch, "nosvg")
    assert run_print(ex, "--html-only").returncode == 0
    assert calls(log) == []


def test_chrome_profile_is_temporary_and_removed(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    (ex / "build" / "print" / ".chrome-profile").mkdir(parents=True)     # left by older versions
    log = fake_chrome(tmp_path, monkeypatch, "svg")
    assert run_print(ex).returncode == 0
    profiles = {a.split("=", 1)[1] for c in calls(log) for a in c if a.startswith("--user-data-dir=")}
    assert len(profiles) == 1                                            # one profile per run
    profile = pathlib.Path(profiles.pop())
    assert profile.parent == pathlib.Path(tempfile.gettempdir()).resolve() and not profile.exists()
    assert not (ex / "build" / "print" / ".chrome-profile").exists()


def test_chrome_profile_is_removed_when_printing_fails(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    script = tmp_path / "failing_chrome.py"
    log = tmp_path / "calls.log"
    script.write_text(f"import json, sys\nopen({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\nsys.exit(2)\n")
    monkeypatch.setenv("EXAMKIT_CHROME", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}")
    r = run_print(ex)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    profile = pathlib.Path(next(a.split("=", 1)[1] for a in calls(log)[0] if a.startswith("--user-data-dir=")))
    assert not profile.exists()


def test_mermaid_markup_shown_as_inline_code_is_no_diagram(tmp_path, monkeypatch):
    ex = copy_example(tmp_path)
    (ex / "notes" / "doc.md").write_text('# Doc\n\nWrite `<pre class="mermaid">` around a diagram.\n', encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "doc"}]}]))
    log = fake_chrome(tmp_path, monkeypatch, "fail")          # a DOM call would fail the run
    r = run_print(ex)
    assert r.returncode == 0, r.stderr
    assert dom_calls(log) == []
    html = (ex / "build" / "print" / "01-doc.html").read_text(encoding="utf-8")
    assert 'class="mermaid"' in html and "mermaid.min.js" not in html


# --- relative images ---
def asset(slug, source):
    """Published path of an image: assets/<slug>/<first 10 hex of sha1(resolved source)>-<basename>."""
    source = pathlib.Path(source).resolve()
    return f"assets/{slug}/{hashlib.sha1(str(source).encode()).hexdigest()[:10]}-{source.name}"


PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def image_note(ex, body, slug="pics"):
    f = ex / "notes" / f"{slug}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"# Pics\n\n{body}\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": slug}]}]))


def test_relative_image_is_copied_and_rewritten(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "img").mkdir()
    (ex / "notes" / "img" / "x y.png").write_bytes(PNG)
    image_note(ex, "![a diagram](img/x%20y.png) and ![remote](https://example.org/r.png) and ![inline](data:image/png;base64,AAAA) and ![abs](/srv/abs.png)")
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    out = ex / "build" / "print"
    a = asset("pics", ex / "notes" / "img" / "x y.png")
    assert (out / a).read_bytes() == PNG
    for name in ("01-pics.html", "00-complete.html"):
        html = (out / name).read_text(encoding="utf-8")
        assert f'src="{a.replace(" ", "%20")}"' in html, name
        assert 'src="https://example.org/r.png"' in html and 'src="data:image/png;base64,AAAA"' in html
        assert 'src="/srv/abs.png"' in html
    assert "warning" not in r.stderr


def test_missing_image_is_a_warning_not_a_crash(tmp_path):
    ex = copy_example(tmp_path)
    image_note(ex, "![gone](img/missing.png)")
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    assert "warning" in r.stderr and "img/missing.png" in r.stderr and "Traceback" not in r.stderr
    assert 'src="img/missing.png"' in (ex / "build" / "print" / "01-pics.html").read_text(encoding="utf-8")


def test_image_outside_the_notes_dir_is_refused(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "secret.png").write_bytes(PNG)
    image_note(ex, "![out](../secret.png)")
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    assert "warning" in r.stderr and "../secret.png" in r.stderr and "outside" in r.stderr
    assert not (ex / "build" / "print" / "assets").exists() or not any((ex / "build" / "print" / "assets").rglob("*.png"))


def test_symlink_inside_notes_pointing_outside_is_refused(tmp_path):
    # the link lives in notes/, its target does not: resolve() follows it, so it is refused like ../
    ex = copy_example(tmp_path)
    (ex / "secret.png").write_bytes(PNG)
    (ex / "notes" / "img").mkdir()
    (ex / "notes" / "img" / "link.png").symlink_to(ex / "secret.png")
    image_note(ex, "![out](img/link.png)")
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    assert "warning" in r.stderr and "img/link.png" in r.stderr and "outside" in r.stderr
    assets = ex / "build" / "print" / "assets"
    assert not assets.exists() or not any(assets.rglob("*.png"))
    assert 'src="img/link.png"' in (ex / "build" / "print" / "01-pics.html").read_text(encoding="utf-8")


def test_subfolder_note_may_reach_up_inside_the_notes_dir(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "img").mkdir()
    (ex / "notes" / "img" / "x.png").write_bytes(PNG)
    image_note(ex, "![up](../img/x.png)", slug="sub/deep")
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    out = ex / "build" / "print"
    a = asset("sub/deep", ex / "notes" / "img" / "x.png")
    assert (out / a).read_bytes() == PNG
    assert f'src="{a}"' in (out / "01-sub-deep.html").read_text(encoding="utf-8")
    assert "warning" not in r.stderr


def test_second_run_clears_old_assets(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "img").mkdir()
    (ex / "notes" / "img" / "x.png").write_bytes(PNG)
    image_note(ex, "![a](img/x.png)")
    assert run_print(ex, "--html-only").returncode == 0
    image_note(ex, "No image any more.")
    assert run_print(ex, "--html-only").returncode == 0
    assert not (ex / "build" / "print" / "assets").exists()


def test_images_of_different_notes_never_overwrite_each_other(tmp_path):
    ex = copy_example(tmp_path)
    notes = ex / "notes"
    (notes / "b").mkdir()
    (notes / "a").mkdir()
    (notes / "b" / "x.png").write_bytes(PNG + b"first")
    (notes / "x.png").write_bytes(PNG + b"second")
    (notes / "a.md").write_text("# A\n\n![one](b/x.png)\n", encoding="utf-8")
    (notes / "a" / "b.md").write_text("# AB\n\n![two](../x.png)\n", encoding="utf-8")
    edit_exam(ex, lambda e: e.__setitem__("notes", [{"group": "", "items": [{"slug": "a"}, {"slug": "a/b"}]}]))
    r = run_print(ex, "--html-only")
    assert r.returncode == 0, r.stderr
    out = ex / "build" / "print"
    for page_name, slug, source, data in (("01-a.html", "a", notes / "b" / "x.png", PNG + b"first"),
                                          ("02-a-b.html", "a/b", notes / "x.png", PNG + b"second")):
        src = re.search(r'<img[^>]*src="([^"]*)"', (out / page_name).read_text(encoding="utf-8")).group(1)
        assert (out / src).read_bytes() == data, page_name          # each page shows its own image
        assert src == asset(slug, source), page_name


def test_print_run_reports_a_profile_that_cannot_be_removed(tmp_path, monkeypatch, capsys):
    from engine import print as print_mod
    ex = copy_example(tmp_path)
    log = fake_chrome(tmp_path, monkeypatch, "svg")
    real_rmtree = shutil.rmtree
    seen = []

    def rmtree(path, *a, **k):
        real_rmtree(path, *a, **k)
        if pathlib.Path(path).name.startswith("examkit-chrome-"):
            seen.append(str(path))
            raise OSError(16, "Device or resource busy", str(path))

    monkeypatch.setattr(shutil, "rmtree", rmtree)
    monkeypatch.setattr(sys, "argv", ["print.py", str(ex)])
    print_mod.main()
    err = capsys.readouterr().err
    assert len(seen) == 1 and any(line.startswith("  ! ") and seen[0] in line for line in err.splitlines()), (seen, err)
    assert calls(log)
