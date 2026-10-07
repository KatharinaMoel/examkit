import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "engine" / "check_tracked.py"


def run(lines):
    return subprocess.run([sys.executable, str(SCRIPT)], input="\n".join(lines) + "\n", capture_output=True, text=True)


def test_detects_planted_error_first():
    r = run(["engine/build.py", "exams/aws-clf-c02/cards/guide.json"])
    assert r.returncode == 1 and "exams/aws-clf-c02/cards/guide.json" in r.stderr


def test_exams_content_is_forbidden_but_gitkeep_allowed():
    assert run(["exams/.gitkeep"]).returncode == 0
    assert run(["exams/x/exam.json"]).returncode == 1


def test_sources_and_build_anywhere_are_forbidden():
    assert run(["foo/sources/a.md"]).returncode == 1
    assert run(["example/build/index.html"]).returncode == 1
    assert run(["build/x"]).returncode == 1


def test_example_sources_allowed_and_names_merely_containing_the_words():
    r = run(["example/sources/dummy.md", "example/sources/.gitkeep", "engine/build.py", "docs/sources.md"])
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_lists_every_offender():
    r = run(["exams/a/x.json", "exams/b/y.json"])
    assert r.returncode == 1 and "exams/a/x.json" in r.stderr and "exams/b/y.json" in r.stderr


def test_git_quoted_non_ascii_path_is_still_caught():
    r = run(['"exams/Pr\\303\\274fung/x.md"', '"example/sources/\\303\\274.md"'])
    assert r.returncode == 1 and "exams/Pr" in r.stderr and "example/sources" not in r.stderr
