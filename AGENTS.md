# examkit — instructions for coding agents

Read this first; it replaces a hand-over. Project rules in short:

- **Engine/content split.** `engine/` is generic and public. Exam content lives in
  `exams/<id>/` (git-ignored, never committed) and in the owner's note vault.
- **Every card is sourced.** `engine/build.py` refuses a card whose `src` does not
  resolve (`guide:<id>` from coverage.json, `note:<slug>#<heading>`, `source:<path>`).
  Model knowledge is allowed only as `ctx_src: "model"` and is counted and shown.
- **No agent commits or pushes.** Explain the state, list files, propose a commit
  message; the owner commits. Never run git commands that change state.
- **Explain-then-run.** Scripts print each step with a one-line explanation.
- Code, file names, config keys, CLI text and docs are English. Card and note
  content may be in any language the exam config allows; the page UI comes from
  `engine/template/ui.<ui_language>.json` (`de`, `en`).

## Where things are

| Path | What |
|---|---|
| `engine/validate.py` | card validation (fields, decks, priorities, languages, covers, resolvable src) |
| `engine/build.py` | `python3 engine/build.py <exam_dir> [--check]` → `<exam_dir>/build/index.html` + `build.json`; prints a coverage summary |
| `engine/notes.py` | frontmatter, Markdown → HTML (python-markdown), Mermaid kept for the browser, note list from `exam.json.notes` |
| `engine/coverage.py` | cards (`covers`) and notes (frontmatter `covers`) per guide item; green/yellow/red |
| `engine/template/index.html` | the flashcard page (tabs Cards, Coverage, Notes, Plan); placeholders `/*TITLE*/ /*CONFIG*/ /*UI*/ /*CARDS*/ /*PLAN*/ /*BUILD*/ /*COVERAGE*/ /*NOTES*/` |
| `engine/template/ui.de.json`, `ui.en.json` | every UI string; `exam.json.ui_language` picks one; `tests/test_ui.py` enforces that the template uses exactly these keys |
| `requirements.txt` | `markdown>=3.5` — the only dependency beyond the stdlib |
| `example/` | minimal exam used by the tests and (later) the public demo |
| `tests/` | `python3 -m pytest -q` — must stay green |
| `exams/<id>/AGENTS.md` | per-exam hand-over (goal, deadline, state, publish URL) — read it when working on that exam |
| `docs/superpowers/` | spec and plans (local only, git-ignored); if absent, the README "Status" section is the summary |

## Current state (2026-10-07, end of Session 2a)

Done: validator, build CLI, config-driven template, example, README (Session 1); coverage tab,
notes tab (Markdown + Mermaid on demand), UI language files de/en, AIF leftovers removed,
hardening (`null` config keys → error list, `unsure`/`conflict` strings, card speech language
from `lang` + `exam.tts`). 70 tests. Install: `python3 -m pip install --user -r requirements.txt`.
First exam `exams/aws-clf-c02` is live as a private claude.ai artifact (coverage + notes tabs).

Decisions worth knowing: coverage counts explicit markers only (card `covers`, note frontmatter
`covers`), never text search; the storage protocol (storage key, localStorage suffixes, DB documents
`fortschritt/*`, collection `feedback`, grading tokens `richtig|teilweise|falsch`) is frozen because
a learner's progress hangs on it; the old lookup tab was removed, not generalised (no consumer).

Next (Session 2b, plan B; details in `docs/superpowers/specs/2026-10-07-examkit-design.md` when present):
1. Print pack (HTML → PDF via headless Chromium, no pandoc), one PDF per note plus a complete one.
2. Progress export/import button; `retired.json` for card ids (ids missing from the previous
   `build.json` must be listed there); smoke test in headless Chromium (page loads, DOM card count
   = JSON, no JS errors).
3. Demo build of `example/` on GitHub Pages via GitHub Actions (tests, forbidden-path check on
   `git ls-files`, build, deploy); add `<!doctype html>` and viewport meta for that target.
4. Small leftovers: German comments in the template; `.notes-nav` group labels stay visible when a
   search hides all their links; CRLF notes lose their frontmatter silently.

Before starting any of this: run the tests, then `python3 engine/build.py example`.
