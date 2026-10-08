"""Headless Chrome for tests and the print pack: find it, dump a page's DOM, print a PDF.

Search order: $EXAMKIT_CHROME (a command line, split like a shell would), then
google-chrome, google-chrome-stable, chromium, chromium-browser on PATH, then the
Flatpak com.google.Chrome. Flatpak Chrome sees only the directories handed to it
with --filesystem=, so every directory a call reads or writes goes into `paths`.

Chrome's own console log (--enable-logging=stderr) printed nothing for page errors
in the Flatpak build tested on 2026-10-07 (Chrome 154), so tests catch errors with
an in-page listener and read the result from the dumped DOM (tests/test_smoke.py).

profile_dir is optional: without it every call gets a fresh temporary profile that is removed
afterwards, also on errors. A call that times out kills Chrome's whole process group: Chrome
starts in its own session, because a timed-out Flatpak Chrome otherwise keeps running
(17 processes left after a plain subprocess.run timeout on 2026-10-08).
"""
import contextlib
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

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
    """Run Chrome in a new session; on timeout (or any interruption) kill its process group, then re-raise."""
    p = subprocess.Popen([*prefix, *COMMON, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, errors="replace", start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except BaseException:
        _kill_group(p)
        raise
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def _kill_group(p):
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(p.pid, signal.SIGKILL)
    p.kill()
    p.wait()
    # No communicate(): a process that left the group could hold the pipes open forever.
    for pipe in (p.stdout, p.stderr):
        pipe.close()


@contextlib.contextmanager
def _profile(profile_dir):
    """The given profile directory (created if needed), or a temporary one removed on exit."""
    if profile_dir is not None:
        d = pathlib.Path(profile_dir).resolve()
        d.mkdir(parents=True, exist_ok=True)
        yield d
        return
    with temporary_profile() as d:
        yield d


@contextlib.contextmanager
def temporary_profile():
    """A fresh Chrome profile directory, removed on exit (also on errors); a failed removal is reported."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="examkit-chrome-")).resolve()
    try:
        yield d
    finally:
        # Not hidden: a Chrome child still writing after exit can keep the profile alive,
        # and silent leftovers would pile up in the temp directory.
        try:
            shutil.rmtree(d)
        except OSError as e:
            print(f"  ! temporary Chrome profile {d} could not be removed ({e}); delete it by hand", file=sys.stderr)


def dump_dom(html_path, profile_dir=None, budget_ms=3000, timeout=90):
    """DOM of the page after its scripts ran (string starting at <!DOCTYPE or <html).

    --virtual-time-budget lets timers and promises run for budget_ms of page time first.
    The dump is preceded by Chrome log lines on stdout, so the DOM is cut out by its start tag.
    """
    html_path = pathlib.Path(html_path).resolve()
    with _profile(profile_dir) as profile:
        prefix = find_chrome([html_path.parent, profile])
        if prefix is None:
            raise RuntimeError("no headless Chrome found (set EXAMKIT_CHROME)")
        r = _run(prefix, [f"--user-data-dir={profile}", f"--virtual-time-budget={budget_ms}", "--dump-dom", html_path.as_uri()], timeout)
    m = DOM_START.search(r.stdout)
    if r.returncode != 0 or not m:
        raise RuntimeError(f"chrome --dump-dom failed (exit {r.returncode}): {r.stderr[-800:]}")
    return r.stdout[m.start():]


def print_pdf(html_path, pdf_path, profile_dir=None, budget_ms=15000, timeout=180):
    """Print html_path to pdf_path without header/footer; returns pdf_path."""
    html_path, pdf_path = pathlib.Path(html_path).resolve(), pathlib.Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.unlink(missing_ok=True)
    with _profile(profile_dir) as profile:
        prefix = find_chrome([html_path.parent, pdf_path.parent, profile])
        if prefix is None:
            raise RuntimeError("no headless Chrome found (set EXAMKIT_CHROME)")
        r = _run(prefix, [f"--user-data-dir={profile}", f"--virtual-time-budget={budget_ms}", "--no-pdf-header-footer",
                          f"--print-to-pdf={pdf_path}", html_path.as_uri()], timeout)
    if r.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"chrome --print-to-pdf failed (exit {r.returncode}): {r.stderr[-800:]}")
    return pdf_path
