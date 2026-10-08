import json, pathlib, re, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
EX = ROOT / "example"
BUILD_PY = ROOT / "engine" / "build.py"
TEMPLATE = ROOT / "engine" / "template" / "index.html"


def build(exam_dir, *args):
    return subprocess.run([sys.executable, str(BUILD_PY), str(exam_dir), *args],
                          capture_output=True, text=True)


def copy_example(tmp_path):
    dst = tmp_path / "ex"
    shutil.copytree(EX, dst, ignore=shutil.ignore_patterns("build"))
    return dst


def edit_cards(exam_dir, fn):
    f = exam_dir / "cards" / "basics.json"
    cards = json.loads(f.read_text(encoding="utf-8"))
    fn(cards)
    f.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")


def edit_exam(exam_dir, fn):
    f = exam_dir / "exam.json"
    exam = json.loads(f.read_text(encoding="utf-8"))
    fn(exam)
    f.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")


def embedded(html, script_id):
    m = re.search(rf'<script id="{script_id}" type="application/json">(.*?)</script>', html, re.S)
    assert m, script_id
    return json.loads(m.group(1))


def outputs(exam_dir):
    return [p for p in (exam_dir / "build" / "index.html", exam_dir / "build" / "build.json") if p.exists()]


def test_check_only_writes_nothing(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex, "--check")
    assert r.returncode == 0, r.stderr
    assert outputs(ex) == []


def test_build_embeds_cards_config_and_manifest(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    for ph in ("CONFIG", "CARDS", "PLAN", "BUILD", "COVERAGE", "NOTES", "UI"):
        assert f"/*{ph}*/" not in html
    cards = embedded(html, "cards")
    assert "ex-basic-def" in {c["id"] for c in cards}
    assert embedded(html, "config")["storage_key"] == "examkit-example-v1"
    m = json.loads((ex / "build" / "build.json").read_text())
    assert m["cards"] == 3 and m["model_cards"] == 1 and m["exam_id"] == "example"
    assert embedded(html, "build")["cards"] == 3


def test_model_marker_is_wired_for_model_cards(tmp_path):
    ex = copy_example(tmp_path)
    assert build(ex).returncode == 0
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert any(c["ctx_src"] == "model" for c in embedded(html, "cards"))
    assert "=== 'model'" in TEMPLATE.read_text(encoding="utf-8")


def test_hostile_card_text_round_trips(tmp_path):
    ex = copy_example(tmp_path)
    nasty = "Close </script> open <!-- and /*PLAN*/ /*CONFIG*/ end"
    edit_cards(ex, lambda cs: cs[0].update(q=nasty))
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    cards = embedded(html, "cards")
    assert nasty in {c["q"] for c in cards}
    assert "<!--" not in html and html.count("</script>") == html.count("<script")
    assert embedded(html, "plan") == {"stand": "", "links_alle": None, "tage": []}
    assert embedded(html, "config")["id"] == "example"


def test_build_is_deterministic_except_timestamp(tmp_path):
    ex = copy_example(tmp_path)
    blank = lambda s: re.sub(r'"built_at": ?"[^"]*"', '"built_at": ""', s)
    build(ex); a = (ex / "build" / "index.html").read_text(encoding="utf-8")
    build(ex); b = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert '"built_at": ""' in blank(a)
    assert blank(a) == blank(b)


def test_build_fails_on_invalid_card(tmp_path):
    ex = copy_example(tmp_path)
    edit_cards(ex, lambda cs: cs[0].update(src="guide:9.9"))
    r = build(ex)
    assert r.returncode == 1 and "guide:9.9" in r.stderr
    assert outputs(ex) == []


def test_build_lists_all_card_errors(tmp_path):
    ex = copy_example(tmp_path)
    def two_bad(cs):
        cs[0]["src"] = "guide:9.9"
        cs[1]["src"] = "guide:8.8"
    edit_cards(ex, two_bad)
    r = build(ex)
    assert r.returncode == 1
    assert "guide:9.9" in r.stderr and "guide:8.8" in r.stderr
    assert outputs(ex) == []


def test_exam_schema_errors_are_listed_with_card_errors(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: (e.pop("grading_prompt"), e.pop("storage_key")))
    edit_cards(ex, lambda cs: cs[0].update(src="guide:9.9"))
    r = build(ex)
    assert r.returncode == 1
    assert "exam.grading_prompt" in r.stderr and "exam.storage_key" in r.stderr and "guide:9.9" in r.stderr
    assert outputs(ex) == []


def test_reserved_deck_key_alle_is_rejected(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e["decks"].update(alle="Everything"))
    r = build(ex, "--check")
    assert r.returncode == 1 and "exam.decks: key 'alle' is reserved" in r.stderr


def test_empty_decks_rejected(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e.update(decks={}, languages="en"))
    r = build(ex, "--check")
    assert r.returncode == 1 and "exam.decks" in r.stderr and "exam.languages" in r.stderr


def test_example_build_in_place():
    r = build(EX)
    assert r.returncode == 0, r.stderr
    assert (EX / "build" / "index.html").exists() and (EX / "build" / "build.json").exists()


def test_build_embeds_coverage_and_notes(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    cov = embedded(html, "coverage")
    assert cov["summary"]["tasks"] == {"total": 1, "green": 1, "yellow": 0, "red": 0}
    assert cov["domains"][0]["tasks"][0]["notes"] == ["intro"]
    notes = embedded(html, "notes")
    assert notes[0]["group"] == "Reading" and notes[0]["items"][0]["slug"] == "intro"
    assert 'class="mermaid"' in notes[0]["items"][0]["html"]
    m = json.loads((ex / "build" / "build.json").read_text())
    assert m["coverage"]["services"]["yellow"] == 1
    assert "coverage tasks" in r.stderr


def test_check_prints_coverage_summary(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex, "--check")
    assert r.returncode == 0 and "coverage tasks" in r.stderr and outputs(ex) == []


def test_step_two_names_the_id_ledger_on_one_line(tmp_path):
    r = build(copy_example(tmp_path), "--check")
    step2 = [line for line in (r.stdout + r.stderr).splitlines() if line.startswith("2. validate")]
    assert len(step2) == 1 and "ids against card-ids.json, the previous build and retired.json" in step2[0], step2


def test_note_covers_unknown_id_fails_build(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "notes" / "extra.md").write_text("---\ncovers: [9.9]\n---\n# Extra\n", encoding="utf-8")
    r = build(ex)
    assert r.returncode == 1 and "extra.md" in r.stderr and "9.9" in r.stderr
    assert outputs(ex) == []


def test_missing_note_in_config_fails_build(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e["notes"][0]["items"].append({"slug": "ghost"}))
    r = build(ex)
    assert r.returncode == 1 and "ghost.md" in r.stderr and outputs(ex) == []


def test_hostile_note_round_trips(tmp_path):
    ex = copy_example(tmp_path)
    nasty = "Close </script> open <!-- and `/*CARDS*/` end"
    f = ex / "notes" / "intro.md"
    f.write_text(f.read_text(encoding="utf-8") + f"\n\n## Nasty\n\n{nasty}\n", encoding="utf-8")
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert "<!--" not in html and html.count("</script>") == html.count("<script")
    assert "/*CARDS*/" in embedded(html, "notes")[0]["items"][0]["html"]


def test_template_has_four_tabs_and_no_lookup():
    t = TEMPLATE.read_text(encoding="utf-8")
    for tab in ("cards", "coverage", "notes", "plan"):
        assert f'id="tab-{tab}"' in t and f'id="view-{tab}"' in t
    for gone in ("/*LOOKUP*/", 'id="lookup"', "aifShow", "servicesIn", "tab-dienste", "view-karten"):
        assert gone not in t
    assert "examkitShow" in t


def test_template_links_cards_to_notes():
    t = TEMPLATE.read_text(encoding="utf-8")
    assert "examkitNote" in t and "cdn.jsdelivr.net/npm/mermaid@11" in t
    for gone in ("NOTIZ", "kompassLink", "KOMPASS", "compass_url", "Lernkompass"):
        assert gone not in t


def test_ui_language_switches_strings(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e.update(ui_language="de"))
    r = build(ex)
    assert r.returncode == 0, r.stderr
    html = (ex / "build" / "index.html").read_text(encoding="utf-8")
    assert embedded(html, "ui")["tab_cards"] == "Karten" and "· Karteikasten</title>" in html


def test_unknown_ui_language_is_error(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e.update(ui_language="fr"))
    r = build(ex, "--check")
    assert r.returncode == 1 and "exam.ui_language" in r.stderr and "fr" in r.stderr
    assert "Traceback" not in r.stderr


def test_null_exam_keys_give_error_list(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e.update({k: None for k in list(e)}))
    r = build(ex, "--check")
    assert r.returncode == 1 and "Traceback" not in r.stderr
    for key in ("id", "title", "storage_key", "grading_prompt", "notes_dir", "ui_language", "decks", "languages"):
        assert f"exam.{key}" in r.stderr, key


def test_tts_must_be_object_of_strings(tmp_path):
    ex = copy_example(tmp_path)
    edit_exam(ex, lambda e: e.update(tts="de-DE"))
    r = build(ex, "--check")
    assert r.returncode == 1 and "exam.tts" in r.stderr


def test_template_reads_card_language_from_config():
    t = TEMPLATE.read_text(encoding="utf-8")
    assert "CONFIG.tts" in t and "cardLang(" in t
    for gone in ("'pruefung'", "Correct: ", "c.erst", "langOf("):
        assert gone not in t


def test_note_jump_strips_inline_markdown():
    t = TEMPLATE.read_text(encoding="utf-8")
    assert "const plain = s =>" in t and "plain(h.textContent)===want" in t


def drop_model_card(cs):
    cs[:] = [c for c in cs if c["id"] != "ex-model"]


def manifest(exam_dir):
    return json.loads((exam_dir / "build" / "build.json").read_text(encoding="utf-8"))


def test_manifest_lists_card_ids(tmp_path):
    ex = copy_example(tmp_path)
    assert build(ex).returncode == 0
    assert manifest(ex)["ids"] == ["ex-basic-def", "ex-model", "ex-svc-thing"]


def test_missing_id_without_retired_is_error(tmp_path):
    ex = copy_example(tmp_path)
    assert build(ex).returncode == 0
    edit_cards(ex, drop_model_card)
    r = build(ex)
    assert r.returncode == 1
    assert "ex-model" in r.stderr and "retired.json" in r.stderr and "Traceback" not in r.stderr
    assert manifest(ex)["ids"] == ["ex-basic-def", "ex-model", "ex-svc-thing"]   # old build untouched


def test_missing_id_listed_in_retired_passes(tmp_path):
    ex = copy_example(tmp_path)
    assert build(ex).returncode == 0
    edit_cards(ex, drop_model_card)
    (ex / "retired.json").write_text('{"ex-model": "folded into ex-basic-def on 2026-10-07"}', encoding="utf-8")
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert manifest(ex)["ids"] == ["ex-basic-def", "ex-svc-thing"]


def test_retired_id_still_live_is_error(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "retired.json").write_text('{"ex-basic-def": "typo"}', encoding="utf-8")
    r = build(ex)
    assert r.returncode == 1 and "ex-basic-def is listed as retired but a live card still uses it" in r.stderr
    assert outputs(ex) == []


def test_retired_bad_shape_is_error(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "retired.json").write_text('["ex-model"]', encoding="utf-8")
    r = build(ex)
    assert r.returncode == 1 and "retired.json" in r.stderr and "Traceback" not in r.stderr


def test_previous_manifest_without_ids_is_tolerated(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "build").mkdir()
    (ex / "build" / "build.json").write_text('{"cards": 3}', encoding="utf-8")
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert manifest(ex)["ids"] == ["ex-basic-def", "ex-model", "ex-svc-thing"]


def test_check_only_also_checks_retired(tmp_path):
    ex = copy_example(tmp_path)
    assert build(ex).returncode == 0
    edit_cards(ex, drop_model_card)
    r = build(ex, "--check")
    assert r.returncode == 1 and "ex-model" in r.stderr


# --- card-ids.json: the id ledger next to exam.json, so the retired-id check also works on a fresh clone ---
IDS = ["ex-basic-def", "ex-model", "ex-svc-thing"]


def ledger(exam_dir):
    return json.loads((exam_dir / "card-ids.json").read_text(encoding="utf-8"))


def fresh(tmp_path):
    """example/ copy without build/ and without card-ids.json: the state before any build."""
    ex = copy_example(tmp_path)
    (ex / "card-ids.json").unlink(missing_ok=True)
    return ex


def test_first_build_creates_the_id_ledger(tmp_path):
    ex = fresh(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert ledger(ex) == IDS
    assert (ex / "card-ids.json").read_text(encoding="utf-8").endswith("\n")


def test_check_never_writes_the_id_ledger(tmp_path):
    ex = fresh(tmp_path)
    assert build(ex, "--check").returncode == 0
    assert not (ex / "card-ids.json").exists()


def test_fresh_clone_with_ledger_catches_a_missing_id(tmp_path):
    ex = fresh(tmp_path)
    (ex / "card-ids.json").write_text(json.dumps(IDS), encoding="utf-8")
    edit_cards(ex, drop_model_card)
    assert not (ex / "build").exists()
    for args in ((), ("--check",)):
        r = build(ex, *args)
        assert r.returncode == 1, args
        assert "ex-model" in r.stderr and "retired.json" in r.stderr and "Traceback" not in r.stderr


def test_ledger_keeps_retired_ids(tmp_path):
    ex = fresh(tmp_path)
    assert build(ex).returncode == 0
    edit_cards(ex, drop_model_card)
    (ex / "retired.json").write_text('{"ex-model": "folded into ex-basic-def"}', encoding="utf-8")
    assert build(ex).returncode == 0
    assert ledger(ex) == IDS                     # every id ever built, retired ones included
    (ex / "retired.json").unlink()
    (ex / "build" / "build.json").unlink()       # only the ledger still knows ex-model
    r = build(ex)
    assert r.returncode == 1 and "ex-model" in r.stderr


def test_ledger_grows_with_new_cards(tmp_path):
    ex = fresh(tmp_path)
    assert build(ex).returncode == 0
    edit_cards(ex, lambda cs: cs.append(dict(cs[0], id="ex-new")))
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert ledger(ex) == sorted(IDS + ["ex-new"])


def test_ledger_takes_ids_of_the_previous_build_too(tmp_path):
    ex = fresh(tmp_path)
    (ex / "build").mkdir()
    (ex / "build" / "build.json").write_text(json.dumps({"ids": IDS + ["ex-old"]}), encoding="utf-8")
    (ex / "retired.json").write_text('{"ex-old": "removed before the ledger existed"}', encoding="utf-8")
    assert build(ex).returncode == 0
    assert ledger(ex) == sorted(IDS + ["ex-old"])


def test_non_string_ids_of_the_previous_build_are_ignored(tmp_path):
    ex = fresh(tmp_path)
    (ex / "build").mkdir()
    (ex / "build" / "build.json").write_text(json.dumps({"ids": IDS + [7, {"a": 1}]}), encoding="utf-8")
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr
    assert ledger(ex) == IDS


def test_malformed_ledger_is_error_with_repair_hint(tmp_path):
    for i, text in enumerate(("{not json", '{"ids": []}', "[1, 2]", '["ex-model", 5, null]')):
        ex = fresh(tmp_path / str(i))
        (ex / "card-ids.json").write_text(text, encoding="utf-8")
        for args in ((), ("--check",)):
            r = build(ex, *args)
            assert r.returncode == 1 and "Traceback" not in r.stderr, text
            assert "card-ids.json" in r.stderr and "repair" in r.stderr and "list of card id strings" in r.stderr, text
        assert (ex / "card-ids.json").read_text(encoding="utf-8") == text          # never overwritten


def test_whitespace_only_retired_reason_is_error(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "retired.json").write_text('{"ex-gone": "   "}', encoding="utf-8")
    r = build(ex)
    assert r.returncode == 1 and "retired.json" in r.stderr and "non-empty reasons" in r.stderr


def test_unreadable_previous_build_json_is_noted_and_skipped(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "build").mkdir()
    (ex / "build" / "build.json").write_text("{broken", encoding="utf-8")
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert "previous build.json unreadable" in r.stderr


def test_example_ledger_is_tracked_and_current():
    cards = json.loads((EX / "cards" / "basics.json").read_text(encoding="utf-8"))
    ids = ledger(EX)
    assert ids == sorted(ids) and {c["id"] for c in cards} <= set(ids)    # retired ids may stay in it


def test_ledger_write_is_atomic(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from engine import build as b
    ex = fresh(tmp_path)
    (ex / "card-ids.json").write_text(json.dumps(IDS), encoding="utf-8")
    real = pathlib.Path.write_text

    def crash(self, data, *a, **k):          # write half the data, then die like an interrupted process
        real(self, data[: len(data) // 2], *a, **k)
        raise KeyboardInterrupt

    monkeypatch.setattr(pathlib.Path, "write_text", crash)
    try:
        b.write_ledger(ex, {}, IDS + ["ex-new"])
    except KeyboardInterrupt:
        pass
    monkeypatch.undo()
    assert ledger(ex) == IDS                 # the old ledger is intact


def test_summary_and_manifest_count_tiers(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "sources" / "exam-guide").mkdir()
    (ex / "sources" / "exam-guide" / "guide.md").write_text("x", encoding="utf-8")
    edit_exam(ex, lambda e: e.update(source_tiers={"exam-guide": "primary", "podcasts": "hypothesis"}))
    edit_cards(ex, lambda cs: cs[2].update(src="source:exam-guide/guide.md"))
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert "   source tiers: primary 1, guide 1, note 1" in r.stderr, r.stderr
    m = json.loads((ex / "build" / "build.json").read_text())
    assert m["by_tier"] == {"primary": 1, "guide": 1, "note": 1}


def test_summary_without_tiers_counts_source(tmp_path):
    ex = copy_example(tmp_path)
    r = build(ex)
    assert r.returncode == 0, r.stderr
    assert "   source tiers: guide 1, note 1, source 1" in r.stderr, r.stderr
    assert json.loads((ex / "build" / "build.json").read_text())["by_tier"] == {"guide": 1, "note": 1, "source": 1}


def test_hypothesis_card_fails_build(tmp_path):
    ex = copy_example(tmp_path)
    (ex / "sources" / "podcasts").mkdir()
    (ex / "sources" / "podcasts" / "x.md").write_text("x", encoding="utf-8")
    edit_exam(ex, lambda e: e.update(source_tiers={"podcasts": "hypothesis"}))
    edit_cards(ex, lambda cs: cs[2].update(src="source:podcasts/x.md"))
    r = build(ex)
    assert r.returncode == 1
    assert "is hypothesis-tier (podcasts) and cannot back a card" in r.stderr
    assert outputs(ex) == []
