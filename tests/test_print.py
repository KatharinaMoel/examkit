import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
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


import pytest
sys.path.insert(0, str(ROOT))
from engine import chrome  # noqa: E402


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
