"""Card validation: structure, allowed values, and resolvable sources.

A card is accepted only if its ``src`` resolves to one of
  guide:<id>              an id in coverage.json (task, svc:, concept:)
  note:<slug>#<heading>   <notes_dir>/<slug>.md contains a heading line "#... <heading>"
  source:<path>           <sources_dir>/<path> is a file; a plain relative path
                          (no ./, ../ or absolute path) whose resolved target
                          (symlinks followed) stays inside sources/

Optional trust tiers (``exam.source_tiers``) map a first-level folder of
``sources/`` to primary, official or hypothesis. When they are set, a
``source:`` src must live in a listed folder whose tier is primary or
official; hypothesis-tier material (podcasts, third-party courses) can
never back a card.
"""
import json
import pathlib
import re

REQUIRED = ("id", "deck", "q", "a", "key", "src", "p", "ctx", "ctx_src")
CTX_SRC = {"note", "source", "guide", "model"}
SRC_RE = re.compile(r"^(guide|note|source):(.+)$")
TIERS = ("primary", "official", "hypothesis")
CARD_TIERS = {"primary", "official"}


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


def check_source_tiers(tiers) -> list[str]:
    """Schema check for exam.source_tiers (None means: not configured)."""
    if tiers is None:
        return []
    if not isinstance(tiers, dict):
        return ['exam.source_tiers: must be an object mapping a sources/ folder to '
                f'one of {", ".join(TIERS)}, e.g. {{"exam-guide": "primary"}}']
    errors = []
    for folder, tier in tiers.items():
        if not isinstance(folder, str) or folder.strip() in ("", ".", "..") or "/" in folder:
            errors.append(f"exam.source_tiers: folder '{folder}' must be a first-level folder name (not empty, '.' or '..', no '/')")
        if not isinstance(tier, str) or tier not in TIERS:
            errors.append(f"exam.source_tiers: tier '{tier}' for folder '{folder}' must be one of {', '.join(TIERS)}")
    return errors


def _escape_msg(src):
    return f"src '{src}' must be a plain relative path inside sources/ (no ./, ../ or absolute paths, which escape sources/)"


def _escape_error(src, rest):
    """A source:<rest> must be a plain relative path: no ./, ../ or absolute path. Error string or None."""
    parts = rest.split("/")
    if rest.startswith("/") or pathlib.PurePath(rest).is_absolute() or any(x in (".", "..") for x in parts):
        return _escape_msg(src)
    return None


def _tier_error(src, rest, tiers):
    """Tier check for an existing, non-escaping source:<rest>; returns an error string or None."""
    parts = rest.split("/")
    if "" in parts:
        return f"src '{src}' has an empty path segment (trailing '/' or '//'); name a file as sources/<folder>/<file>"
    if len(parts) < 2:
        return f"src '{src}': the file must live in a tier folder (sources/<folder>/<file>), not directly in sources/"
    folder = parts[0]
    if folder not in tiers:
        return f"src '{src}': folder '{folder}' has no tier; list it in exam.source_tiers"
    tier = tiers[folder]
    if tier == "hypothesis":
        return (f"src '{src}' is hypothesis-tier ({folder}) and cannot back a card; "
                "cite a primary/official source and mention the origin in ctx")
    if tier not in CARD_TIERS:
        return f"src '{src}': folder '{folder}' has invalid tier '{tier}'"
    return None


def _effective_tiers(tiers):
    """Tiers the card check uses: None (not configured), the object, or {} for a broken config (fail closed)."""
    if tiers is not None and not isinstance(tiers, dict):
        return {}  # a broken tier config accepts no source: card
    return tiers


def source_tier(src, tiers) -> str:
    """Bucket for the build summary: guide, note, the tier of a source: path, or source without tiers."""
    m = SRC_RE.match(str(src))
    if not m:
        return "?"
    kind, rest = m.groups()
    if kind != "source" or tiers is None:
        return kind
    return tiers.get(rest.split("/", 1)[0], "?") if isinstance(tiers, dict) else "?"


def resolve_src(src, cov_ids, notes_dir, sources_dir, *, source_tiers=None):
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
    escape = _escape_error(src, rest)
    if escape:
        return escape  # checked first: with or without tiers, a source: path never leaves sources/
    path = pathlib.Path(sources_dir) / rest
    if not path.exists():
        return f"src source: file {rest} not found under {sources_dir}"
    if not path.resolve().is_relative_to(pathlib.Path(sources_dir).resolve()):
        return _escape_msg(src)  # a symlink inside sources/ that points outside
    if source_tiers is not None:
        tier_error = _tier_error(src, rest, source_tiers)
        if tier_error:
            return tier_error  # more specific for a trailing '/' or a bare folder
    if not path.is_file():
        return f"src '{src}' is a directory, not a file"
    return None


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
    tiers = exam.get("source_tiers")
    errors += check_source_tiers(tiers)
    tiers = _effective_tiers(tiers)
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
                msg = resolve_src(c["src"], cov_ids, notes_dir, sources_dir, source_tiers=tiers)
                if msg:
                    errors.append(f"{label}: {msg}")
    return errors
