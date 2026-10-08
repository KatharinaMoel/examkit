#!/usr/bin/env python3
"""Print pack: one HTML page per note plus a complete one, then PDFs through headless Chrome.

Usage: python3 engine/print.py <exam_dir> [--html-only] [--budget-ms N]
Writes <exam_dir>/build/print/NN-<slug>.html and 00-complete.html, and next to each a .pdf
unless --html-only. Notes come from exam.json (notes_dir, notes) exactly as the Notes tab
shows them. Images a note references by a relative path are copied to build/print/assets/<slug>/<hash>-<name>.
After printing, every page with a Mermaid diagram is loaded once more and its rendered DOM must
show an <svg> per diagram; otherwise the run fails (mermaid.js missing or broken).
Diagnostics go to stderr, the output directory to stdout. Exit 1 on errors.
"""
import argparse
import datetime
import hashlib
import html as html_mod
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from engine import chrome as chrome_mod  # noqa: E402
from engine import notes as notes_mod  # noqa: E402

MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
XREF_RE = re.compile(r'<a href="#note-[^"]*">(.*?)</a>', re.S)
LEAD_H1_RE = re.compile(r"\A\s*<h1[^>]*>(.*?)</h1>\s*", re.S)
IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]*)(")', re.I)
URL_SCHEME_RE = re.compile(r"\A[a-zA-Z][a-zA-Z0-9+.-]*:")
MERMAID_BLOCK_RE = re.compile(r'<pre\b[^>]*\bclass="[^"]*\bmermaid\b[^"]*"[^>]*>(.*?)</pre>', re.S)

CSS = """
.warn { color: #8a1c2c; border: 1pt solid #8a1c2c; padding: 3pt 6pt; font-size: 9pt; }
@page { size: A4; margin: 13mm 12mm 14mm; }
* { box-sizing: border-box; }
body { font-family: "IBM Plex Sans", "Segoe UI", Arial, sans-serif; font-size: 9.6pt; line-height: 1.38; color: #111; margin: 0; }
.part { break-before: page; }
.part:first-of-type { break-before: auto; }
.partmeta { font-size: 8pt; color: #555; margin: 0 0 2pt; }
.part h1 { font-size: 16pt; margin: 0 0 6pt; padding-bottom: 3pt; border-bottom: 2px solid #0e6e78; color: #0e6e78; }
.partsub { font-size: 10pt; color: #444; margin: 0 0 8pt; }
.notebody h1 { font-size: 13pt; margin: 10pt 0 4pt; }
h2 { font-size: 11.5pt; margin: 9pt 0 3pt; color: #0a545c; break-after: avoid; }
h3 { font-size: 10.2pt; margin: 7pt 0 2pt; break-after: avoid; }
p { margin: 0 0 4pt; } ul, ol { margin: 0 0 4pt; padding-left: 15pt; } li { margin-bottom: 1pt; }
table { border-collapse: collapse; width: 100%; margin: 2pt 0 6pt; break-inside: avoid; font-size: 8.8pt; }
th, td { border: 0.6pt solid #b9c3cc; padding: 2pt 4pt; vertical-align: top; text-align: left; }
th { background: #e6eff1; }
blockquote { margin: 3pt 0 6pt; padding: 3pt 7pt; border-left: 2.5pt solid #0e6e78; background: #f1f6f7; break-inside: avoid; }
blockquote p { margin: 0 0 2pt; }
code { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 8.6pt; }
pre:not(.mermaid) { background: #f4f4f4; padding: 4pt; font-size: 8.4pt; white-space: pre-wrap; }
pre.mermaid { text-align: center; margin: 3pt 0 7pt; break-inside: avoid; background: none; }
pre.mermaid svg { max-width: 100%; max-height: 118mm; height: auto; }
hr { border: 0; border-top: 0.6pt solid #ccc; }
.xref { font-style: italic; }
.stamp { font-size: 7.5pt; color: #666; margin-top: 10pt; }
"""

MERMAID_JS = """<script src="%s"></script>
<script>
(function(){
  function warn(msg){ var p = document.createElement('p'); p.className = 'warn'; p.textContent = msg; document.body.insertBefore(p, document.body.firstChild); document.documentElement.dataset.mermaid = 'failed'; }
  if (typeof mermaid === 'undefined') { warn('Diagrams not rendered: mermaid.js did not load (no network?). The diagram source is printed instead.'); return; }
  mermaid.initialize({startOnLoad:false, theme:'neutral', securityLevel:'strict'});
  mermaid.run({querySelector:'pre.mermaid'}).then(function(){ document.documentElement.dataset.mermaid = 'done'; })
    .catch(function(e){ warn('Diagrams not rendered: ' + e); });
})();
</script>
""" % MERMAID_URL


def say(msg):
    print(msg, file=sys.stderr)


def parts(exam, groups):
    """Flat, numbered list of notes in Notes-tab order: {n, slug, title, subtitle, group, html}."""
    out = []
    for g in groups:
        for it in g["items"]:
            body = XREF_RE.sub(r'<span class="xref">\1</span>', it["html"])
            m = LEAD_H1_RE.match(body)
            # Notes start with "# Title"; the section header already shows it, so drop the duplicate.
            if m and html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() == it["title"].strip():
                body = body[m.end():]
            out.append({"n": len(out) + 1, "slug": it["slug"], "title": it["title"], "subtitle": it["subtitle"],
                        "group": g["group"], "html": body})
    return out


def _section(exam, p):
    e = html_mod.escape
    meta = " · ".join(x for x in (exam["title"], exam.get("exam_code") or "", p["group"]) if x)
    sub = f'<p class="partsub">{e(p["subtitle"])}</p>' if p["subtitle"] else ""
    return (f'<section class="part"><header><p class="partmeta">{e(meta)}</p><h1>{e(p["title"])}</h1>{sub}</header>'
            f'<div class="notebody">{p["html"]}</div></section>\n')


def page(exam, selected, stamp):
    """Complete HTML document for the given parts; the Mermaid script only when a diagram is present."""
    e = html_mod.escape
    body = "".join(_section(exam, p) for p in selected)
    title = exam["title"] if len(selected) != 1 else f'{selected[0]["title"]} · {exam["title"]}'
    mermaid = MERMAID_JS if MERMAID_BLOCK_RE.search(body) else ""
    return (f'<!doctype html>\n<html><head><meta charset="utf-8"><title>{e(title)}</title><style>{CSS}</style></head>\n'
            f'<body data-generated="{e(stamp)}">\n{body}<p class="stamp">examkit · {e(exam["title"])} · {e(stamp)}</p>\n{mermaid}</body></html>\n')


def localize_images(p, notes_dir, out):
    """Copy images the note references by a relative path to out/assets/<slug>/ and point src there.

    Paths are relative to the note file and must stay inside notes_dir. URLs with a scheme
    (https:, data:, file:), absolute paths and fragments stay as they are. Returns warning lines.
    """
    root = pathlib.Path(notes_dir).resolve()
    note_dir = (root / p["slug"]).parent
    warnings = []

    def swap(m):
        src = html_mod.unescape(m.group(2))
        if not src or URL_SCHEME_RE.match(src) or src.startswith(("/", "#")):
            return m.group(0)
        rel = urllib.parse.unquote(urllib.parse.urlsplit(src).path)
        target = (note_dir / rel).resolve()
        if not target.is_relative_to(root):
            warnings.append(f"   warning: note {p['slug']}: image {src} points outside the notes directory, not copied")
            return m.group(0)
        if not target.is_file():
            warnings.append(f"   warning: note {p['slug']}: image {src} not found ({target})")
            return m.group(0)
        # The hash of the resolved source keeps two different files apart even when slug and path line up.
        name = f"{hashlib.sha1(str(target).encode()).hexdigest()[:10]}-{target.name}"
        dest = out / "assets" / p["slug"] / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, dest)
        new = urllib.parse.quote(f"assets/{p['slug']}/{name}", safe="/")
        return m.group(1) + html_mod.escape(new) + m.group(3)

    p["html"] = IMG_SRC_RE.sub(swap, p["html"])
    return warnings


def write_html(exam_dir, exam, groups, stamp, notes_dir=None):
    """Writes build/print/NN-<slug>.html per note and 00-complete.html.

    Returns [(path, label)] in that order; label is the note slug or "complete pack".
    With notes_dir, relative images are copied into build/print/assets/ (see localize_images).
    """
    out = exam_dir / "build" / "print"
    out.mkdir(parents=True, exist_ok=True)
    # Clear pages, PDFs and copied images of a previous run, and the Chrome profile older versions kept here.
    for old in [*out.glob("*.html"), *out.glob("*.pdf")]:
        if old.is_file():
            old.unlink()
    for old in (out / "assets", out / ".chrome-profile"):
        shutil.rmtree(old, ignore_errors=True)
    ps = parts(exam, groups)
    if notes_dir is not None:
        for p in ps:
            for w in localize_images(p, notes_dir, out):
                say(w)
    written = []
    for p in ps:
        # Subfolder slugs ("sub/note") become flat names; the NN prefix keeps them unique.
        f = out / f'{p["n"]:02d}-{p["slug"].replace("/", "-")}.html'
        f.write_text(page(exam, [p], stamp), encoding="utf-8")
        written.append((f, p["slug"]))
    f = out / "00-complete.html"
    f.write_text(page(exam, ps, stamp), encoding="utf-8")
    written.append((f, "complete pack"))
    return written


def unrendered_diagrams(dom):
    """(blocks without <svg>, all blocks) for the <pre class="mermaid"> elements of a dumped DOM."""
    blocks = MERMAID_BLOCK_RE.findall(dom)
    return sum("<svg" not in b for b in blocks), len(blocks)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exam_dir", type=pathlib.Path)
    ap.add_argument("--html-only", action="store_true", help="write the HTML pages, skip Chrome and the PDFs")
    ap.add_argument("--budget-ms", type=int, default=15000, help="page time Chrome grants scripts (Mermaid) before printing")
    a = ap.parse_args()
    ex = a.exam_dir.resolve()

    say(f"1. read config        exam.json and notes from {ex}")
    exam = json.loads((ex / "exam.json").read_text(encoding="utf-8"))
    notes_dir = pathlib.Path(exam.get("notes_dir") or "notes").expanduser()
    if not notes_dir.is_absolute():
        notes_dir = ex / notes_dir
    groups, errors = notes_mod.load_notes(notes_dir, exam)
    if errors:
        say("\n".join(errors))
        say(f"{len(errors)} error(s). Nothing written.")
        sys.exit(1)
    n = sum(len(g["items"]) for g in groups)
    stamp = datetime.date.today().isoformat()

    say(f"2. render html        {n} notes -> one page each plus 00-complete, stamped {stamp}")
    written = write_html(ex, exam, groups, stamp, notes_dir)
    out = written[0][0].parent
    if a.html_only:
        say("3. --html-only: done, no PDFs, no diagram check")
        print(out)
        return
    with_mermaid = [(f, label) for f, label in written if MERMAID_BLOCK_RE.search(f.read_text(encoding="utf-8"))]
    # One Chrome profile per run, in a temporary directory that is removed afterwards, also on errors.
    with chrome_mod.temporary_profile() as profile:
        try:
            say(f"3. print pdf          {len(written)} pages through headless Chrome, {a.budget_ms} ms page time each")
            for f, _ in written:
                pdf = f.with_suffix(".pdf")
                say(f"   {f.name} -> {pdf.name}")
                chrome_mod.print_pdf(f, pdf, profile, budget_ms=a.budget_ms)
            say(f"   ok: {len(written)} pdf files in {out}")
            say(f"4. check diagrams     {len(with_mermaid)} pages with Mermaid: the rendered DOM must show an <svg> per diagram")
            failed = []
            for f, label in with_mermaid:
                missing, total = unrendered_diagrams(chrome_mod.dump_dom(f, profile, budget_ms=a.budget_ms, timeout=180))
                say(f"   {f.name}: {total - missing} of {total} diagrams rendered")
                if missing or not total:
                    failed.append(f"error: diagrams not rendered in {f.name} (note {label}): {missing} of {total} "
                                  "Mermaid blocks without <svg> (mermaid.js did not load or failed)")
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            say(str(e))
            say("The HTML pages are written; print them by hand or set EXAMKIT_CHROME to a working Chrome.")
            sys.exit(1)
    if failed:
        say("\n".join(failed))
        say(f"{len(failed)} page(s) with unrendered diagrams. The PDFs are written but show diagram source instead of drawings.")
        sys.exit(1)
    print(out)


if __name__ == "__main__":
    main()
