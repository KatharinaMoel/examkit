import json, pathlib, copy, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engine import validate as v

EX = pathlib.Path(__file__).resolve().parents[1] / "example"

def load():
    exam = json.loads((EX / "exam.json").read_text())
    cov = json.loads((EX / "coverage.json").read_text())
    cards = v.load_cards(EX / "cards")
    return exam, cov, cards

def run(cards, exam=None, cov=None):
    e, c, _ = load()
    return v.validate(cards, exam or e, cov or c, EX / "notes", EX / "sources")

def test_example_is_valid():
    _, _, cards = load()
    assert run(cards) == []

def test_detects_planted_error_first():
    # Lernprotokoll 13.09.: erst einen Treffer erzeugen, dann messen
    _, _, cards = load()
    bad = copy.deepcopy(cards); del bad[0]["a"]
    assert any("field a" in m for m in run(bad))

def test_unknown_guide_id():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[1]["src"] = "guide:3.9"
    msgs = run(bad)
    assert any("guide:3.9" in m for m in msgs)

def test_note_heading_renamed():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["src"] = "note:intro#What a basic was"
    msgs = run(bad)
    assert any("intro.md" in m and "What a basic was" in m for m in msgs)

def test_missing_source_file():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[2]["src"] = "source:nope.md"
    assert any("nope.md" in m for m in run(bad))

def test_bad_src_format():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["src"] = "01 §1 Schachtelung"
    assert any("src" in m and "01 §1" in m for m in run(bad))

def test_language_not_allowed():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["lang"] = "fr"
    assert any("lang" in m and "fr" in m for m in run(bad))

def test_covers_unknown_id():
    _, _, cards = load()
    bad = copy.deepcopy(cards); bad[0]["covers"] = ["9.9"]
    assert any("covers" in m and "9.9" in m for m in run(bad))

def test_duplicate_id():
    _, _, cards = load()
    bad = copy.deepcopy(cards) + [copy.deepcopy(cards[0])]
    assert any("duplicate" in m and "ex-basic-def" in m for m in run(bad))

def test_priority_and_deck_and_ctx_src():
    _, _, cards = load()
    bad = copy.deepcopy(cards)
    bad[0]["p"] = 4; bad[1]["deck"] = "nope"; bad[2]["ctx_src"] = "guess"
    msgs = run(bad)
    assert any("p must be" in m for m in msgs)
    assert any("deck" in m and "nope" in m for m in msgs)
    assert any("ctx_src" in m and "guess" in m for m in msgs)

def test_no_cards():
    assert any("no cards" in m for m in run([]))

def _with(**changes):
    _, _, cards = load()
    bad = copy.deepcopy(cards)
    bad[0].update(changes)
    return run(bad)

def test_covers_null_does_not_crash():
    assert any("covers must be a list of ids" in m for m in _with(covers=None))

def test_covers_nested_list_does_not_crash():
    assert any("covers must be a list of ids" in m for m in _with(covers=[["x"]]))

def test_covers_string_is_rejected():
    msgs = _with(covers="1.1")
    assert any("covers must be a list of ids" in m for m in msgs)
    assert len(msgs) == 1

def test_key_string_is_rejected():
    assert any("key must be a list of strings" in m for m in _with(key="smallest unit"))

def test_deck_list_does_not_crash():
    assert any("deck" in m for m in _with(deck=["a"]))

def test_ctx_src_and_lang_lists_do_not_crash():
    msgs = _with(ctx_src=["a"], lang=["en"])
    assert any("ctx_src" in m for m in msgs)
    assert any("lang" in m for m in msgs)

def test_id_list_does_not_crash():
    assert any("id must be a string" in m for m in _with(id=["a"]))

def test_bare_string_card(tmp_path):
    (tmp_path / "x.json").write_text('["x"]')
    cards = v.load_cards(tmp_path)
    msgs = run(cards)
    assert any("card #1 in x.json is not an object" in m for m in msgs)

def test_p_bool_and_float_rejected():
    assert any("p must be" in m for m in _with(p=True))
    assert any("p must be" in m for m in _with(p=1.0))

def test_messages_include_file():
    msgs = _with(p=4)
    assert any("ex-basic-def (basics.json)" in m for m in msgs)


def test_unsure_and_conflict_must_be_strings():
    assert any("unsure must be a non-empty string" in m for m in _with(unsure=5))
    assert any("conflict must be a non-empty string" in m for m in _with(conflict=["a"]))
    assert any("unsure must be a non-empty string" in m for m in _with(unsure="  "))
    assert not any("unsure" in m for m in _with(unsure="Checked against the 2026 guide only"))


def test_null_languages_and_decks_do_not_crash():
    _, _, cards = load()
    msgs = run(cards, exam={"decks": None, "languages": None})
    assert any("deck" in m for m in msgs)


# --- source tiers -----------------------------------------------------------

TIERS = {"exam-guide": "primary", "classroom": "official", "podcasts": "hypothesis"}


def _tiered_sources(tmp_path):
    src = tmp_path / "sources"
    for rel in ("exam-guide/guide.md", "classroom/lesson.md", "podcasts/x.md", "unlisted/y.md", "loose.md"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x", encoding="utf-8")
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    return src


def _tiered(tmp_path, src, tiers=TIERS):
    """Validate the example cards with card #3 pointing at ``src`` under tiered sources."""
    exam, cov, cards = load()
    exam = dict(exam, source_tiers=tiers)
    bad = copy.deepcopy(cards)
    bad[2]["src"] = src
    return v.validate(bad, exam, cov, EX / "notes", _tiered_sources(tmp_path))


def test_tier_primary_and_official_accepted(tmp_path):
    assert _tiered(tmp_path, "source:exam-guide/guide.md") == []
    assert _tiered(tmp_path, "source:classroom/lesson.md") == []


def test_tier_hypothesis_rejected(tmp_path):
    msgs = _tiered(tmp_path, "source:podcasts/x.md")
    assert any("src 'source:podcasts/x.md' is hypothesis-tier (podcasts) and cannot back a card; "
               "cite a primary/official source and mention the origin in ctx" in m for m in msgs), msgs


def test_tier_unknown_folder_rejected(tmp_path):
    msgs = _tiered(tmp_path, "source:unlisted/y.md")
    assert any("unlisted" in m and "exam.source_tiers" in m for m in msgs), msgs


def test_tier_file_without_folder_rejected(tmp_path):
    msgs = _tiered(tmp_path, "source:loose.md")
    assert any("loose.md" in m and "tier folder" in m for m in msgs), msgs


def test_tier_escaping_paths_rejected(tmp_path):
    for src in ("source:../outside.md", "source:./exam-guide/guide.md",
                "source:podcasts/../exam-guide/guide.md", f"source:{tmp_path / 'outside.md'}"):
        msgs = _tiered(tmp_path, src)
        assert any(src in m and "escape" in m for m in msgs), (src, msgs)


def test_tier_missing_file_still_reported(tmp_path):
    msgs = _tiered(tmp_path, "source:exam-guide/nope.md")
    assert any("nope.md" in m and "not found" in m for m in msgs), msgs


def test_without_tiers_old_behaviour(tmp_path):
    # no source_tiers: a loose file and even a podcast file are accepted as before
    _tiered_sources(tmp_path)
    assert v.resolve_src("source:loose.md", set(), EX / "notes", tmp_path / "sources") is None
    assert v.resolve_src("source:podcasts/x.md", set(), EX / "notes", tmp_path / "sources") is None
    exam, _, _ = load()
    assert "source_tiers" not in exam


def test_without_tiers_escaping_paths_rejected(tmp_path):
    # no source_tiers: ./, ../ and absolute paths are refused even when the file exists
    src_dir = _tiered_sources(tmp_path)
    for src in ("source:../outside.md", "source:./loose.md",
                "source:podcasts/../loose.md", f"source:{tmp_path / 'outside.md'}"):
        msg = v.resolve_src(src, set(), EX / "notes", src_dir)
        assert msg is not None and src in msg and "escape" in msg, (src, msg)
    exam, cov, cards = load()
    bad = copy.deepcopy(cards)
    bad[2]["src"] = "source:../outside.md"
    assert any("source:../outside.md" in m and "escape" in m
               for m in v.validate(bad, exam, cov, EX / "notes", src_dir))


def test_without_tiers_escaping_path_rejected_even_if_missing(tmp_path):
    msg = v.resolve_src("source:../nope.md", set(), EX / "notes", _tiered_sources(tmp_path))
    assert msg is not None and "escape" in msg, msg


NEUTRAL = "must be a plain relative path inside sources/ (no ./, ../ or absolute paths, which escape sources/)"


def test_escape_message_is_neutral_without_tiers(tmp_path):
    msg = v.resolve_src("source:../outside.md", set(), EX / "notes", _tiered_sources(tmp_path))
    assert msg == f"src 'source:../outside.md' {NEUTRAL}", msg


def _outside_links(tmp_path):
    src_dir = _tiered_sources(tmp_path)
    (src_dir / "link.md").symlink_to(tmp_path / "outside.md")
    (src_dir / "exam-guide" / "link.md").symlink_to(tmp_path / "outside.md")
    (src_dir / "exam-guide" / "inside.md").symlink_to(src_dir / "loose.md")
    return src_dir


def test_symlink_pointing_outside_rejected_without_tiers(tmp_path):
    src_dir = _outside_links(tmp_path)
    for src in ("source:link.md", "source:exam-guide/link.md"):
        msg = v.resolve_src(src, set(), EX / "notes", src_dir)
        assert msg is not None and src in msg and "escape" in msg, (src, msg)
    # a link that stays inside sources/ is fine
    assert v.resolve_src("source:exam-guide/inside.md", set(), EX / "notes", src_dir) is None


def test_symlink_pointing_outside_rejected_with_tiers(tmp_path):
    src_dir = _outside_links(tmp_path)
    msg = v.resolve_src("source:exam-guide/link.md", set(), EX / "notes", src_dir, source_tiers=TIERS)
    assert msg is not None and "source:exam-guide/link.md" in msg and "escape" in msg, msg
    assert v.resolve_src("source:exam-guide/inside.md", set(), EX / "notes", src_dir, source_tiers=TIERS) is None


def test_source_directory_is_not_a_file(tmp_path):
    src_dir = _tiered_sources(tmp_path)
    (src_dir / "exam-guide" / "sub").mkdir()
    for src, tiers in (("source:exam-guide", None), ("source:exam-guide/sub", None), ("source:exam-guide/sub", TIERS)):
        msg = v.resolve_src(src, set(), EX / "notes", src_dir, source_tiers=tiers)
        assert msg == f"src '{src}' is a directory, not a file", (src, tiers, msg)


def test_invalid_source_tiers_rejected(tmp_path):
    # the card cites a guide id, so each case plants exactly one error: the config error
    cases = [
        (["podcasts"], "exam.source_tiers: must be an object"),
        ({"podcasts": "secondary"}, "'podcasts'"),
        ({"podcasts": 1}, "'podcasts'"),
        ({"a/b": "primary"}, "'a/b'"),
        ({"": "primary"}, "''"),
        ({".": "primary"}, "'.'"),
        ({"..": "primary"}, "'..'"),
        ({"  ": "primary"}, "'  '"),
    ]
    for tiers, needle in cases:
        msgs = _tiered(tmp_path, "guide:svc:thing", tiers=tiers)
        assert len(msgs) == 1 and "exam.source_tiers" in msgs[0] and needle in msgs[0], (tiers, msgs)
    # a valid object produces no config error
    assert _tiered(tmp_path, "guide:svc:thing") == []


def test_broken_tiers_config_rejects_source_cards(tmp_path):
    # fail closed: a source_tiers that is not an object must not reopen the door for source: cards
    msgs = _tiered(tmp_path, "source:exam-guide/guide.md", tiers=["exam-guide"])
    assert any("source:exam-guide/guide.md" in m and "exam.source_tiers" in m for m in msgs), msgs


def test_tier_empty_segment_named(tmp_path):
    for src in ("source:exam-guide/", "source:exam-guide//guide.md"):
        msgs = _tiered(tmp_path, src)
        assert any(src in m and "empty path segment" in m for m in msgs), (src, msgs)


def test_source_tier_of():
    assert v.source_tier("guide:1.1", TIERS) == "guide"
    assert v.source_tier("note:intro#X", TIERS) == "note"
    assert v.source_tier("source:exam-guide/guide.md", TIERS) == "primary"
    assert v.source_tier("source:classroom/lesson.md", TIERS) == "official"
    assert v.source_tier("source:dummy.md", None) == "source"
