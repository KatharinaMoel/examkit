"""engine/chrome.py with a fake Chrome (a Python script set as EXAMKIT_CHROME): profiles and timeouts."""
import json
import pathlib
import shlex
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import chrome  # noqa: E402

FAKE = '''
import json, pathlib, subprocess, sys, time
args = sys.argv[1:]
log = pathlib.Path(%(log)r)
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")
if %(mode)r == "fail":
    sys.exit(3)
if %(mode)r == "hang":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    pathlib.Path(%(pids)r).write_text(json.dumps([child.pid, __import__("os").getpid()]))
    time.sleep(120)
page = pathlib.Path(args[-1][len("file://"):])
for a in args:
    if a.startswith("--print-to-pdf="):
        pathlib.Path(a.split("=", 1)[1]).write_bytes(b"%%PDF-fake " * 300)
if "--dump-dom" in args:
    print("log line")
    print(page.read_text())
'''


def fake_chrome(tmp_path, monkeypatch, mode="ok"):
    """Install a fake Chrome; returns (log file with one JSON argv per call, pid file)."""
    log, pids = tmp_path / "calls.log", tmp_path / "pids.json"
    script = tmp_path / "fake_chrome.py"
    script.write_text(FAKE % {"log": str(log), "mode": mode, "pids": str(pids)}, encoding="utf-8")
    monkeypatch.setenv("EXAMKIT_CHROME", f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}")
    return log, pids


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def profile_of(argv):
    return next(a.split("=", 1)[1] for a in argv if a.startswith("--user-data-dir="))


def alive(pid):
    try:
        state = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state != "Z"


def page(tmp_path):
    p = tmp_path / "page.html"
    p.write_text("<!doctype html><html><body>hi</body></html>", encoding="utf-8")
    return p


def test_detects_planted_error_first(tmp_path, monkeypatch):
    monkeypatch.setenv("EXAMKIT_CHROME", "/bin/false")
    with pytest.raises(RuntimeError, match="dump-dom failed"):
        chrome.dump_dom(page(tmp_path))


def test_without_profile_dir_a_temporary_one_is_used_and_removed(tmp_path, monkeypatch):
    log, _ = fake_chrome(tmp_path, monkeypatch)
    dom = chrome.dump_dom(page(tmp_path))
    assert dom.startswith("<!doctype html>")
    chrome.print_pdf(page(tmp_path), tmp_path / "out.pdf")
    profiles = [pathlib.Path(profile_of(a)) for a in calls(log)]
    assert len(profiles) == 2 and profiles[0] != profiles[1]
    for p in profiles:
        assert p.parent == pathlib.Path(tempfile.gettempdir()).resolve() and not p.exists()


def test_temporary_profile_is_removed_on_failure_too(tmp_path, monkeypatch):
    log, _ = fake_chrome(tmp_path, monkeypatch, mode="fail")
    with pytest.raises(RuntimeError, match="exit 3"):
        chrome.print_pdf(page(tmp_path), tmp_path / "out.pdf")
    profile = pathlib.Path(profile_of(calls(log)[0]))
    assert profile.parent == pathlib.Path(tempfile.gettempdir()).resolve() and not profile.exists()


def test_given_profile_dir_is_used_and_kept(tmp_path, monkeypatch):
    log, _ = fake_chrome(tmp_path, monkeypatch)
    chrome.dump_dom(page(tmp_path), tmp_path / "prof")
    assert profile_of(calls(log)[0]) == str((tmp_path / "prof").resolve()) and (tmp_path / "prof").is_dir()


def test_timeout_kills_every_process_of_the_call(tmp_path, monkeypatch):
    log, pids = fake_chrome(tmp_path, monkeypatch, mode="hang")
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        chrome.dump_dom(page(tmp_path), timeout=3)
    assert time.monotonic() - started < 30
    child, parent = json.loads(pids.read_text())
    deadline = time.monotonic() + 5
    while (alive(child) or alive(parent)) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not alive(parent), "fake chrome still running"
    assert not alive(child), "a process started by chrome survived the timeout"
    assert not pathlib.Path(profile_of(calls(log)[0])).exists()
