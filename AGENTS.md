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
| `engine/chrome.py` | headless Chrome helper: `find_chrome`, `dump_dom`, `print_pdf` (Flatpak paths via `--filesystem`) |
| `engine/print.py` | `python3 engine/print.py <exam_dir> [--html-only]` → `build/print/NN-<slug>.html` and `.pdf` per note plus `00-complete.*`; PDF needs headless Chrome |
| `engine/check_tracked.py` | `git ls-files \| python3 engine/check_tracked.py` fails on tracked exam content, `sources/` (except `example/sources/`) or `build/` |
| `.github/workflows/demo.yml` | CI: tracked-path check, tests, build of `example/`; deploys it to GitHub Pages from `main` |
| `requirements.txt` | `markdown>=3.5` — the only dependency beyond the stdlib |
| `example/` | minimal exam used by the tests and the public demo |
| `tests/` | `python3 -m pytest -q` — must stay green; `tests/test_smoke.py` drives headless Chrome and is skipped when none is found |
| `exams/<id>/AGENTS.md` | per-exam hand-over (goal, deadline, state, publish URL) — read it when working on that exam |
| `docs/superpowers/` | spec and plans (local only, git-ignored); if absent, the README "Status" section is the summary |

## Current state (2026-10-07, end of Session 2b)

Done: validator, build CLI, config-driven template, example, README (Session 1); coverage tab,
notes tab (Markdown + Mermaid on demand), UI language files de/en, hardening (Session 2a);
progress export/import (JSON file, newer grade wins per card), `retired.json` for card ids
(`build.json` lists all `ids`), browser smoke test, print pack (`engine/print.py`), tracked-path check
and GitHub Actions workflow for the Pages demo (Session 2b). 108 tests. Repo `KatharinaMoel/examkit`,
demo live at <https://katharinamoel.github.io/examkit/> (first workflow run 2026-10-07 passed). Install:
`python3 -m pip install --user -r requirements.txt`.
First exam `exams/aws-clf-c02` is live as a private claude.ai artifact (coverage + notes tabs).
The workflow uses checkout@v7, setup-python@v7, upload-pages-artifact@v5, deploy-pages@v5 (checked on
the GitHub release pages on 2026-10-07; keep the last two on matching majors). Enable Pages once with
source "GitHub Actions". Whether `ubuntu-latest` has Chrome shows in the first run's `-rs` output.

Decisions worth knowing: coverage counts explicit markers only (card `covers`, note frontmatter
`covers`), never text search; the storage protocol (storage key, localStorage suffixes, DB documents
`fortschritt/*`, collection `feedback`, grading tokens `richtig|teilweise|falsch`) is frozen because
a learner's progress hangs on it; the old lookup tab was removed, not generalised (no consumer).
Chrome's console log printed nothing for page errors in the Flatpak build tested on 2026-10-07, so the
smoke test uses an in-page error listener (see the docstring in `engine/chrome.py`).

Next:
1. AIF-C01 exam migrated into examkit as the second exam (after the CLF exam).
2. Decide whether to publish the static CLF page (after the exam).
3. First real feeding run for the CLF exam through the generic runbook (`~/ki-os/40-runbooks/kursmaterial-gegen-wissensbasis-abgleichen.md`, vault guide `~/ki-os/20-knowledge/anleitungen/lernkasten-fuettern.md`, both written 2026-10-07, runbook stays `entwurf` until that run). Service coverage goes into a separate services note (decided for the CLF exam, see `exams/aws-clf-c02/AGENTS.md`).
4. Leftovers: relative images in notes reach the print pack but not the Notes tab of the built page; the smoke harness runs `flatpak info` at collection time (skipif), reads only single-word lowercase probe keys, and a raw `>` in a probe attribute could cut the probe tag on older Chromium; after the source-tiers merge the build.py step-2 text should mention card-ids.json.

Before starting any of this: run the tests, then `python3 engine/build.py example`.
