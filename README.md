# examkit

Build a flashcard trainer, a notes reader and a printable study pack for any
exam from plain JSON cards and Markdown notes. Opinionated, built for my own
certification prep (AWS), shared in case it is useful.

## Principles

- **Engine/content split**: the engine is generic and public; exam content and
  sources live in `exams/<id>/`, which never enters this repository.
- **Every card is sourced**: `build.py` refuses a card whose `src` does not
  resolve to a guide item, a note heading or a source file; source folders
  can carry trust tiers (see Source tiers below).
- **Model knowledge is visible**: cards that rest on an LLM's memory are
  marked as such, on the card and in the build summary.
- **Explain-then-run**: the build prints each step with a one-line explanation.

## Quickstart

    python3 -m pip install --user -r requirements.txt   # python-markdown
    python3 engine/build.py example            # builds example/build/index.html
    python3 engine/build.py example --check    # validate only
    python3 engine/print.py example            # notes as PDF: example/build/print/ (needs headless Chrome)
    python3 engine/print.py example --html-only
    python3 -m pytest -q

## Demo

**Try it: <https://katharinamoel.github.io/examkit/>**

The `example/` exam is built by GitHub Actions (`.github/workflows/demo.yml`) and published to this
repository's GitHub Pages site on every push to `main`. Progress there lives only in your browser.

## Source tiers

`exam.json` may map each first-level folder of `sources/` to a trust tier:

    "source_tiers": {"exam-guide": "primary", "classroom": "official", "podcasts": "hypothesis"}

Once the key is set, a `source:<path>` src must live in a listed folder (`sources/<folder>/<file>`, no
`./`, `../` or absolute paths), and only `primary` and `official` folders can back a card. A
`hypothesis` source (podcasts, third-party courses) is refused: cite a primary/official source and
mention the origin in `ctx`. Without the key, any existing file under `sources/` is accepted. With or
without the key, a `source:` must be a file (not a directory) given as a plain relative path: `./`, `../`,
absolute paths and symlinks that point outside `sources/` are always refused. The build
summary and `build.json` (`by_tier`) count cards per tier (`guide`, `note`, and `source` when no tiers
are set).

## Math

Formulas are opt-in per exam: set `"math": "mathjax"` in `exam.json` (any other value is a build
error). Without the key the page is built exactly as before.

- Delimiters: `$...$` and `\(...\)` inline, `$$...$$` and `\[...\]` display. An inline `$` must not
  touch whitespace on its inner side and the closing `$` must not be followed by a digit, so
  "costs $5 and $6" stays text; `\$` is a literal dollar.
- Rendering: MathJax 3.2.2 with SVG output, one script from cdnjs
  (`https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-svg.js`) and no stylesheet, so the
  page still loads scripts only from cdnjs and stylesheets only from Google Fonts. TeX extensions that
  MathJax autoloads come from the same cdnjs folder. Offline, the TeX source stays visible.
- Where: card front and back (question, answer, context, conflict, source), the AI verdict, the history,
  the Notes tab (navigation and text), the Coverage tab and the Plan tab. A changed region is typeset
  again after every re-render; a hidden tab is typeset when it is shown (`engine/template/math.html`).
- Notes: before Markdown runs, every formula outside code is swapped for a placeholder and put back
  afterwards, HTML-escaped and wrapped in `<span class="math">`, so `_`, `*`, `\\` and `|` (also in
  table cells) reach MathJax unchanged. Code spans and fenced blocks are never formulas.
- Print pack: pages with formulas load MathJax and typeset inside Chrome's page time
  (`--budget-ms`); afterwards every `<span class="math">` must hold MathJax output, otherwise the run
  names the note and exits 1 (like the Mermaid check).

## Origins

Optional: say where a card's content comes from (covered in the lecture, needed in an exercise, extra
reading), independent of its priority `p`. `exam.json` lists the allowed values in order, like `decks`:

    "origins": {"vl": "Vorlesung", "uebung": "Übung", "literatur": "Literatur", "voraussetzung": "Voraussetzung"}

A card may then carry `origin` (one of these keys) and `origin_detail` (short free text):

    {"id": "...", "origin": "uebung", "origin_detail": "hw01 1.1", ...}

- Validation: keys are lowercase letters, digits, `-` or `_`; labels are non-empty strings. A card's
  `origin` must be a listed key, `origin_detail` a non-empty string next to an `origin`. A card with
  `origin` in an exam without `origins` is a build error.
- Build summary and `build.json`: cards per origin (`by_origin`, config order, non-zero only) and
  without origin (`no_origin`). The Coverage tab shows the per-origin card counts inside each item.
- Page: the card front shows the label and `origin_detail` as a small badge; a chip row ("Any origin",
  one chip per used origin, "no origin" when some cards have none) filters the cards like the deck chips
  (single choice). The choice is kept locally as `ui.origin` next to `ui.deck` in the existing state;
  older states without it load as "Any origin", and the reset box names the active origin filter.
- Without `origins` the page is built exactly as before: the origin code (`engine/template/origin.html`
  and the `/*ORIGIN_...*/` hooks in the template) and the `origin_*` UI strings are left out.

## Progress file

"Save progress" writes a JSON file with every grade, the history and the plan ticks; "Load progress"
merges such a file into the current state (per card the newer grade wins). Card ids are permanent:
every real build records all ids ever built in `card-ids.json` next to `exam.json` (keep it with
the cards; `--check` never writes it), and `build.py` refuses a build when an id from that file or
from the previous `build.json` is gone unless `retired.json` names it with a reason. An id that was
never published (say a draft built once locally) may be removed from `card-ids.json` by hand; the
cost is that the retired check no longer knows that id, so it can come back with other content.

## Print pack

`engine/print.py` writes one HTML page and PDF per note plus `00-complete` into `build/print/`.
Images a note references by a relative path (inside the notes directory) are copied to
`build/print/assets/<slug>/` (file names carry a short hash of the source path); a missing or
outside image is a warning. After printing, every page with a Mermaid diagram is loaded again: if
a diagram has no rendered `<svg>` (mermaid.js did not load, e.g. offline), the run names the note
and exits 1. `--html-only` skips Chrome and this check.
Chrome runs with a temporary profile and is killed with all its processes on a timeout.

## Status

Session 1 (2026-10-07): validator, build, template with config placeholders.
Session 2a (2026-10-07): coverage tab (cards and notes per guide item, red/yellow/green),
notes tab (Markdown + Mermaid), UI language files `de`/`en`, hardening.
Session 2b (2026-10-07): progress export/import, retired.json, browser smoke test, print pack, GitHub Pages demo.
Math (2026-10-23): optional MathJax formulas (`exam.json` `math`), protected in notes, checked in the print pack.
Origins (2026-10-23): optional card origin (`exam.json` `origins`, card `origin`/`origin_detail`): badge, filter, counts.
