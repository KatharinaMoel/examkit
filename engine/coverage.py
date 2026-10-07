"""Coverage: which guide items (tasks, services, concepts) have cards and notes.

Counting uses explicit markers only: a card's ``covers`` list and a note's
frontmatter ``covers`` list. No text search.
"""
import pathlib

from engine import notes as notes_mod
from engine import validate as v

KINDS = ("tasks", "services", "concepts")
STATES = ("green", "yellow", "red")


def notes_covers(notes_dir):
    """id -> list of note slugs (sorted by file name) whose frontmatter covers the id."""
    by_id = {}
    for f in sorted(pathlib.Path(notes_dir).glob("*.md")):
        meta, _ = notes_mod.split_frontmatter(f.read_text(encoding="utf-8"))
        for cid in notes_mod.note_covers(meta):
            by_id.setdefault(cid, []).append(f.stem)
    return by_id


def status(n_cards, n_notes):
    return "green" if n_cards and n_notes else "yellow" if n_cards or n_notes else "red"


def compute(coverage, cards, notes_dir):
    """Return (report, errors). The report mirrors coverage.json; every item row gains
    cards, p1, notes (slugs) and status. errors lists note ids that are not in coverage.json."""
    ids = v.coverage_ids(coverage)
    by_note = notes_covers(notes_dir)
    errors = [f"note {slug}.md: covers '{cid}' is not an id in coverage.json"
              for cid, slugs in sorted(by_note.items()) if cid not in ids for slug in slugs]
    n_cards, n_p1 = {}, {}
    for c in cards:
        for cid in c.get("covers") or []:
            n_cards[cid] = n_cards.get(cid, 0) + 1
            if c.get("p") == 1:
                n_p1[cid] = n_p1.get(cid, 0) + 1

    def row(item):
        cid = item["id"]
        r = dict(item)
        r.update(cards=n_cards.get(cid, 0), p1=n_p1.get(cid, 0), notes=by_note.get(cid, []))
        r["status"] = status(r["cards"], len(r["notes"]))
        return r

    report = {"domains": [], "services": [row(s) for s in coverage.get("services", [])],
              "concepts": [row(c) for c in coverage.get("concepts", [])]}
    for d in coverage.get("domains", []):
        dd = {k: d[k] for k in ("id", "title", "weight") if k in d}
        dd["tasks"] = [row(t) for t in d.get("tasks", [])]
        report["domains"].append(dd)
    rows = {"tasks": [t for d in report["domains"] for t in d["tasks"]],
            "services": report["services"], "concepts": report["concepts"]}
    report["summary"] = {k: {"total": len(rs), **{s: sum(r["status"] == s for r in rs) for s in STATES}}
                         for k, rs in rows.items()}
    return report, errors


def summary_lines(report):
    """One console line per kind, then the task ids that have neither card nor note."""
    lines = []
    for kind in KINDS:
        s = report["summary"][kind]
        lines.append(f"   coverage {kind:9s} {s['green']} green / {s['yellow']} yellow / {s['red']} red of {s['total']}")
    red = [t["id"] for d in report["domains"] for t in d["tasks"] if t["status"] == "red"]
    if red:
        lines.append("   tasks without card or note: " + ", ".join(red))
    return lines
