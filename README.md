# examkit

Build a flashcard trainer, a notes reader and a printable study pack for any
exam from plain JSON cards and Markdown notes. Opinionated, built for my own
certification prep (AWS), shared in case it is useful.

## Principles

- **Engine/content split**: the engine is generic and public; exam content and
  sources live in `exams/<id>/`, which never enters this repository.
- **Every card is sourced**: `build.py` refuses a card whose `src` does not
  resolve to a guide item, a note heading or a source file.
- **Model knowledge is visible**: cards that rest on an LLM's memory are
  marked as such, on the card and in the build summary.
- **Explain-then-run**: the build prints each step with a one-line explanation.

## Quickstart

    python3 -m pip install --user -r requirements.txt   # python-markdown
    python3 engine/build.py example            # builds example/build/index.html
    python3 engine/build.py example --check    # validate only
    python3 -m pytest -q

## Status

Session 1 (2026-10-07): validator, build, template with config placeholders.
Session 2a (2026-10-07): coverage tab (cards and notes per guide item, red/yellow/green),
notes tab (Markdown + Mermaid), UI language files `de`/`en`, hardening.
Planned: print pack, progress export/import, demo on GitHub Pages.
