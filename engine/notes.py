"""Notes: frontmatter, Markdown -> HTML, and the note list for the Notes tab.

Markdown is rendered at build time with python-markdown. A ```mermaid block is
kept verbatim as <pre class="mermaid"> and drawn by mermaid.js in the browser.
Frontmatter is the minimal YAML subset the vault uses: `key: value` lines,
where a value in [brackets] is a list of strings.
"""
import html
import pathlib
import re

try:
    import markdown
except ImportError:  # reported by render(), so --help and validation still work
    markdown = None

FRONT_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
MERMAID_RE = re.compile(r"```mermaid[^\n]*\n(.*?)```", re.S)
WIKILINK_ALIAS_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
MARKER = "EXAMKITMERMAID{}END"


def _unquote(s):
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" else s


def _value(raw):
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_unquote(x.strip()) for x in inner.split(",")] if inner else []
    return _unquote(raw)


def split_frontmatter(text):
    """Return (meta, body). meta is {} when the text has no leading --- block."""
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = _value(value.strip())
    return meta, text[m.end():]


def note_covers(meta):
    """`covers` as a list of strings; [] when absent or empty; a scalar becomes one id."""
    c = meta.get("covers", [])
    if isinstance(c, str):
        return [c] if c else []
    return list(dict.fromkeys(str(x) for x in c if str(x)))


def _wikilink(m):
    target = m.group(1).split("/")[-1].split("#")[0]
    return f'<a href="#note-{html.escape(target)}">{html.escape(target)}</a>'


def render(body):
    """Markdown body -> HTML. Mermaid blocks survive untouched inside <pre class="mermaid">."""
    if markdown is None:
        raise SystemExit("python-markdown is missing: python3 -m pip install --user -r requirements.txt")
    blocks = []

    def keep(m):
        blocks.append(m.group(1))
        return f"\n\n{MARKER.format(len(blocks) - 1)}\n\n"

    text = MERMAID_RE.sub(keep, body)
    text = WIKILINK_ALIAS_RE.sub(r"\2", text)
    text = WIKILINK_RE.sub(_wikilink, text)
    out = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"]).convert(text)
    for i, code in enumerate(blocks):
        out = out.replace(f"<p>{MARKER.format(i)}</p>", f'<pre class="mermaid">{html.escape(code)}</pre>')
    return out


def _first_heading(body):
    for line in body.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None


def load_notes(notes_dir, exam):
    """Notes for the Notes tab, in configured order. Returns (groups, errors).

    exam["notes"] is an optional list of {"group": str, "items": [{"slug", "title"?, "subtitle"?}]}.
    Without it every *.md in notes_dir, sorted by name, forms one unnamed group.
    """
    notes_dir = pathlib.Path(notes_dir)
    spec = exam.get("notes")
    if spec is None:
        spec = [{"group": "", "items": [{"slug": p.stem} for p in sorted(notes_dir.glob("*.md"))]}]
    if not isinstance(spec, list):
        return [], ["exam.notes: must be a list of groups"]
    groups, errors = [], []
    for g in spec:
        if not isinstance(g, dict):
            errors.append("exam.notes: every group must be an object with items")
            continue
        items = []
        for it in g.get("items") or []:
            slug = it.get("slug") if isinstance(it, dict) else None
            if not isinstance(slug, str) or not slug:
                errors.append("exam.notes: every item needs a string slug")
                continue
            f = notes_dir / f"{slug}.md"
            if not f.exists():
                errors.append(f"exam.notes: {f} does not exist")
                continue
            meta, body = split_frontmatter(f.read_text(encoding="utf-8"))
            title = it.get("title") or meta.get("title") or _first_heading(body) or slug
            items.append({"slug": slug, "title": str(title), "subtitle": str(it.get("subtitle") or ""),
                          "covers": note_covers(meta), "html": render(body)})
        groups.append({"group": str(g.get("group") or ""), "items": items})
    return groups, errors
