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
  content may be in any language the exam config allows; the page UI is German
  until the UI language file exists.

## Where things are

| Path | What |
|---|---|
| `engine/validate.py` | card validation (fields, decks, priorities, languages, covers, resolvable src) |
| `engine/build.py` | `python3 engine/build.py <exam_dir> [--check]` → `<exam_dir>/build/index.html` + `build.json` |
| `engine/template/index.html` | the flashcard page; placeholders `/*TITLE*/ /*CONFIG*/ /*KARTEN*/ /*PLAN*/ /*LOOKUP*/ /*BUILD*/` |
| `example/` | minimal exam used by the tests and (later) the public demo |
| `tests/` | `python3 -m pytest -q` — must stay green |
| `exams/<id>/AGENTS.md` | per-exam hand-over (goal, deadline, state, publish URL) — read it when working on that exam |
| `docs/superpowers/` | spec and plans (local only, git-ignored); if absent, the README "Status" section is the summary |

## Current state (2026-10-07, end of Session 1)

Done: validator, build CLI, config-driven template, example, 32 tests, README.
First exam `exams/aws-clf-c02` is live as a private claude.ai artifact.

Next (Session 2, in this order; details in `docs/superpowers/specs/2026-10-07-examkit-design.md` when present):
1. Coverage tab: count cards (`covers`) and notes (`covers:` frontmatter) per guide item; red/yellow/green.
2. Notes tab in the same page (Markdown + Mermaid from `notes_dir`), replacing the separate "Lernkompass"; set `compass_url` only if a separate reader exists.
3. Print pack (HTML → PDF via headless Chromium, no pandoc).
4. UI language files `engine/template/ui.de.json`, `ui.en.json`; remove AIF-specific leftovers (NOTIZ map, old deck labels, `window.aifShow`, German placeholder names such as `KARTEN`).
5. Progress export/import button; `retired.json` for card ids; smoke test in headless Chromium.
6. Demo build of `example/` for GitHub Pages; add `<!doctype html>` and viewport meta for that target.
7. Hardening noted in review: exam.json keys present but `null` should produce an error list, not a traceback; `unsure`/`conflict` must be strings; TTS language from config.

Before starting any of this: run the tests, then `python3 engine/build.py example`.
