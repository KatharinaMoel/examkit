"""Headless Chrome for tests and the print pack: find it, dump a page's DOM, print a PDF.

Search order: $EXAMKIT_CHROME (a command line, split like a shell would), then
google-chrome, google-chrome-stable, chromium, chromium-browser on PATH, then the
Flatpak com.google.Chrome. Flatpak Chrome sees only the directories handed to it
with --filesystem=, so every directory a call reads or writes goes into `paths`.

Chrome's own console log (--enable-logging=stderr) printed nothing for page errors
in the Flatpak build tested on 2026-10-07 (Chrome 154), so tests catch errors with
an in-page listener and read the result from the dumped DOM (tests/test_smoke.py).
"""
import os
import pathlib
import re
import shlex
import shutil
import subprocess

FLATPAK_ID = "com.google.Chrome"
NATIVE = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
COMMON = ("--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check")
DOM_START = re.compile(r"^(?:<!doctype|<html)", re.I | re.M)


def find_chrome(paths=()):
    """Command prefix for headless Chrome, or None. `paths`: directories Chrome must read or write."""
    env = os.environ.get("EXAMKIT_CHROME")
    if env:
        return shlex.split(env)
    for name in NATIVE:
        found = shutil.which(name)
        if found:
            return [found]
    if shutil.which("flatpak") and subprocess.run(["flatpak", "info", FLATPAK_ID], capture_output=True).returncode == 0:
        grants = [f"--filesystem={pathlib.Path(p).resolve()}" for p in paths]
        return ["flatpak", "run", *grants, FLATPAK_ID]
    return None


def _run(prefix, args, timeout):
    return subprocess.run([*prefix, *COMMON, *args], capture_output=True, text=True, errors="replace", timeout=timeout)


def dump_dom(html_path, profile_dir, budget_ms=3000, timeout=90):
    """DOM of the page after its scripts ran (string starting at <!DOCTYPE or <html).

    --virtual-time-budget lets timers and promises run for budget_ms of page time first.
    The dump is preceded by Chrome log lines on stdout, so the DOM is cut out by its start tag.
    """
    html_path, profile_dir = pathlib.Path(html_path).resolve(), pathlib.Path(profile_dir).resolve()
    prefix = find_chrome([html_path.parent, profile_dir])
    if prefix is None:
        raise RuntimeError("no headless Chrome found (set EXAMKIT_CHROME)")
    profile_dir.mkdir(parents=True, exist_ok=True)
    r = _run(prefix, [f"--user-data-dir={profile_dir}", f"--virtual-time-budget={budget_ms}", "--dump-dom", html_path.as_uri()], timeout)
    m = DOM_START.search(r.stdout)
    if r.returncode != 0 or not m:
        raise RuntimeError(f"chrome --dump-dom failed (exit {r.returncode}): {r.stderr[-800:]}")
    return r.stdout[m.start():]


def print_pdf(html_path, pdf_path, profile_dir, budget_ms=15000, timeout=180):
    """Print html_path to pdf_path without header/footer; returns pdf_path."""
    html_path, pdf_path = pathlib.Path(html_path).resolve(), pathlib.Path(pdf_path).resolve()
    profile_dir = pathlib.Path(profile_dir).resolve()
    prefix = find_chrome([html_path.parent, pdf_path.parent, profile_dir])
    if prefix is None:
        raise RuntimeError("no headless Chrome found (set EXAMKIT_CHROME)")
    profile_dir.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.unlink(missing_ok=True)
    r = _run(prefix, [f"--user-data-dir={profile_dir}", f"--virtual-time-budget={budget_ms}", "--no-pdf-header-footer",
                      f"--print-to-pdf={pdf_path}", html_path.as_uri()], timeout)
    if r.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"chrome --print-to-pdf failed (exit {r.returncode}): {r.stderr[-800:]}")
    return pdf_path
