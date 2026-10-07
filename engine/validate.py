"""Card validation: structure, allowed values, and resolvable sources.

A card is accepted only if its ``src`` resolves to one of
  guide:<id>              an id in coverage.json (task, svc:, concept:)
  note:<slug>#<heading>   <notes_dir>/<slug>.md contains a heading line "#... <heading>"
  source:<path>           <sources_dir>/<path> exists
"""
import json
import pathlib
import re

REQUIRED = ("id", "deck", "q", "a", "key", "src", "p", "ctx", "ctx_src")
CTX_SRC = {"note", "source", "guide", "model"}
SRC_RE = re.compile(r"^(guide|note|source):(.+)$")


def load_cards(cards_dir: pathlib.Path) -> list[dict]:
    """Load all cards; every returned entry is a dict carrying ``_file``.

    A non-object entry (or a file whose top level is not a list) is wrapped as
    ``{"_raw": <value>, "_file": <name>}`` so that ``validate`` can report it
    instead of crashing.
    """
    cards = []
    for f in sorted(pathlib.Path(cards_dir).glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for c in data if isinstance(data, list) else [data]:
            if isinstance(c, dict):
                c["_file"] = f.name
            else:
                c = {"_raw": c, "_file": f.name}
            cards.append(c)
    return cards


def coverage_ids(coverage: dict) -> set[str]:
    ids = {t["id"] for d in coverage.get("domains", []) for t in d.get("tasks", [])}
    ids |= {s["id"] for s in coverage.get("services", [])}
    ids |= {c["id"] for c in coverage.get("concepts", [])}
    return ids


def _heading_in(note: pathlib.Path, heading: str) -> bool:
    want = heading.strip()
    for line in note.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") and line.lstrip("#").strip() == want:
            return True
    return False


def resolve_src(src, cov_ids, notes_dir, sources_dir):
    m = SRC_RE.match(str(src))
    if not m:
        return f"src '{src}' must be guide:<id>, note:<slug>#<heading> or source:<path>"
    kind, rest = m.groups()
    if kind == "guide":
        return None if rest in cov_ids else f"src guide:{rest} is not an id in coverage.json"
    if kind == "note":
        if "#" not in rest:
            return f"src note:{rest} needs '#<heading>'"
        slug, heading = rest.split("#", 1)
        note = pathlib.Path(notes_dir) / f"{slug}.md"
        if not note.exists():
            return f"src note: file {note} does not exist"
        if not _heading_in(note, heading):
            return f"src note: {note.name} has no heading '{heading}'"
        return None
    path = pathlib.Path(sources_dir) / rest
    return None if path.exists() else f"src source: file {rest} not found under {sources_dir}"


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def validate(cards, exam, coverage, notes_dir, sources_dir) -> list[str]:
    errors = []
    if not cards:
        return ["no cards found"]
    cov_ids = coverage_ids(coverage)
    decks = set(exam.get("decks") or {})
    langs = set(exam.get("languages") or [])
    seen = {}
    for n, c in enumerate(cards, 1):
        if not isinstance(c, dict):
            errors.append(f"card #{n} in ? is not an object")
            continue
        where = c.get("_file", "?")
        if "_raw" in c:
            errors.append(f"card #{n} in {where} is not an object")
            continue
        cid = c.get("id") if isinstance(c.get("id"), str) else "?"
        label = f"{cid} ({where})"
        for f in REQUIRED:
            if f not in c or c[f] in ("", None, []):
                errors.append(f"{label}: field {f} missing")
        if "id" in c and not isinstance(c["id"], str):
            errors.append(f"{label}: id must be a string (card #{n})")
        elif cid in seen:
            errors.append(f"{label}: duplicate id ({seen[cid]} and {where})")
        if cid != "?":
            seen.setdefault(cid, where)
        deck = c.get("deck")
        if not isinstance(deck, str) or deck not in decks:
            errors.append(f"{label}: deck '{deck}' not in exam.decks")
        p = c.get("p")
        if type(p) is not int or p not in (1, 2, 3):
            errors.append(f"{label}: p must be 1, 2 or 3")
        ctx_src = c.get("ctx_src")
        if not isinstance(ctx_src, str) or ctx_src not in CTX_SRC:
            errors.append(f"{label}: ctx_src '{ctx_src}' not in {sorted(CTX_SRC)}")
        if "lang" in c and (not isinstance(c["lang"], str) or c["lang"] not in langs):
            errors.append(f"{label}: lang '{c['lang']}' not in exam.languages {sorted(langs)}")
        if "key" in c and c["key"] not in ("", None, []) and not _is_str_list(c["key"]):
            errors.append(f"{label}: key must be a list of strings")
        for f in ("unsure", "conflict"):
            if f in c and (not isinstance(c[f], str) or not c[f].strip()):
                errors.append(f"{label}: {f} must be a non-empty string")
        if "covers" in c:
            if not _is_str_list(c["covers"]):
                errors.append(f"{label}: covers must be a list of ids")
            else:
                for cv in c["covers"]:
                    if cv not in cov_ids:
                        errors.append(f"{label}: covers '{cv}' is not an id in coverage.json")
        if "src" in c:
            if not isinstance(c["src"], str):
                errors.append(f"{label}: src '{c['src']}' must be guide:<id>, note:<slug>#<heading> or source:<path>")
            else:
                msg = resolve_src(c["src"], cov_ids, notes_dir, sources_dir)
                if msg:
                    errors.append(f"{label}: {msg}")
    return errors
