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
