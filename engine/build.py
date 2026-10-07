#!/usr/bin/env python3
"""Build one exam: validate cards, embed data into the template, write build/.

Usage: python3 engine/build.py <exam_dir> [--check]
Diagnostics go to stderr, the output path to stdout. Exit 1 on validation errors.
"""
import argparse
import datetime
import html as html_mod
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from engine import validate as v  # noqa: E402

TEMPLATE = HERE / "template" / "index.html"
EMPTY_PLAN = {"stand": "", "links_alle": None, "tage": []}
PLACEHOLDERS = ("TITLE", "CONFIG", "KARTEN", "PLAN", "LOOKUP", "BUILD")
PLACEHOLDER_RE = re.compile(r"/\*(" + "|".join(PLACEHOLDERS) + r")\*/")


def say(msg):
    print(msg, file=sys.stderr)


def jdump(obj):
    # "</" would end the <script> block early, "<!--" would switch the parser into script-escaped mode
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\u0021--")


def git_head(path):
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def notes_head(notes_dir):
    try:
        top = subprocess.run(["git", "-C", str(notes_dir), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None
    return None if pathlib.Path(top).resolve() == HERE.parent.resolve() else git_head(notes_dir)


def check_exam(exam):
    """Schema check for exam.json; returns a list of error strings."""
    errors = []
    for key in ("id", "title", "storage_key", "grading_prompt", "notes_dir"):
        if not isinstance(exam.get(key), str) or not exam.get(key):
            errors.append(f"exam.{key}: missing or not a non-empty string")
    decks = exam.get("decks")
    if not isinstance(decks, dict) or not decks:
        errors.append("exam.decks: missing or not a non-empty object")
    elif "alle" in decks:
        errors.append("exam.decks: key 'alle' is reserved")
    if not isinstance(exam.get("languages"), list):
        errors.append("exam.languages: missing or not a list")
    return errors


def render(template, values):
    """Substitute every placeholder in one pass, so placeholder text inside data stays untouched."""
    for name in PLACEHOLDERS:
        n = template.count(f"/*{name}*/")
        if n != 1:
            raise SystemExit(f"template: placeholder /*{name}*/ found {n} times")
    return PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exam_dir", type=pathlib.Path)
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    a = ap.parse_args()
    ex = a.exam_dir.resolve()

    say(f"1. read config        exam.json, coverage.json, cards/*.json from {ex}")
    exam = json.loads((ex / "exam.json").read_text(encoding="utf-8"))
    coverage = json.loads((ex / "coverage.json").read_text(encoding="utf-8"))
    cards = v.load_cards(ex / "cards")
    exam_errors = check_exam(exam)
    notes_dir = pathlib.Path(exam.get("notes_dir") or "notes").expanduser()
    if not notes_dir.is_absolute():
        notes_dir = ex / notes_dir
    sources_dir = ex / "sources"
    plan_file = ex / "plan.json"
    plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else EMPTY_PLAN

    say(f"2. validate           {len(cards)} cards: fields, decks, priorities, languages, resolvable src")
    errors = exam_errors + v.validate(cards, exam, coverage, notes_dir, sources_dir)
    if errors:
        say("\n".join(errors))
        say(f"{len(errors)} error(s). Nothing written.")
        sys.exit(1)

    for c in cards:
        c.pop("_file", None)
    cards.sort(key=lambda c: c["p"])
    model_cards = sum(c["ctx_src"] == "model" for c in cards)
    by_deck = {}
    for c in cards:
        by_deck[c["deck"]] = by_deck.get(c["deck"], 0) + 1
    say(f"   ok: {len(cards)} cards, decks {by_deck}, model-knowledge cards: {model_cards}")
    if a.check:
        say("3. --check: done, nothing written")
        return

    manifest = {
        "exam_id": exam["id"], "exam_code": exam.get("exam_code"),
        "built_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        # notes_head: HEAD of whatever repo contains notes_dir - for a notes dir inside examkit
        # (e.g. example/notes) that would be examkit's own HEAD, so it is reported as None.
        "repo_head": git_head(HERE.parent), "notes_head": notes_head(notes_dir),
        "cards": len(cards), "by_deck": by_deck, "model_cards": model_cards,
        "by_priority": {p: sum(c["p"] == p for c in cards) for p in (1, 2, 3)},
    }
    say("3. render             embed config, cards, plan, lookup and manifest into template")
    html = render(TEMPLATE.read_text(encoding="utf-8"), {
        "TITLE": html_mod.escape(f"{exam['title']} · Karteikasten"),
        "CONFIG": jdump(exam), "KARTEN": jdump(cards), "PLAN": jdump(plan),
        "LOOKUP": "null", "BUILD": jdump(manifest)})

    out = ex / "build"
    say(f"4. write              {out/'index.html'} ({len(html)//1024} KB), build.json")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "build.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(out / "index.html")


if __name__ == "__main__":
    main()
